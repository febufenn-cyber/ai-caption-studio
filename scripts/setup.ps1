$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Invoke-Bootstrap([string]$Version) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        return $false
    }

    & py $Version scripts/bootstrap.py
    return $LASTEXITCODE -eq 0
}

if (Invoke-Bootstrap "-3.12") { exit 0 }
if (Invoke-Bootstrap "-3.11") { exit 0 }
if (Invoke-Bootstrap "-3.10") { exit 0 }

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python scripts/bootstrap.py
    exit $LASTEXITCODE
}

Write-Error "Python 3.10+ is required. Install Python and rerun scripts/setup.ps1"
