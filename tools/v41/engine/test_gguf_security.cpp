// Regression cases for llama.cpp #26979 and #29384. No model files or GPU needed.
#include "gguf.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

static void append(std::vector<uint8_t> & out, uint64_t value, int bytes) {
    for (int i = 0; i < bytes; ++i) out.push_back(uint8_t(value >> (8 * i)));
}

static bool parses(const std::array<uint64_t, 4> & shape) {
    std::vector<uint8_t> data{'G', 'G', 'U', 'F'};
    append(data, 3, 4); // version
    append(data, 1, 8); // tensor count
    append(data, 0, 8); // metadata count
    append(data, 1, 8); data.push_back('x');
    append(data, 4, 4);
    for (auto dimension : shape) append(data, dimension, 8);
    append(data, GGML_TYPE_F32, 4);
    append(data, 0, 8); // data offset
    while (data.size() % GGUF_DEFAULT_ALIGNMENT) data.push_back(0);
    data.resize(data.size() + 32); // enough for the valid control, never a huge allocation
    auto * ctx = gguf_init_from_buffer(data.data(), data.size(), {true, nullptr});
    if (ctx) gguf_free(ctx);
    return ctx != nullptr;
}

int main() {
    struct Case { const char * name; std::array<uint64_t, 4> shape; bool accepted; };
    const Case cases[] = {
        {"small valid tensor", {4, 1, 1, 1}, true},
        {"zero-element tensor", {0, 1, 1, 1}, true},
        {"padded byte size wraps", {4, 1073741823, 1073741825, 1}, false},
        {"element product wraps to zero", {UINT64_C(1) << 32, UINT64_C(1) << 32, 1, 1}, false},
        {"element product exceeds INT64_MAX", {UINT64_C(1) << 32, UINT64_C(1) << 31, 1, 1}, false},
    };
    int failures = 0;
    for (const auto & c : cases) {
        const bool passed = parses(c.shape) == c.accepted;
        std::printf("%s: %s\n", passed ? "PASS" : "FAIL", c.name);
        failures += !passed;
    }
    return failures ? 1 : 0;
}
