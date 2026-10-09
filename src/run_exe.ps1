# -*- coding: utf-8 -*-
# Launch the PACKAGED exe (not the source) with the same pinned data as the
# reference screenshot, so its client area can be pixel-diffed against the
# original. Keep this file ASCII-only - Windows PowerShell 5.1 reads BOM-less
# UTF-8 as ANSI and would mangle any non-ASCII path.
#
#   powershell -File run_exe.ps1 -Shot          # pin the reference frame (recommended)
#   powershell -File run_exe.ps1 -Scale 1 -Ip 172.19.80.1 -Adapter "vEthernet (WSL)"
param(
    [string]$Name = 'IPScaner',
    [string]$Scale = '',
    [string]$Ip = '',
    [string]$Adapter = '',
    [string]$ActiveIps = '',
    [string]$TipIndex = '',
    [switch]$Freeze,
    [switch]$Shot
)

$proj = Split-Path $PSScriptRoot -Parent
# Reorganised 2026-09-28: the exe now sits in the project root, no more dist\
# KEEP THIS FILE ASCII-ONLY (see the header note).
$exe  = Join-Path $proj ($Name + ".exe")
# Log goes to %TEMP% so the project folder stays clean (output/ was archived).
$log  = Join-Path $env:TEMP 'ipscaner_run_exe.log'

# -Shot has exactly the same meaning as in run_app.ps1, and the four pinned
# values must stay identical between the two scripts (see theme.SHOT_*).
# The source run and the packaged run MUST be captured with identical args,
# otherwise you are comparing two different frames, not replica accuracy.
if ($Shot) {
    $Scale = '1'
    $Ip = '172.19.80.1'
    $Adapter = 'vEthernet (WSL)'
    $TipIndex = '1'
    $ActiveIps = '172.19.80.1; 192.168.56.1; 192.168.5.65'
    $Freeze = $true
}

if (-not (Test-Path $exe)) { throw "missing exe: $exe" }

Get-Process -Name $Name -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 600

$parts = @()
if ($Scale     -ne '') { $parts += "--scale=$Scale" }
if ($Ip        -ne '') { $parts += "--ip=$Ip" }
if ($Adapter   -ne '') { $parts += "--adapter=$Adapter" }
if ($ActiveIps -ne '') { $parts += "--active-ips=$ActiveIps" }
if ($TipIndex  -ne '') { $parts += "--tip-index=$TipIndex" }
if ($Freeze)           { $parts += "--freeze" }
$parts = $parts | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
$argLine = ($parts -join ' ')

# WMI/CIM Create is used on purpose: Start-Process-spawned GUIs do not survive
# the tool-call boundary on this machine.
$cmd = "`"$exe`" $argLine"
$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
        -Arguments @{ CommandLine = $cmd; CurrentDirectory = $proj }
"exe=$exe args=$argLine ReturnValue=$($res.ReturnValue) ProcessId=$($res.ProcessId)" |
    Set-Content -Encoding UTF8 $log

Start-Sleep -Seconds 9

Get-Process $Name -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -ne '' } |
    ForEach-Object { "PID=$($_.Id) WS=$([math]::Round($_.WorkingSet64/1MB,1))MB TITLE=$($_.MainWindowTitle)" } |
    Add-Content -Encoding UTF8 $log

exit 0
