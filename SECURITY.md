# Security

## Reporting a vulnerability

Please report anything that should not be public until it is fixed **privately**, through GitHub's private
vulnerability reporting: the repository's **Security** tab, **Report a vulnerability**
([direct link](https://github.com/musicurgy/delta-inference-engine/security/advisories/new)). Say what you found, how to reproduce it
(the request, the config keys involved, the version), and what an attacker gains. We answer there, fix it in
a release, and credit you in the advisory unless you ask us not to.

Ordinary hardening ideas and findings that are safe to discuss in public are welcome as an
[issue](https://github.com/musicurgy/delta-inference-engine/issues) or as a pull request, which we
review like our own code.

Supported: the latest release. Fixes go into the next release, not into older ones.

## What the server exposes

Delta runs a model on your PC and serves it over HTTP (`serve/server.py`, through `tools/v41/serve/serve_ds41.py`). Out of the box it is reachable from
this PC only. The details and every setting are in [docs/DETAILS.md](docs/DETAILS.md) ("From other devices",
"Host names", "Web pages without an API key", "Tools from MCP servers").

- **Where it listens.** `127.0.0.1` by default. `--host 0.0.0.0` (or `"host"` in `tools/v41/serve/ds41-windows.json`) opens it to
  your network.  From 0.94 the server refuses to start that way without an API key; on a network you trust,
  "allow_no_key": true in the config (or STRATA_ALLOW_NO_KEY=1) lets it run with a warning.
- **Image URLs.** A picture given as an http(s) URL is fetched by the server, so from 0.94 a URL whose host resolves
  to this PC or a private / link-local network address is refused (redirects are checked too, and so is the address
  each connection actually reaches, so a name that changes its answer cannot get around it);
  STRATA_IMAGE_FETCH_PRIVATE=1 allows it.  Hugging Face telemetry is off in every launcher and download script.
- **Pictures by file path.** A picture given as a path on this PC is read only up to 32 MiB.  From 0.94 a server that
  listens beyond this PC reads no picture by path, unless `"image_local_files": true` is in the run config; a
  picture sent as a data: URL works as before.
- **API key.** `"api_key"` in the run config (or `STRATA_API_KEY`) is required on `/v1/*` and on every endpoint
  that shows the model's state, requests or answers (`/status`, `/metrics`, `/settings`, `/mcp`, `/props`, `/slots`,
  `/api/requests`, `/config`) and on every `POST`. It is compared in constant time. Set one before you open the
  server to your network or put a tunnel in front of it.
- **Host check (DNS rebinding, 0.1.38).** Without an API key the server answers only requests whose `Host` is a name
  it knows (`localhost`, an IP address, the address it listens on and, when it listens beyond this PC, this PC's
  name). Others get 403. `"allowed_hosts"` adds names; with an API key the key decides.
- **Origin check (0.1.38).** Without an API key, a browser `POST` to `/v1/*` from another web site's page (it carries
  an `Origin` header) gets 403 unless that origin is the server's own page, `localhost`, an allowed host, or listed in
  `"trusted_origins"` / `"cors_origins"`. Changing settings (`/settings`, and `/config`: the few run config keys the
  page's Model settings may change - never the network, key, MCP or program keys), `/load` and `/unload` and the
  MCP tools are accepted only as JSON from the server's own page (or `"trusted_origins"`), so a page elsewhere cannot
  change settings or run tools.
- **CORS** is off unless `"cors_origins"` lists origins, and then only for `/v1/*`.
- **MCP tools** are opt-in: only the servers you put in the run config, only for requests from the server's own page
  that ask for them. They run with your user's rights, and the model decides when to call them.
- **The request monitor** (`/api-monitor`, which keeps the last prompts and answers in memory) is off unless
  `"api_monitor": true` is set.

Delta has not had an outside security audit yet.

## Local dependency and network checks

On Windows, `tools/security/scan.ps1 -Trivy C:\path\to\trivy.exe` downloads llama.cpp's published advisories,
scans the working tree (including development dependencies) with Trivy, and separately scans the installed Python
package versions. Install Trivy from its official release and verify the checksum first. The script disables Trivy
telemetry and writes reports under the ignored `logs/` directory; secret findings can contain sensitive text, so do
not publish raw reports. This is an on-demand check, not a background notification service.

`tools/security/install-advisory-monitor.ps1` installs the current user's
`Delta-Llama-Published-Advisories` Windows task, daily at 09:00 while that user
is logged on, with a missed run started when available. It runs without elevated
rights and writes public advisory snapshots, changes and pending review items to
`logs/advisory-monitor/`; `latest.json` is the last successful result. It fetches
only published llama.cpp advisories from GitHub, uploads no source, and performs
no patches or model/process recovery. Run the installer with `-Remove` to remove
the task. Polling failures retain the last successful snapshot and write a dated
error report. An unchanged later poll does not clear pending review items.

The local 2026-11-14 scheduled test exited 0 and observed 13 advisories. Its
second poll found no changes. All 13 records exactly matched the saved advisory
snapshot used by the dated source/patch review, and the local pin and disabled
RPC build were rechecked. `tools/security/advisory-reviewed.json` records those
exact content hashes; a later advisory update becomes pending again. These
acknowledgements describe the reviewed build and dispositions, including the RPC
exclusion, rather than declaring every build safe.

The [2026-11-14 local review](tools/security/review-2026-11-14.json) records the tested RTX Spark build, patches,
findings and limits. Native sources need their own advisory and patch review: a clean package scan does not cover
the custom ARM64 PyTorch wheel or prove the C++ engine safe. ZAP's passive scan checks web responses; outbound-code
review and process connection monitoring address different questions.

The vendor security fixes and helper requirement updates are kept in `tools/xolotl/ggml/xolotl-ggml.patch`, so the
normal vendor checkout step reapplies them. The converter helpers now require Python 3.11+; the tested CLIP conversion
is recorded in the review, not a claim that every legacy converter/model combination was exercised. Pillow's
vulnerable Python 3.10 fallback is no longer installed. Existing 3.10 environments must upgrade Python and reinstall
their dependencies to remove an old Pillow wheel; changing the requirements file alone does not uninstall it.
