#Requires -Version 5.1
[CmdletBinding()]
param([string]$RepoRoot='',[Parameter(Mandatory=$true)][string]$OutDir,[string]$Python='')
$ErrorActionPreference='Stop'
if(-not $RepoRoot){$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path}
if(-not $Python){$Python=(Get-Command python.exe -ErrorAction Stop).Source}
$src=Join-Path $RepoRoot 'bob\agentwatcher\watch_agent_health.py'
$work=Join-Path $OutDir 'watcher-build'; if(Test-Path $work){Remove-Item $work -Recurse -Force}
$dist=Join-Path $work 'dist'; New-Item -ItemType Directory -Force $dist | Out-Null
$argList=@('-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--name','Watch-AgentHealth','--distpath',$dist,'--workpath',(Join-Path $work 'build'),'--specpath',$work,$src)
$stdout=Join-Path $work 'pyinstaller.stdout.log'
$stderr=Join-Path $work 'pyinstaller.stderr.log'
$p=Start-Process -FilePath $Python -ArgumentList $argList -WorkingDirectory $RepoRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$exe=Join-Path $dist 'Watch-AgentHealth.exe'
if($p.ExitCode -ne 0 -or -not(Test-Path $exe)){
  Write-Host '--- stdout ---'; if(Test-Path $stdout){ Get-Content $stdout -Tail 40 }
  Write-Host '--- stderr ---'; if(Test-Path $stderr){ Get-Content $stderr -Tail 40 }
  throw "watcher build failed $($p.ExitCode)"
}
Write-Host "INFO built $exe"
$exe
