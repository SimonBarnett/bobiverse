[CmdletBinding()]
param([switch], [string] = '', [string] = '', [string] = '')
& (Join-Path  'Invoke-JeevesMonitorCheck.ps1') -Check cmd_trace_stall -DryRun: -InstallRoot  -ChairHome  -DigestHome 
exit 
