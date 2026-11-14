// Native ARM64 Q2_0 rows. Quantization preserves ActQ's legacy FP32 scale
// and half-away rounding; the optional oracle uses FP16 scales and ties-even.
#include "strata/kernels/cpu/expert.hpp"
#include "strata/kernels/f16_bits.hpp"
#include <arm_neon.h>
#include <algorithm>
#include <cmath>
#include <cstring>

namespace strata::kernels::cpu {
namespace {
float half_at(const uint8_t* p) {
    uint16_t h;
    std::memcpy(&h, p, sizeof h);
    return f32_from_f16(h);
}

// Four packed bytes contain sixteen consecutive two-bit weights. Decode to
// signed weights [-1, 2], then accumulate exact int32 products before scaling.
int dot16(const uint8_t* codes, const int8_t* q) {
    uint32_t packed;
    std::memcpy(&packed, codes, sizeof packed);
    static const uint8_t indices[16] = {0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3};
    static const int8_t shifts[16] = {0,-2,-4,-6,0,-2,-4,-6,0,-2,-4,-6,0,-2,-4,-6};
    const uint8x16_t bytes = vqtbl1q_u8(vreinterpretq_u8_u32(vdupq_n_u32(packed)), vld1q_u8(indices));
    const uint8x16_t c = vandq_u8(vshlq_u8(bytes, vld1q_s8(shifts)), vdupq_n_u8(3));
    const int8x16_t w = vsubq_s8(vreinterpretq_s8_u8(c), vdupq_n_s8(1));
    const int8x16_t x = vld1q_s8(q);
#if defined(__ARM_FEATURE_DOTPROD)
    return vaddvq_s32(vdotq_s32(vdupq_n_s32(0), w, x));
#else
    return vaddlvq_s16(vmull_s8(vget_low_s8(w), vget_low_s8(x))) +
           vaddlvq_s16(vmull_high_s8(w, x));
#endif
}

float row_dot(const uint8_t* codes, size_t code_stride, const uint8_t* scales,
              size_t scale_stride, const ActQ& a, int nblocks) {
    float result = 0.f;
    for (int b = 0; b < nblocks; ++b) {
        float block = 0.f;
        for (int h = 0; h < 2; ++h) {
            const auto* c = codes + b * code_stride + h * 8;
            const auto* q = a.q + b * QK + h * QKA;
            const int dot = dot16(c, q) + dot16(c + 4, q + 16);
            block += (float) dot * a.scale[2 * b + h];
        }
        result += half_at(scales + b * scale_stride) * block;
    }
    return result;
}
}

void act_quant_q8_1(const float* x, int n, ActQ& a) {
    a.nchunks = n / QKA;
    a.bp_pairs = 0;
    const bool oracle = expert_oracle_q8_0_enabled();
    for (int k = 0; k < a.nchunks; ++k) {
        const float* xb = x + k * QKA;
        float32x4_t vmax = vdupq_n_f32(0.f);
        for (int j = 0; j < QKA; j += 4) vmax = vmaxq_f32(vmax, vabsq_f32(vld1q_f32(xb + j)));
        const float amax = vmaxvq_f32(vmax);
        const float s = amax / 127.f;
        const float inv = oracle ? (amax != 0.f ? 127.f / amax : 0.f) : (s > 0.f ? 1.f / s : 0.f);
        int sum = 0;
        for (int j = 0; j < QKA; j += 4) {
            const float32x4_t t = vmulq_n_f32(vld1q_f32(xb + j), inv);
            // Legacy x86 uses add-half then truncate, including its FP32
            // rounding at values immediately adjacent to a half-integer.
            const float32x4_t bias = vbslq_f32(vcgeq_f32(t, vdupq_n_f32(0.f)),
                                                vdupq_n_f32(.5f), vdupq_n_f32(-.5f));
            int32x4_t q = oracle ? vcvtnq_s32_f32(t) : vcvtq_s32_f32(vaddq_f32(t, bias));
            q = vmaxq_s32(vdupq_n_s32(-127), vminq_s32(vdupq_n_s32(127), q));
            int32_t values[4];
            vst1q_s32(values, q);
            for (int i = 0; i < 4; ++i) { a.q[k * QKA + j + i] = (int8_t) values[i]; sum += values[i]; }
        }
        a.scale[k] = oracle ? f32_from_f16(f16_from_f32(s)) : s;
        a.sum[k] = sum;
        a.hx[k] = a.scale[k] * (float) sum;
    }
}

void q2_0_gguf_rows_multi(const uint8_t* w, size_t row_bytes, int nblocks,
                         const ActQ* const* a, int nt, float* const* out, int r0, int r1) {
    for (int r = r0; r < r1; ++r) {
        const uint8_t* row = w + (size_t) r * row_bytes;
        for (int t = 0; t < nt; ++t) out[t][r] = row_dot(row + 2, BB, row, BB, *a[t], nblocks);
    }
}

void s2_expert_gu_rows(const uint8_t* blob, const ActQ& a, float* ff, int r0, int r1) {
    for (int r = r0; r < r1; ++r) {
        const float g = row_dot(blob + O_GU_CODES + (size_t) (2*r) * ROW_GU, 16,
                               blob + O_GU_SCALES + (size_t) (2*r) * SC_GU * 2, 2, a, SC_GU);
        const float u = row_dot(blob + O_GU_CODES + (size_t) (2*r+1) * ROW_GU, 16,
                               blob + O_GU_SCALES + (size_t) (2*r+1) * SC_GU * 2, 2, a, SC_GU);
        ff[r] = (g / (1.f + std::exp(-g))) * u;
    }
}
void s2_expert_down_rows(const uint8_t* blob, const ActQ& a, float* out, int r0, int r1) {
    for (int r = r0; r < r1; ++r)
        out[r] = row_dot(blob + O_D_CODES + (size_t) r * ROW_D, 16,
                        blob + O_D_SCALES + (size_t) r * SC_D * 2, 2, a, SC_D);
}
void s2_expert_gu_rows_multi(const uint8_t* blob, const ActQ* const* a, int nt, float* const* ff, int r0, int r1) {
    for (int t = 0; t < nt; ++t) s2_expert_gu_rows(blob, *a[t], ff[t], r0, r1);
}
void s2_expert_down_rows_multi(const uint8_t* blob, const ActQ* const* a, int nt, float* const* out, int r0, int r1) {
    for (int t = 0; t < nt; ++t) s2_expert_down_rows(blob, *a[t], out[t], r0, r1);
}
void s2_expert_vnni_q(const uint8_t* blob, const ActQ& a, float* out, ExpertScratch& ws) {
    s2_expert_gu_rows(blob, a, ws.ff, 0, FF);
    act_quant_q8_1(ws.ff, FF, ws.a2);
    s2_expert_down_rows(blob, ws.a2, out, 0, H);
}
void s2_expert_vnni(const uint8_t* blob, const float* x, float* out, ExpertScratch& ws) {
    act_quant_q8_1(x, H, ws.a1);
    s2_expert_vnni_q(blob, ws.a1, out, ws);
}
void s2_expert_vnni_multi(const uint8_t* blob, const ActQ* const* a, int nt, float* const* out, ExpertScratchMulti& ws) {
    for (int t = 0; t < nt; ++t) s2_expert_vnni_q(blob, *a[t], out[t], ws.single);
}
bool q2_bitplane_enabled() { return false; }
}  // namespace strata::kernels::cpu
