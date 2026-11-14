<#
Recheck this working tree after a pull. Reads public llama.cpp advisories and runs
Trivy locally with telemetry disabled. Does not upload source or enable a service.
Install the official Trivy Windows binary, verify its release checksum, then run:
  .\tools\security\scan.ps1 -Trivy C:\path\to\trivy.exe
Reports may contain sensitive secret matches: keep them in the ignored logs folder.
#>
param(
    [string]$Trivy = 'trivy',
    [string]$Python = '',
    [string]$Output = ''
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $Python) { $Python = Join-Path $root '.venv/Scripts/python.exe' }
if (-not $Output) { $Output = Join-Path $root ('logs/security-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$null = New-Item -ItemType Directory -Force -Path $Output
$Output = (Resolve-Path $Output).Path
$trivyCommand = (Get-Command $Trivy -ErrorAction Stop).Source
Push-Location $root
try {
    $advisories = Invoke-RestMethod -Uri 'https://api.github.com/repos/ggml-org/llama.cpp/security-advisories?per_page=100' -Headers @{'User-Agent'='Delta-security-review'}
    # Review fix ancestry and local patches; advisory dates alone do not prove applicability.
    ConvertTo-Json -InputObject @($advisories) -Depth 50 | Set-Content -Encoding utf8 (Join-Path $Output 'llama-advisories.json')
    & git -C third_party/llama.cpp rev-parse HEAD | Set-Content (Join-Path $Output 'llama-pin.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the llama.cpp pin.' }
    & $trivyCommand filesystem --scanners vuln,secret,misconfig --include-dev-deps --disable-telemetry --no-progress --timeout 15m `
        --skip-dirs '.git,.venv,logs,pr-zips,build*' --skip-files '*.gguf,*.exe,*.dll,*.lib,*.obj,*.pdb,*.zip' `
        --format json --output (Join-Path $Output 'repository.json') .
    if ($LASTEXITCODE -ne 0) { throw 'Trivy repository scan failed.' }
    $runtime = Join-Path $Output 'runtime'
    $null = New-Item -ItemType Directory -Force -Path $runtime
    & $Python -c 'import importlib.metadata as m; print("\n".join(sorted(d.metadata["Name"]+"=="+d.version for d in m.distributions())))' |
        Set-Content -Encoding ascii (Join-Path $runtime 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not inventory the installed Python environment.' }
    & $trivyCommand filesystem --scanners vuln --disable-telemetry --no-progress --format json `
        --output (Join-Path $Output 'runtime.json') $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Trivy runtime scan failed.' }
    foreach ($name in @('repository', 'runtime')) {
        $report = Get-Content -Raw (Join-Path $Output "$name.json") | ConvertFrom-Json
        $vulnerabilities = @($report.Results | ForEach-Object { $_.Vulnerabilities } | Where-Object { $null -ne $_ })
        $misconfigs = @($report.Results | ForEach-Object { $_.Misconfigurations } | Where-Object { $null -ne $_ })
        $secrets = @($report.Results | ForEach-Object { $_.Secrets } | Where-Object { $null -ne $_ })
        Write-Output "$name`: $($vulnerabilities.Count) vulnerability findings, $($misconfigs.Count) configuration findings, $($secrets.Count) secret findings"
    }
    Write-Output "Review reports in $Output. A completed scan is not a clean bill of health."
} finally {
    Pop-Location
}
