<#
Registers the weekly ingestion runs in Windows Task Scheduler on this laptop, where the real
database lives. Provided, not run by any setup step: run it yourself once, from the repo root.

    .\scripts\schedule_windows.ps1 -Python "C:\path\to\python.exe"

Planned times are UTC; Task Scheduler runs on local Brussels time, so the tasks use the winter
(CET, UTC+1) conversion:

    matchweek  Monday 23:30 UTC    -> Tuesday 00:30 Brussels
    news       Thursday 23:00 UTC  -> Friday 00:00 Brussels

During summer time (CEST, UTC+2, last Sunday of March to last Sunday of October) the same local
times are one hour earlier in UTC: Monday 22:30 UTC and Thursday 22:00 UTC. That still follows
Monday's last kickoff, and the Phase 5 digests (05:00 UTC) still run after it.

-StartWhenAvailable catches up a run missed while the laptop was off; -WakeToRun wakes it from
sleep. Each run writes a JSON summary to logs\ (gitignored).
#>
param(
    [string]$Python = "python",
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

New-Item -ItemType Directory -Force (Join-Path $RepoRoot "logs") | Out-Null

$runs = @(
    @{ Name = "PL chatbot - ingest matchweek"; Mode = "matchweek"; Day = "Tuesday"; At = "00:30" },
    @{ Name = "PL chatbot - ingest news";      Mode = "news";      Day = "Friday";  At = "00:00" }
)

foreach ($r in $runs) {
    $action = New-ScheduledTaskAction -Execute $Python `
        -Argument "-m ingestion $($r.Mode) --summary logs\ingest-$($r.Mode).json" `
        -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $r.Day -At $r.At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun
    Register-ScheduledTask -TaskName $r.Name -Action $action -Trigger $trigger `
        -Settings $settings -Description "python -m ingestion $($r.Mode)" -Force | Out-Null
    Write-Host "Registered '$($r.Name)': $($r.Day) $($r.At) local time"
}
