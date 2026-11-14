#pragma once

#if defined(__x86_64__) || defined(__i386__) || defined(_M_X64) || defined(_M_IX86)
#define STRATA_CPU_X86 1
#include <immintrin.h>
#else
#define STRATA_CPU_X86 0
#endif
#if defined(_MSC_VER) && defined(_M_ARM64)
#include <intrin.h>
#endif
#include <atomic>

namespace strata::platform {
inline void spin_pause() {
#if STRATA_CPU_X86
    _mm_pause();
#elif defined(_MSC_VER) && defined(_M_ARM64)
    __yield();
#elif defined(__aarch64__)
    __asm__ __volatile__("yield");
#endif
}

// Host writes may be observed by a CUDA device through mapped memory. Use a
// system-scope barrier on ARM, including the compiler barrier.
inline void store_fence() {
#if STRATA_CPU_X86
    _mm_sfence();
#elif defined(_MSC_VER) && defined(_M_ARM64)
    __dmb(0xf);
#elif defined(__aarch64__)
    __asm__ __volatile__("dmb sy" ::: "memory");
#else
    std::atomic_thread_fence(std::memory_order_seq_cst);
#endif
}
}
