param(
    [ValidateSet('Install', 'Start', 'Stop', 'Status', 'Uninstall')]
    [string]$Action = 'Status'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Jalankan skrip ini di Windows.' }

$taskName = 'KeySound'
$python = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$script = Join-Path $PSScriptRoot 'keysound.py'
$logDir = Join-Path $env:LOCALAPPDATA 'KeySound'
$log = Join-Path $logDir 'service.log'
$arguments = '-u "{0}" --log-file "{1}"' -f $script, $log
$task = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($task) {
    $actions = @($task.Actions)
    if ($actions.Count -ne 1 -or $actions[0].Execute -ne $python -or $actions[0].Arguments -ne $arguments) {
        throw 'Task KeySound sudah ada dengan jalur berbeda. Periksa Task Scheduler; skrip tidak akan menimpanya.'
    }
}

switch ($Action) {
    'Install' {
        if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $script)) {
            throw 'Buat .venv dan pasang requirements.txt dari folder proyek terlebih dahulu.'
        }
        if ($task) { throw 'Task sudah terpasang. Gunakan Start, Stop, Status, atau Uninstall.' }
        if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
            throw 'Port 8765 sedang dipakai. Hentikan instance manual terlebih dahulu; tidak ada proses yang dimatikan otomatis.'
        }
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $taskAction = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $PSScriptRoot
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'KeySound local keyboard audio, interactive user session.' | Out-Null
        Start-ScheduledTask -TaskName $taskName -TaskPath '\'
        Write-Output 'Task terpasang dan diminta mulai. Gunakan Status untuk memeriksa dashboard; autostart berlaku setelah login.'
    }
    'Start' {
        if (-not $task) { throw 'Task belum dipasang. Jalankan Install terlebih dahulu.' }
        Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
        Start-ScheduledTask -TaskName $taskName -TaskPath '\'
        Write-Output 'Start diminta. Periksa Status atau dashboard.'
    }
    'Stop' {
        if (-not $task) { throw 'Task belum dipasang; instance terminal dihentikan dengan Ctrl+C.' }
        Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
        Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
        Write-Output 'Task dihentikan dan dinonaktifkan, termasuk autostart. Gunakan Start untuk mengaktifkannya lagi.'
    }
    'Uninstall' {
        if ($task) {
            Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
            Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
            Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false
        }
        Write-Output 'Task dihapus. Konfigurasi dan audio pengguna tidak dihapus.'
    }
    'Status' {
        if ($task) {
            $task | Select-Object TaskName, State
            Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\' | Select-Object LastRunTime, LastTaskResult
        } else { Write-Output 'Task belum terpasang.' }
        try {
            $state = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/state' -TimeoutSec 3
            $state.status | ConvertTo-Json -Depth 3
        } catch { Write-Output ('Dashboard belum terhubung. Periksa log: ' + $log) }
    }
}
