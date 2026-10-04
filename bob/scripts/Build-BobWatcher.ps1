#Requires -Version 5.1
[CmdletBinding()]
param([string]$RepoRoot='',[Parameter(Mandatory=$true)][string]$OutDir,[string]$Python='')
$ErrorActionPreference='Stop'
if(-not $RepoRoot){$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path}
if(-not $Python){$Python=(Get-Command python.exe -ErrorAction Stop).Source}
$src=Join-Path $RepoRoot 'bob\agentwatcher\watch_agent_health.py'
$work=Join-Path $OutDir 'watcher-build'; if(Test-Path $work){Remove-Item $work -Recurse -Force}
$dist=Join-Path $work 'dist'; New-Item -ItemType Directory -Force $dist | Out-Null
$args=@('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','Watch-AgentHealth','--distpath',$dist,'--workpath',(Join-Path $work 'build'),'--specpath',$work,$src)
$log=Join-Path $work 'pyinstaller.log'; $p=Start-Process $Python -ArgumentList (($args|%{if([string]$_ -match '[\s"]'){ '"'+([string]$_).Replace('"','\"')+'"'}else{[string]$_}})-join ' ') -WorkingDirectory $RepoRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $log -RedirectStandardError $log
$exe=Join-Path $dist 'Watch-AgentHealth.exe'; if($p.ExitCode -ne 0 -or -not(Test-Path $exe)){Get-Content $log -Tail 30; throw "watcher build failed $($p.ExitCode)"}; $exe
