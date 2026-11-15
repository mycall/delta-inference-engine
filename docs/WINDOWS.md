# DeepSeek-V4.1-Flash on Windows (native, no WSL)

The DeepSeek-V4.1 engine (`tools/v41/engine`) builds and serves natively on Windows 11 with MSVC + CUDA.

Tested on one machine:
- RTX 3090 24 GB, Ryzen 7 5800X, 128 GB DDR4-3200, Samsung 990 EVO Plus NVMe
- Windows 11 Pro, driver 616.92, CUDA 12.8, Visual Studio 2022 Build Tools

Other cards should work with `CUDA_ARCH` set (89 = RTX 40). Reports are welcome.

**RTX 50 (sm_120), from a community build on an RTX 5090 D v2 ([#14](https://github.com/Indras-Mirror/Xolotl/issues/14)):**
- CUDA 12.8 cannot build sm_120 here: ptxas rejects the MXFP4 kernel's block-scale mma (`.kind::mxf4 not supported on
  .target 'sm_120'`). Use **CUDA 13.1** with `-DCMAKE_CUDA_ARCHITECTURES=120a`; plain `120` fails the same way, the `a`
  suffix is required.
- If a newer Visual Studio (e.g. "18" Build Tools) is installed, `vswhere -latest` picks it and nvcc refuses it as the
  host compiler (`C1189: unsupported Microsoft Visual Studio version`). Point VCVARS at the **VS 2022** Build Tools
  `vcvars64.bat`.
- The config's `"tokenizer"` must be the folder that directly holds `vocab.json`, `merges.txt` and `token_type.json`.
  Serve now also accepts the model folder when the files sit in its `tokenizer/` subfolder (the HF repos' layout).

## What you need

| | |
| --- | --- |
| GPU | NVIDIA, 24 GB, driver new enough for CUDA 12.8 |
| RAM | 128 GB recommended for the 72 GiB arena in the example configs; lower `--arena-gib` on smaller machines |
| Disk | ~370 GB on an NVMe (NTFS): the model (148-163 GB) + the official Engram shards (203 GB), plus room for the parts while joining |
| Tools | Visual Studio 2022 (Desktop development with C++), CUDA Toolkit 12.8+ (13.1+ for RTX 50), Git for Windows (Git Bash), Python 3.12 |

## 1. Code and llama.cpp

```bat
git clone https://github.com/Indras-Mirror/Xolotl
cd Xolotl
```

Then, in **Git Bash**, from the repo root:

```bash
bash tools/xolotl/fetch-llama.sh      # llama.cpp at the pinned commit + the Xolotl ggml patch
```

## 2. Build

```bat
python -m venv .venv-build
.venv-build\Scripts\pip install cmake ninja
build-win.bat configure
build-win.bat
```

- `build-win.bat` finds Visual Studio through `vswhere` and CUDA through `CUDA_PATH`.
- Set `CUDA_ARCH` for your card (default 86).
- It runs 6 parallel jobs by default; set `JOBS` to change that. Full parallel nvcc can exhaust RAM.
- Output: `build-win\ds41_generate.exe`.

### Windows on ARM64 (RTX Spark)

`build-ds41.bat` detects native Windows ARM64, including an x64 shell running under
emulation, and builds into `build-ds41-arm64`. This path enables the experimental
`STRATA_ARM64` CMake option. The x86 portable and compatibility builds cannot be used
with the ARM64 CUDA libraries.

The native build needs Visual Studio's ARM64 C++ tools, its ARM64 Clang tools, CMake
with Windows ARM64 CUDA support, and the ARM64 CUDA Toolkit (13.4 or newer). The
toolkit must contain `lib/arm64/cudadevrt.lib`; adding that directory to an x64
linker's search path does not fix an architecture mismatch. NVIDIA documents the
[ARM64 compiler and CUDA environment](https://docs.nvidia.com/rtx-spark/rtx-spark-porting-guide/latest/porting/build.html).

The build uses clang-cl for C/C++, nvcc with the ARM64 MSVC host compiler for CUDA,
and `121a` for the RTX Spark N1X GPU. CPU expert formats handled by ggml use its ARM
NEON kernels. Strata's Q2_0 rows use NEON integer dot products; the legacy activation
scale and rounding rules are preserved. Floating-point row reductions can differ
in the last bits from the x86 kernels. The ARM target requires ARMv8.2, FP16 and dot
product instructions; this is not a build for every Windows ARM device. EXL3 CPU
experts still require AVX2 and are not enabled by this port.

`Start DeepSeek.bat` selects the native build and skips x86 release downloads on
ARM64. The engine accepts CUDA devices classified as integrated GPUs, including
RTX Spark, as well as discrete GPUs. Pictures setup also selects PyTorch for the Python interpreter's architecture.
For Windows ARM64 Python 3.14, the upstream CPU index has no compatible wheel;
setup uses NVIDIA's stable `torch==2.14.0+cu134` wheel (~1.9 GB) from its
[Windows ARM64 package index](https://github.com/NVIDIA/pytorch-windows-ci#install-built-wheels).
This CUDA-enabled package also runs CPU tensors: installing it does not change the
pictures device setting. Windows ARM64 Python 3.13 keeps the upstream CPU package
when pictures use the CPU. Setup resolves the replacement before removing an
installed PyTorch and checks a tensor operation after installation.

The engine tests need no model download:

```bat
python tools\v41\serve\test_cpu_level.py
python tools\v41\serve\test_install_torch.py
cmake --build build-ds41-arm64 --target arm64_cpu_test test_ds41_fq test_ds41_hcmix test_ds41_kvfp4
build-ds41-arm64\arm64_cpu_test.exe
build-ds41-arm64\test_ds41_fq.exe
build-ds41-arm64\test_ds41_fq.exe --cuda
build-ds41-arm64\test_ds41_hcmix.exe --cuda
build-ds41-arm64\test_ds41_kvfp4.exe --cuda
```

This covers the DeepSeek build and launcher. The separate `setup.py` installers,
HIP, SYCL and Metal builds are outside this Windows ARM64 CUDA path. No inference
speed comparison against x86 is claimed.

Validated on November 9, 2026, on Windows ARM64 with an RTX Spark N1X, CUDA 13.5.37,
Clang 22.1.3 and MSVC 19.51.36260: the engine and all three helpers built, the NEON
CPU tests and five launcher tests passed, and CUDA fake-quant, HC-mix and FP4-cache
tests had no bitwise differences from their references. The x64 CPU library also
built. The Unsloth UD-IQ2_XXS model loaded and returned a short chat response over
the local API; a streamed tool call and usage reporting also passed. PyTorch
2.14.0+cu134 passed CPU and CUDA tensor checks, and the downloaded vision encoder
produced finite embeddings for a synthetic 224-by-224 image on the CPU. These are
smoke tests, not quality or throughput benchmarks. HIP, SYCL and Metal were not
built in this environment; those build checks remain required before review.

On RTX Spark, CPU RAM and GPU allocations share physical memory. CUDA reports a
combined dedicated/shared budget; `nvidia-smi` reports the dedicated carveout.
Increasing that carveout leaves less memory for Windows and the expert arena.
See [NVIDIA's Windows UMA memory guide](https://docs.nvidia.com/rtx-spark/rtx-spark-porting-guide/latest/uma/umacuda.html).
The defaults measured on discrete GPUs can leave too little headroom here: on the
102 GiB Windows RAM / 24 GiB dedicated GPU configuration, a 74 GiB arena, 0.6 GiB
margin and 16,384-token batch encountered CUDA out-of-memory while regrowing the
cache after a 10,372-token prompt.

`DS41_PROMPT_BATCH` optionally overrides the prompt batch size, while retaining
the model-specific safety caps. Together with `DS41_ARENA_GIB` and
`DS41_VRAM_MARGIN`, it allows a smaller memory budget without changing the shipped
defaults. Set these in `ds41-paths.bat` or the launcher's environment, then restart
`Start DeepSeek.bat`. Smaller batches can slow prompt processing. The margin is
memory excluded from the GPU cache budget; it does not change the GPU carveout.

On that RTX Spark with Unsloth UD-IQ2_XXS, the following opt-in settings passed four
synthetic chat requests (short, 10,464 tokens, short, 10,465 tokens) without a CUDA
out-of-memory error or watchdog stall on November 9, 2026. Available Windows RAM,
sampled once per second, stayed at or above 6.6 GiB. The two long requests took
95.0 and 87.7 seconds including their answers; this is a stability smoke test,
not a throughput comparison or a guarantee for larger contexts or concurrent apps.

```bat
set "DS41_ARENA_GIB=64"
set "DS41_VRAM_MARGIN=16"
set "DS41_PROMPT_BATCH=2048"
```

## 3. Model files

### Local RTX Spark N1X qualification profile

`Start DeepSeek (RTX Spark tested).bat` selects an opt-in profile for the measured
96-GiB dedicated GPU / 32-GiB host split. It requires the existing October-17
Unsloth UD-IQ2_XXS shards and `V41-1017-MTP-iq2xxs-imx.gguf` in `DS41_MODELS`.
It uses the original engine, an 8-GiB CPU arena, 24-GiB GPU reserve, 512-token
prompt batch, 512-MiB staging and upload working-set trimming. CPU vision stays
lazy; image requests were not benchmarked. The ordinary launcher stays unchanged
unless the operator selects `DS41_CONFIG_TEMPLATE`.

The JSON template is `tools/v41/serve/profiles/rtx-spark-n1x-tested.json`. It pins
the recorded engine environment, including drafter depth 5 and expert counts
96/64/32. `STRATA_ENC_BOUND=0` explicitly preserves the test runs' unbounded
replay setting; the ordinary launcher sets 128. Routing biases remain 0.28/0.3
and dense weights are requantized to q5_K, so this is not an exact-routing or
full-precision accuracy claim. Model context allocation stays 1,048,576 tokens;
long contexts at that limit have not been qualified.

On November 14, 2026, with the user-configured 128-GiB initial / 160-GiB maximum
Windows pagefile active, four sequential comparison runs completed 24 requests
without engine replacement. Twenty sorting/loop contracts passed; four warm-ups
returned a JSON object instead of the requested number. Original and allocation
patch responses matched, with no meaningful speed advantage for the patch.
Original long-prompt medians were 92.87/95.16 seconds on the approximately
6.3K-token synthetic fixtures. Two actual contained OpenCode edit/export trials
then passed cold and warm using the same original-engine process. These results
cover a bounded workflow, not general accuracy or long-term stability.

The prepared template was checked against the qualified config's engine arguments
and recorded environment. Evidence is under
`logs/allocation-ab-5a0fef29506e424faf3f63057d2c724c/`; deployment history is in the
sibling integration repository's `history/2026-11-14-system-commit.md`. The reboot
changed background workloads too, so those results do not isolate a pagefile
speed improvement. This profile trades cache capacity and batch size for the
headroom needed by that deployment; it is not claimed faster than every older
configuration.

The qualified original executable's SHA-256 is
`8adace46da0058212abc28b7537d2f40a984512bfb6c47ed8b285e9f2af3d093`.
An allocation-retry experiment is retained under `tools/v41/experiments/` as an
unapplied patch; applying and rebuilding it requires fresh qualification. This launcher
reproduces configuration, not a source-to-binary reproducibility claim.

`tools/xolotl/win_fetch_files.py` downloads named files from a Hugging Face repo with curl. It resumes, checks every file against the LFS sha256, and needs no hf CLI. It puts files flat in the target folder, so the tokenizer files can sit next to the model.

Example: the official 1017 Engram shards plus the 1017 GSQ parts, then the join:

```bat
python tools\xolotl\win_fetch_files.py deepseek-ai/DeepSeek-V4.1-Flash-1017 main D:\models\dsv41-1017-engram ^
  config.json model.safetensors.index.json model-00047-of-00048.safetensors model-00048-of-00048.safetensors
python tools\xolotl\win_fetch_files.py IndrasMirror/DeepSeek-V4.1-Flash-1017-GSQ-Uncensored main D:\models\dsv41-1017-gsq ^
  SHA256SUMS rank-1017-085.bin V41-GSQ-1017.gguf.experts.json V41-MTP-Vision-1017.Q2_K.gguf ^
  tokenizer/vocab.json tokenizer/merges.txt tokenizer/token_type.json tokenizer/chat_template.jinja ^
  V41-GSQ-1017.gguf.part-01-of-15 ... V41-GSQ-1017.gguf.part-15-of-15
python tools\xolotl\win_join_parts.py D:\models\dsv41-1017-gsq V41-GSQ-1017.gguf
```

- `win_join_parts.py` is `reassemble.sh` without bash: it hashes while it joins, then checks the result against SHA256SUMS.
- **The Engram shards are read in place on NTFS**, so `extract_engram.py` is not needed.
- **GGUFs published as llama.cpp split shards** (`-00001-of-0000N.gguf`) must be merged first, because the expert tier reads a single file. `tools/xolotl/gguf_merge_shards.py` does it byte for byte without decoding Strata's tensor types (which llama.cpp's gguf-split cannot size):

  ```bat
  python tools\xolotl\gguf_merge_shards.py <model>-00001-of-0000N.gguf <model>.gguf
  ```

  Expert ranks from such builds (e.g. `expert-rank.json`, a list of `[layer, expert, count]`) convert to `--rank` files as int32 `(layer, expert)` pairs, hottest first.

## 4. Serve

```bat
python -m venv .venv-serve
.venv-serve\Scripts\pip install jinja2 regex
.venv-serve\Scripts\python -I tools\v41\serve\serve_ds41.py --engine strata --config tools\v41\serve\strata-ds41-1017-win.json --port 8150
```

The Windows configs are `strata-ds41*-win.json`. They carry `ds41-engine.sh`'s settings as `"env"`, because there is no flock or systemd-run on Windows. Edit their paths (`exe`, `-m`, `--engram`, `--rank`, `STRATA_SERVE_DSPARK`, `tokenizer`, `log`) for your folders.
- `--engram` takes `;` between folders on Windows.
- Browser chat and monitor: http://127.0.0.1:8150
- OpenAI API: `/v1`; Anthropic API: `/v1/messages`

## Measured on the test machine (served, greedy, 400 tokens, median of 3)

| Model | Prose | Code | Agent JSON | Prefill (13.3K prompt) |
| --- | ---: | ---: | ---: | ---: |
| V4.1 September GSQ, `--arena-gib 64`, PCIe share 1.0 | 13.0 | 17.4 | 15.7 tok/s | 209.5 tok/s |
| same, `--arena-gib 72`, `STRATA_TIER_BATCH_PCIE=0.75` | 14.7 | 22.1 | 18.8 tok/s | - |
| 1017, lxe's dsx 2-bit (merged), September DSpark draft | 12.3 | 18.6 | 15.4 tok/s | 131.9 tok/s |

Notes from this machine:
- **Large pages are not needed for CUDA copies on Windows.** 4 KB pinned pages copy to the card at 26 GB/s here (PCIe 4.0 x16).
- **Decode is bound by kernel-launch overhead.** CUDA graphs halve the dense half's time (`GGML_CUDA_DISABLE_GRAPHS=1` doubles it); the expert tier is not graphed yet.

## What the port changed

- **`tools/v41/engine/ds41_sys.hpp`:** the engine's file and memory calls on Win32. The Linux paths forward to the same POSIX calls as before.
  - Positional reads through `CreateFileW` + overlapped I/O; O_DIRECT maps to `FILE_FLAG_NO_BUFFERING`.
  - 64-bit offsets, because MSVC's `off_t` is 32-bit.
  - `_aligned_malloc` / `_aligned_free` pairs; `GlobalMemoryStatusEx` for MemAvailable.
- **Engram:** the raw block-device read (FIEMAP) is Linux-only; Windows reads the safetensors file.
- **MSVC:**
  - `ptq1_0.cpp` gets intrinsics without GCC target attributes.
  - `ds41_generate` links with an 8 MiB stack reserve, Linux's default, because of its alloca scratch.
  - `strcasecmp` maps to `_stricmp`.
  - `bench_ds41_engram` stays Linux-only.
- **A Windows-only heap corruption, fixed in CMakeLists.txt.** Every prompt batch over 96 tokens crashed with 0xC0000374.
  - `ds41_generate` links ggml-cuda (the dense half) and `strata_mmq`, which are two copies of llama.cpp's MMQ host code.
  - MSVC's linker takes a template instance (`mul_mat_q_case<T>`) from the first library on the line, `ggml-cuda.lib`, which is compiled with `GGML_CUDA_USE_GRAPHS`. That makes `ggml_backend_cuda_context` larger than the one `strata_mmq` allocates.
  - GNU ld searches forward only and keeps `strata_mmq`'s copy, so Linux never hits it.
  - The fix defines the same `GGML_CUDA_USE_GRAPHS` for `strata_mmq`, giving the same layout whichever copy the linker picks.
