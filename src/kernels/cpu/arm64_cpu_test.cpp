// Synthetic ARM64 correctness checks: no downloaded model or GPU required.
#include "strata/kernels/cpu/expert.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"
#include "strata/kernels/cpu/native_expert.hpp"
#include "strata/kernels/f16_bits.hpp"
#include "ggml.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

namespace cpu = strata::kernels::cpu;
using strata::kernels::f16_from_f32;
using strata::kernels::f32_from_f16;
static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr, "FAIL: %s\n", why); std::exit(1); }
}

static void q2_test() {
    std::mt19937 rng(5927);
    std::uniform_real_distribution<float> random(-4.f, 4.f);
    for (bool oracle : {false, true}) {
        cpu::expert_set_oracle_q8_0(oracle);
        for (int blocks : {1, 3, 8, 80}) {
            const int n = blocks * cpu::QK, rows = 5;
            std::vector<cpu::ActQ> a(8);
            std::vector<float> x(n);
            for (int t = 0; t < 8; ++t) {
                for (float& v : x) v = t == 0 ? 0.f : random(rng);
                if (t == 1) {
                    for (int i = 0; i < n; ++i) x[i] = (float) (i % 20 - 10) + .5f;
                    for (int i = 0; i < n; i += 32) x[i] = 127.f;
                }
                cpu::act_quant_any(x.data(), n, a[t]);
                require(a[t].nchunks == n / 32 && a[t].bp_pairs == 0, "ActQ dimensions");
                for (int k = 0; k < n / 32; ++k) {
                    float mx = 0.f;
                    for (int j = 0; j < 32; ++j) mx = std::max(mx, std::fabs(x[32*k+j]));
                    const float s = mx / 127.f;
                    const float inv = oracle ? (mx ? 127.f / mx : 0.f) : (s ? 1.f / s : 0.f);
                    int sum = 0;
                    for (int j = 0; j < 32; ++j) {
                        const float v = x[32*k+j] * inv;
                        int q = oracle ? (int) std::nearbyint(v) : (int) (v + (v >= 0 ? .5f : -.5f));
                        q = std::clamp(q, -127, 127);
                        require(a[t].q[32*k+j] == q, "Q2 activation rounding");
                        sum += q;
                    }
                    const float scale = oracle ? f32_from_f16(f16_from_f32(s)) : s;
                    require(a[t].scale[k] == scale && a[t].sum[k] == sum && a[t].hx[k] == scale * sum,
                            "Q2 activation scales and sums");
                }
            }
            const size_t stride = blocks * cpu::BB;
            std::vector<uint8_t> w(rows * stride);
            for (auto& v : w) v = (uint8_t) rng();
            for (int r = 0; r < rows; ++r) for (int b = 0; b < blocks; ++b) {
                uint16_t h = b % 3 == 0 ? 1 : f16_from_f32(random(rng));
                std::memcpy(w.data() + r*stride + b*cpu::BB, &h, 2);
            }
            for (int nt : {1, 3, 8}) {
                std::vector<std::vector<float>> y(nt, std::vector<float>(rows, -9876.f));
                const cpu::ActQ* ap[8]; float* yp[8];
                for (int t = 0; t < nt; ++t) { ap[t] = &a[t]; yp[t] = y[t].data(); }
                cpu::q2_rows_any(w.data(), stride, blocks, ap, nt, yp, 1, rows-1);
                for (int t = 0; t < nt; ++t) {
                    require(y[t][0] == -9876.f && y[t].back() == -9876.f, "Q2 row bounds");
                    std::vector<float> single(rows);
                    float* sp = single.data();
                    cpu::q2_rows_any(w.data(), stride, blocks, ap+t, 1, &sp, 1, rows-1);
                    for (int r = 1; r < rows-1; ++r) {
                        double ref = 0, magnitude = 0;
                        for (int b = 0; b < blocks; ++b) {
                            const auto* p = w.data() + r*stride + b*cpu::BB;
                            uint16_t h; std::memcpy(&h, p, 2);
                            for (int j = 0; j < 64; ++j) {
                                const int code = ((p[2+j/4] >> (2*(j%4))) & 3) - 1;
                                double v = (double) code * f32_from_f16(h) * a[t].scale[2*b+j/32] * a[t].q[64*b+j];
                                ref += v; magnitude += std::fabs(v);
                            }
                        }
                        require(std::fabs(y[t][r] - ref) <= 2e-6 * magnitude + 1e-6, "NEON Q2 rows vs decoded weights");
                        require(y[t][r] == single[r], "Q2 single/multi-token equality");
                    }
                }
            }
        }
    }
    cpu::expert_set_oracle_q8_0(false);
    std::puts("NEON Q2: quantization, decoded-weight parity, row bounds, and token grouping passed");
}

static void decode_activation(int type, const uint8_t* src, float* dst, int n) {
    const auto* traits = ggml_get_type_traits((ggml_type) type);
    if (traits->to_float) { traits->to_float(src, dst, n); return; }
    // Intermediate-only Q8_1/Q8_K have no public type-trait dequantizer.
    // Their payload is a scale, then (Q8_1: an FP16 sum), then signed bytes.
    require(type == GGML_TYPE_Q8_1 || type == GGML_TYPE_Q8_K, "activation reference format");
    const int block = type == GGML_TYPE_Q8_1 ? 32 : 256;
    const size_t stride = ggml_row_size((ggml_type) type, block);
    for (int k = 0; k < n; k += block, src += stride) {
        float scale;
        if (type == GGML_TYPE_Q8_1) {
            uint16_t h; std::memcpy(&h, src, 2); scale = f32_from_f16(h);
        } else {
            std::memcpy(&scale, src, 4);
        }
        for (int j = 0; j < block; ++j) dst[k+j] = scale * (int8_t) src[4+j];
    }
}

