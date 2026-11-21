<#
Registers the weekly ingestion runs in Windows Task Scheduler on this laptop, where the real
database lives. Provided, not run by any setup step: run it yourself once, from the repo root.

    .\scripts\schedule_windows.ps1 -Python "C:\path\to\python.exe"

Planned times are UTC; Task Scheduler runs on local Brussels time, so the tasks use the winter
(CET, UTC+1) conversion:

    matchweek  Monday 23:30 UTC    -> Tuesday 00:30 Brussels
    news       Thursday 23:00 UTC  -> Friday 00:00 Brussels
    recap      Tuesday 05:00 UTC   -> Tuesday 06:00 Brussels   (python -m digests recap --publish)
    highlights Friday 05:00 UTC    -> Friday 06:00 Brussels    (python -m digests news --publish)
    freshness  an hour after each ingestion (python -m backend.observability.freshness --store):
               Tuesday 01:30 and Friday 01:00 Brussels; a failed check makes the task fail

The digest runs push the GitHub Pages site (gh-pages branch) with this laptop's git credentials.

During summer time (CEST, UTC+2, last Sunday of March to last Sunday of October) the same local
times are one hour earlier in UTC: Monday 22:30 UTC and Thursday 22:00 UTC. That still follows
Monday's last kickoff, and the Phase 5 digests (05:00 UTC) still run after it.

-StartWhenAvailable catches up a run missed while the laptop was off; -WakeToRun wakes it from
sleep; the tasks also run on battery. Docker Desktop must be running (start it at login). Each run
writes a JSON summary to logs\ (gitignored). Re-running this script overwrites all six tasks.
#>
param(
    [string]$Python = "python",
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

New-Item -ItemType Directory -Force (Join-Path $RepoRoot "logs") | Out-Null

$runs = @(
    @{ Name = "PL chatbot - ingest matchweek"; Args = "-m ingestion matchweek --summary logs\ingest-matchweek.json"; Day = "Tuesday"; At = "00:30" },
    @{ Name = "PL chatbot - ingest news";      Args = "-m ingestion news --summary logs\ingest-news.json";           Day = "Friday";  At = "00:00" },
    @{ Name = "PL chatbot - freshness (Tue)";  Args = "-m backend.observability.freshness --store";              Day = "Tuesday"; At = "01:30" },
    @{ Name = "PL chatbot - freshness (Fri)";  Args = "-m backend.observability.freshness --store";              Day = "Friday";  At = "01:00" },
    @{ Name = "PL chatbot - matchweek recap";  Args = "-m digests recap --publish --summary logs\digest-recap.json";  Day = "Tuesday"; At = "06:00" },
    @{ Name = "PL chatbot - news highlights";  Args = "-m digests news --publish --summary logs\digest-news.json";    Day = "Friday";  At = "06:00" }
)

foreach ($r in $runs) {
    $action = New-ScheduledTaskAction -Execute $Python `
        -Argument $r.Args `
        -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $r.Day -At $r.At
    # Task Scheduler's default only starts tasks on AC power; a laptop on battery would queue them.
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $r.Name -Action $action -Trigger $trigger `
        -Settings $settings -Description "python $($r.Args)" -Force | Out-Null
    Write-Host "Registered '$($r.Name)': $($r.Day) $($r.At) local time"
}
