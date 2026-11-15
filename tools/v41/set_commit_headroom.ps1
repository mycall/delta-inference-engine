# Read-only by default. Configure only after operator review; never reboots.
param([switch]$Apply, [switch]$RestoreAutomatic)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pagePath = 'C:\pagefile.sys'
$initialMiB = 131072
$maximumMiB = 163840
$memoryKey = 'HKLM:/SYSTEM/CurrentControlSet/Control/Session Manager/Memory Management'
$pagingFiles = @((Get-ItemProperty -LiteralPath $memoryKey -Name PagingFiles).PagingFiles)
$customPagingFile = "$pagePath $initialMiB $maximumMiB"
$computer = Get-CimInstance Win32_ComputerSystem
$settings = @(Get-CimInstance Win32_PageFileSetting)
$usage = @(Get-CimInstance Win32_PageFileUsage)
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$plan = [ordered]@{
    schema=1; action=if ($RestoreAutomatic) {'restore_automatic'} else {'configure_pagefile'}
    before=[ordered]@{automatic=[bool]$computer.AutomaticManagedPagefile;paging_files=$pagingFiles;settings=@($settings | Select-Object Name,InitialSize,MaximumSize);usage=@($usage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage)}
    proposed=[ordered]@{automatic=[bool]$RestoreAutomatic;name=$pagePath;initial_mib=$initialMiB;maximum_mib=$maximumMiB}
    elevated=$elevated;free_disk_bytes=(Get-PSDrive C).Free;reboot_performed=$false
    status='plan';restart_may_be_required=$true
}
$extra = if ($usage.Count -eq 1) { [Math]::Max([int64]0,([int64]$maximumMiB-[int64]$usage[0].AllocatedBaseSize)*1MB) } else { $null }
$plan.maximum_extra_disk_bytes = $extra
$plan.disk_reserve_ok = $null -ne $extra -and $plan.free_disk_bytes -ge ($extra+64GB)
if (-not $Apply) { $plan | ConvertTo-Json -Depth 7; return }
if (-not $elevated) { throw 'Run the reviewed script in an administrator PowerShell; no setting was changed' }
if ($usage.Count -ne 1 -or $usage[0].Name -ine $pagePath) { throw 'Unexpected page-file layout; inspect manually' }
if ($RestoreAutomatic) {
    if ($pagingFiles.Count -ne 1 -or $pagingFiles[0] -cne $customPagingFile) {
        throw 'Restore requires exactly the custom configuration this script proposes'
    }
} else {
    if (-not $computer.AutomaticManagedPagefile -or $settings.Count -or $pagingFiles.Count -ne 1 -or $pagingFiles[0] -cne '?:\pagefile.sys') { throw 'Page-file settings changed since review; inspect manually' }
    if (-not $plan.disk_reserve_ok) { throw 'Insufficient free disk for the maximum plus a 64-GiB reserve' }
}
$receipt = Join-Path $repoRoot ('logs/pagefile-change-'+[Guid]::NewGuid().ToString('N')+'.json')
function Save-Receipt { $plan | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $receipt -Encoding utf8 }
Save-Receipt
try {
    if ($RestoreAutomatic) {
        Set-ItemProperty -LiteralPath $memoryKey -Name PagingFiles -Value ([string[]]@('?:\pagefile.sys'))
    } else {
        # Win32_PageFileSetting documents this backing value, but this host's
        # WMI setter rejects the requested sizes. Write the approved startup
        # configuration directly; preserve the existing REG_MULTI_SZ type.
        if ((Get-Item -LiteralPath $memoryKey).GetValueKind('PagingFiles').ToString() -ne 'MultiString') { throw 'Unexpected registry value type' }
        Set-ItemProperty -LiteralPath $memoryKey -Name PagingFiles -Value ([string[]]@($customPagingFile))
    }
    $plan.status = 'configured'
    $plan.after = [ordered]@{automatic=[bool](Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile;paging_files=@((Get-ItemProperty -LiteralPath $memoryKey -Name PagingFiles).PagingFiles);settings=@(Get-CimInstance Win32_PageFileSetting | Select-Object Name,InitialSize,MaximumSize);usage=@(Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage)}
    $expected = if ($RestoreAutomatic) {'?:\pagefile.sys'} else {$customPagingFile}
    if ($plan.after.paging_files.Count -ne 1 -or $plan.after.paging_files[0] -cne $expected) { throw 'Startup registry readback differs' }
    if ($plan.after.automatic -ne [bool]$RestoreAutomatic) { throw 'Automatic-management readback differs' }
    if (-not $RestoreAutomatic -and ($plan.after.settings.Count -ne 1 -or $plan.after.settings[0].InitialSize -ne $initialMiB -or $plan.after.settings[0].MaximumSize -ne $maximumMiB)) { throw 'Custom-size readback differs' }
} catch {
    $plan.status = 'failed'; $plan.error = $_.Exception.Message
    if (-not $RestoreAutomatic) {
        # Return to the reviewed automatic state after an incomplete apply.
        Set-ItemProperty -LiteralPath $memoryKey -Name PagingFiles -Value ([string[]]$pagingFiles)
        $plan.returned_to_automatic = [bool](Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile
    }
    throw
} finally { Save-Receipt; Write-Output $receipt }