static double reference_dot(ggml_type type, const uint8_t* w, const uint8_t* a,
                            const float* decoded_w, const float* decoded_a, int n) {
    double result = 0;
    for (int j = 0; j < n; ++j) result += (double) decoded_w[j] * decoded_a[j];
    if (type == GGML_TYPE_Q5_1) {
        // Q5_1's minimum term consumes Q8_1's separately FP16-rounded sum.
        // A plain dot of dequantized values omits that extra rounding.
        const size_t wr = ggml_row_size(type, 32), ar = ggml_row_size(GGML_TYPE_Q8_1, 32);
        for (int k = 0; k < n; k += 32) {
            uint16_t m, s;
            std::memcpy(&m, w + (k/32)*wr + 2, 2);
            std::memcpy(&s, a + (k/32)*ar + 2, 2);
            double sum = 0;
            for (int j = 0; j < 32; ++j) sum += decoded_a[k+j];
            result += f32_from_f16(m) * (f32_from_f16(s) - sum);
        }
    }
    return result;
}

static void native_test() {
    constexpr int n = 256, nt = 3;
    std::mt19937 rng(864);
    std::uniform_real_distribution<float> rand(-.08f, .08f);
    for (ggml_type type : {GGML_TYPE_Q4_0, GGML_TYPE_Q5_1, GGML_TYPE_Q2_K, GGML_TYPE_Q4_K, GGML_TYPE_IQ4_NL}) {
        cpu::NativeFmt f;
        std::string err;
        require(cpu::native_fmt(type, type, n, n, f, err), "native format");
        const auto* wt = ggml_get_type_traits(type);
        require(wt->from_float_ref && wt->to_float, "reference weight conversion");
        std::vector<uint8_t> blob(f.bytes);
        std::vector<float> weights(n), decoded(n), input(n);
        for (size_t off = 0; off < blob.size(); off += f.gu_row) {
            for (float& v : weights) v = rand(rng);
            wt->from_float_ref(weights.data(), blob.data()+off, n);
        }
        std::vector<std::vector<uint8_t>> a(nt, std::vector<uint8_t>(f.act_bytes));
        std::vector<std::vector<uint8_t>> h(nt, std::vector<uint8_t>(f.h_bytes));
        std::vector<std::vector<float>> ff(nt, std::vector<float>(n)), out = ff, ad = ff, hd = ff;
        const void* ap[nt]; const void* hp[nt]; float* fp[nt]; float* op[nt];
        for (int t = 0; t < nt; ++t) {
            for (float& v : input) v = rand(rng) * 10;
            cpu::native_quant_act(f, input.data(), a[t].data());
            decode_activation(f.gu_act, a[t].data(), ad[t].data(), n);
            ap[t] = a[t].data(); fp[t] = ff[t].data(); op[t] = out[t].data();
        }
        cpu::native_gu_rows(f, blob.data(), ap, nt, fp, 0, n);
        double error = 0, magnitude = 0;
        for (int r = 0; r < n; ++r) {
            std::vector<float> up(n);
            wt->to_float(blob.data()+r*f.gu_row, decoded.data(), n);
            wt->to_float(blob.data()+f.up_off+r*f.gu_row, up.data(), n);
            for (int t = 0; t < nt; ++t) {
                const double g = reference_dot(type, blob.data()+r*f.gu_row, a[t].data(),
                                               decoded.data(), ad[t].data(), n);
                const double u = reference_dot(type, blob.data()+f.up_off+r*f.gu_row, a[t].data(),
                                               up.data(), ad[t].data(), n);
                const double ref = g/(1+std::exp(-g))*u;
                error += std::fabs(ff[t][r]-ref); magnitude += std::fabs(ref);
            }
        }
        require(error < 1e-4 * magnitude + 1e-7, "ggml NEON gate/up vs dequantized reference");
        for (int t = 0; t < nt; ++t) {
            cpu::native_quant_h(f, ff[t].data(), h[t].data()); hp[t] = h[t].data();
            decode_activation(f.d_act, h[t].data(), hd[t].data(), n);
        }
        cpu::native_down_rows(f, blob.data(), hp, nt, op, 0, n);
        error = magnitude = 0;
        for (int r = 0; r < n; ++r) {
            wt->to_float(blob.data()+f.down_off+r*f.d_row, decoded.data(), n);
            for (int t = 0; t < nt; ++t) {
                const double ref = reference_dot(type, blob.data()+f.down_off+r*f.d_row, h[t].data(),
                                                 decoded.data(), hd[t].data(), n);
                error += std::fabs(out[t][r]-ref); magnitude += std::fabs(ref);
            }
        }
        require(error < 1e-4 * magnitude + 1e-7, "ggml NEON down vs dequantized reference");
        std::printf("ggml NEON %s: gate/up and down passed\n", ggml_type_name(type));
    }
}
int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    require(!cpu::cpu_avx512_ok() && !cpu::cpu_avx2_ok() && !cpu::cpu_avx1_ok() &&
            !cpu::cpu_sse42_ok() && !cpu::cpu_avxvnni_ok(), "ARM must not dispatch x86 kernels");
    q2_test();
    native_test();
    return 0;
}
