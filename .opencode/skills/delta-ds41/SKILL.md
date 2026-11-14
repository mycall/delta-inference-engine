---
name: delta-ds41
description: Operate, troubleshoot, tune, or review the security of this repository's DeepSeek V4.1 Flash setup on Windows ARM64 RTX Spark. Use its decision and experiment history to continue maintenance across sessions.
---

# Delta DS41

Use this as a small entry point to the project's history and maintained files.
Read [history](references/history.md) first, then only the sources needed for the
current task. History explains past choices; inspect current files before acting.
Run commands from the repository root (`../../..` from this skill directory).
Follow [AGENTS.md](../../../AGENTS.md), including Semble for code discovery.

## Operate and diagnose

- Read [local settings](../../../ds41-paths.bat) and the
  [configuration template](../../../tools/v41/serve/ds41-windows.json).
  `tools/v41/serve/local/ds41-windows.json` is generated; change its inputs.
- Check the configured port, `/health`, and `/v1/models` before starting anything.
  Use `Start DeepSeek.bat` when a start is needed; it supplies required environment
  settings. Avoid duplicate engines and stopping an engine serving this OpenCode session.
- The local OpenAI-compatible API is normally `http://127.0.0.1:8080/v1`.
  Read the OpenCode provider example in [README.md](../../../README.md) if connecting
  a client. Keep network exposure and API authentication consistent with AGENTS.md.
- This skill requires no MCP service. Delta's bundled management MCP was not validated
  for the tuned DS41 launcher; integration needs a separate task and validation.
  For the planned MCP harness-patching capability, read the
  [OpenShell goal](references/openshell-goal.md); it is not implemented yet.

## Compare and improve

- Prioritize interactive coding/chat speed and correctness. Check the actual memory
  split, model, quantization, and overrides; historical settings are starting points.
- Change one variable. Compare a same-day baseline and candidate using the same
  prompts, sampling settings, context lengths, and cache conditions. Alternate runs
  when practical. Record first-token and total latency, prefill/decode rates,
  correctness, and host/GPU memory headroom. Follow the
  [benchmark guide](../../../docs/COMMUNITY_BENCHMARKS.md).
- Promote a default only after a measured improvement without an observed correctness
  regression; state test coverage. Exact speculation does not make a profile with
  approximate routing or quantization exact. Test new drafters against the existing one.
- For builds, read [Windows instructions](../../../docs/WINDOWS.md). Preserve the
  ARM64 environment and custom PyTorch installation. Vendor checkout steps can reset
  local changes: durable llama.cpp fixes belong in
  [the vendor patch](../../../tools/xolotl/ggml/xolotl-ggml.patch).

## Review security and retain history

- Follow [SECURITY.md](../../../SECURITY.md) and the dated review linked in history.
  Use `tools/security/scan.ps1 -Trivy <verified-trivy-executable>` for an on-demand
  scan. Treat package scans, native-code review, and outbound-connection monitoring
  as different checks. Preserve unresolved findings and scan failures explicitly.
- Keep raw reports and sensitive prompts in ignored local logs. Do not copy secrets
  into history. Old scan results describe that run, not the current security state.
- After meaningful work, append a concise dated history entry: request, decision,
  changes, comparison/test results, limitations, and next step. Link the maintained
  files or reports. Record rejected options so later sessions do not repeat them
  without a reason. Change this skill only when the workflow or pointers change.
