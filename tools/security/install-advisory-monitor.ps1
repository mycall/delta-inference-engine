param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskName = 'Delta-Llama-Published-Advisories'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    return
}
$python = Join-Path $repoRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the local virtual environment first' }
$script = Join-Path $PSScriptRoot 'watch_advisories.py'
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $script + '"') -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Fetch public llama.cpp advisories into local logs/advisory-monitor. No source upload, patching, or model restart.'
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Select-Object TaskName,State
