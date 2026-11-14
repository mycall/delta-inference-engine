# Goal: sandboxed harness improvement through MCP

Recorded 2026-11-14. Status: proposed architecture; no hot-patch tools, OpenShell
installation, or sandbox enforcement have been implemented by this skill.

Let the local DeepSeek V4.1 Flash model improve its OpenCode harness through a
small skill and narrowly scoped MCP tools, with NVIDIA OpenShell containing the
agent and patch execution. Preserve fast, accurate inference and a readable
history of what changed, why, and how it performed.

## Proposed responsibilities

- **Skill:** explain the workflow and load relevant history on demand.
- **OpenCode and MCP tools inside the sandbox:** inspect the permitted workspace,
  create candidate patches, run tests and comparisons, and report results. Tool
  processes and their children need containment too; a host-side unrestricted
  shell exposed through MCP would defeat this design.
- **Protected controller outside the writable workspace:** own sandbox policy,
  credentials, activation rules, and recovery. The model can propose changes to
  its skills, prompts, tool adapters, and harness code, but cannot grant itself
  broader permissions or change the controller's validation rules.
- **Delta inference:** initially retain the working Windows ARM64 CUDA service.
  Allow only the necessary API access from the sandbox. Validate connectivity
  and authentication explicitly; sandbox loopback is not necessarily host loopback.

## Patch lifecycle

1. Read history and inspect the current configuration and Git state. Select an
   isolated candidate workspace without disturbing existing local changes.
2. Produce a patch with a recorded base revision and candidate hash. Scope writes
   to the candidate; exclude policy, credentials, and active installation paths.
3. Run the relevant tests and security checks. Compare representative coding
   tasks for correctness, latency, and memory use against the working harness.
4. Have the protected controller activate the exact validated artifact under
   operator-defined rules. Avoid modifying the running process in place; use a
   controlled reload or restart appropriate to the component.
5. Verify health and recover to the previous working version on failure. Record
   success, rejection, or recovery in history, including limitations.

MCP tools such as inspect, stage, test, compare, and request-activation are proposed
interfaces, not existing capabilities. Keep inference-engine and GPU changes out
of the first harness-only prototype so it can be tested without interrupting the
model supplying the agent.

## Platform qualification comes first

NVIDIA's [Windows guide](https://github.com/NVIDIA/OpenShell/blob/main/WINDOWS.md)
currently places native x64/ARM64 support on the `windows` branch using Microsoft
MXC ProcessContainer. It explicitly says the boundary is not production-qualified:
exclusive mediated egress and live revocation are unverified, and the loopback
exception can expose unrelated host services. A successful build does not resolve
these limitations.

The first implementation milestone is a compatibility and containment experiment
on this RTX Spark: check the MXC host probe, OpenCode execution, inference access,
filesystem restrictions, blocked destinations, child processes, and recovery.
Do not claim full isolation from passing a limited test. If native MXC cannot meet
the required boundary, evaluate a Linux VM/WSL2 deployment with a supported OpenShell
runtime and verify host integration separately. See NVIDIA's
[installation requirements](https://docs.nvidia.com/openshell/latest/about/installation).

Completion means a bounded harness patch can be proposed, tested, activated, and
rolled back, with a retained history, while attempts to alter protected policy or
access unauthorized host files and services are rejected by controls outside the
agent. Platform limitations must be resolved or explicitly accommodated before
enabling autonomous activation.
