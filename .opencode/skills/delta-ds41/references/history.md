# DS41 maintenance history

This is the continuation record for the local RTX Spark setup. Entries describe
what was decided and checked at the time; current configuration takes precedence.
Keep summaries here and detailed results in their existing files. Local `logs/`
artifacts may be absent in another checkout.

## 2026-11-13 — Windows unified-memory tuning

The objective was fast, accurate interactive coding/chat with DeepSeek V4.1 Flash
1017 UD-IQ2_XXS on RTX Spark N1X, Windows ARM64. The working split was 96 GiB
dedicated GPU memory and 32 GiB host memory (about 30.5 GiB visible to Windows).
The old 64 GiB host expert arena could not fit this allocation.

The retained settings were an 8 GiB arena, 8 GiB GPU margin, upload working-set
trimming, 512 MiB staging, and prompt batch 12288. The local settings' recorded
comparison reports 10–23% improvements on four coding checks and 4.2 GiB host
headroom with a 23,742-token prompt. Images were not benchmarked. These results
do not establish that this memory split is best for every workload.

Read [ds41-paths.bat](../../../../ds41-paths.bat) for current overrides and the
local results path. The existing bundled MTP drafter was retained. The normal
profile includes approximations; do not describe the complete profile as exact.

## 2026-11-14 — Dependencies, security, and outbound behavior

Two GGUF overflow fixes were backported and the ARM64 CUDA engine rebuilt.
Helper manifests and HTTP response headers were updated. Changes to vendored
llama.cpp were retained in the canonical patch rather than a blanket vendor update.
Five native GGUF cases, eleven Python tests, two live DS41 checks, and an isolated
CLIP conversion were recorded as passing; this did not cover all converters.

The [review record](../../../../tools/security/review-2026-11-14.json) contains
versions, advisories, results, residual findings, and limitations. The review left
unused vendor UI dependency findings, container warnings, and CSP hardening work
visible. No external connections were observed in the monitored scenarios; that
does not cover every feature or establish absence of all outbound behavior.

Dependency-Check remains blocked by unavailable NVD access. The user explicitly
chose to leave it blocked and finish the other checks. Do not request the key again
unless circumstances change. [SECURITY.md](../../../../SECURITY.md) documents the
on-demand scanner; no continuous monitoring was established.

## 2026-11-14 — OpenCode continuation skill

The user requested a small OpenCode skill and prefers history as the organizing
idea. This project-local skill connects operations, controlled comparisons, and
security maintenance through the existing files and this dated record. It adds
no service and requires no MCP configuration. The bundled management MCP still
needs DS41-specific validation before use with the tuned launcher.

For later entries, record the date, user objective, decision and alternatives,
files changed, measured/tested results, limits, and remaining work. Keep historical
results intact and add a correction or superseding entry when needed.

## 2026-11-14 — Goal expanded to sandboxed harness improvement

The user proposed allowing the model to modify its own harness through MCP,
inside NVIDIA OpenShell. The current skill supplies maintenance instructions;
it does not implement hot-patching. The [recorded goal](openshell-goal.md) describes
candidate patches, controlled testing and activation, recovery, and history.
The intended boundary keeps sandbox policy and activation controls outside the
model's writable harness. Native Windows ARM64 OpenShell remains experimental
according to NVIDIA's linked guide, so platform qualification is the first
milestone. This entry records the goal, not a completed integration.

## 2026-11-14 — Platform checks and pre-implementation checkpoint

The user requested a local Git commit before implementation, without a push.
No harness-patching code has been added. The checkpoint includes the existing
ARM64 work, security fixes and scanner, and OpenCode skill with its history.
Pre-commit verification passed 35 Python tests and five native GGUF cases.

The installed OpenShell reports `0.1.5-dev.40+g5b9e5b91a`. Fetching the upstream
`windows` branch returned the same full commit,
`5b9e5b91afb10afbce8d9be09e2513a7efc22a21`; the checkout is clean. All five installed
artifacts match their installation-manifest hashes, and the four OpenShell
executables in the retained trial directory match the active executables.
These checks identify the installed build; they do not establish the provenance
of any earlier local patches beyond the installation record.

The [general OpenShell release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.8)
is 0.1.8, but native Windows follows its separate branch. Installed MXC reports
`1.0.0+7bf21024` and its Authenticode signature validates. Microsoft has released
[MXC 1.0.1](https://github.com/microsoft/mxc/releases/tag/v1.0.1), including
ProcessContainer loopback and network-denial reporting fixes. No upgrade was
performed during this checkpoint.

The MXC host probe passed, including `baseContainerSupportsIngressHostLoopbackAllow`.
Two real upstream MXC scenarios passed on the installed binaries: `fs-rw`
produced its permitted write; `fs-readonly` produced its control write and
blocked the prohibited write. Local run histories are under the neighboring
OpenShell-windows checkout's `target/windows-e2e-results/`, runs
`results-e2e-20261114-023202` and `results-e2e-20261114-023239`.
The disposable gateway used port 17681 and was stopped after each run; no
persistent gateway was registered. These checks do not test egress containment,
OpenCode/MCP execution, activation, rollback, or resolve upstream's Windows
isolation limitations. WSL2 Ubuntu 26.04 has Docker installed, but its normal
user cannot access the Docker socket; no fallback deployment was made.

Next: compare MXC 1.0.1 in a separate installation, retain the current binaries,
then qualify the sandbox and implement the bounded skill-patching prototype.
