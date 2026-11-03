# Install / verify the RAG pi extensions (anti-drift).
#
# ASCII ONLY! (PowerShell 5.1 decodes BOM-less UTF-8 .ps1 as GBK)
#
# Uses .NET MD5 directly (Get-FileHash is not available on all PowerShell hosts).
#
# Deploys:
#   rag_extension/pi_rag_tool.ts     -> ~/.pi/agent/extensions/pi_rag_tool.ts
#   rag_extension/rag_autoreload.ts  -> ~/.pi/agent/extensions/rag_autoreload.ts
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_rag_extension.ps1          # deploy
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_rag_extension.ps1 -Check   # verify only
param([switch]$Check)

$ErrorActionPreference = 'Stop'

$srcDir = 'D:\class\project-config\langchain-rag\rag_extension'
$dstDir = Join-Path $env:USERPROFILE '.pi\agent\extensions'
$files  = @('pi_rag_tool.ts', 'rag_autoreload.ts')

function Get-Md5([string]$p) {
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($p)
        try {
            return ([BitConverter]::ToString($md5.ComputeHash($fs))).Replace('-', '')
        } finally {
            $fs.Close()
        }
    } finally {
        $md5.Dispose()
    }
}

if (-not (Test-Path $dstDir)) {
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
}

$failed = $false

foreach ($f in $files) {
    $src = Join-Path $srcDir $f
    $dst = Join-Path $dstDir $f

    if (-not (Test-Path $src)) {
        Write-Host "[FAIL] source not found: $src"
        $failed = $true
        continue
    }

    $srcHash = Get-Md5 $src
    if (Test-Path $dst) { $dstHash = Get-Md5 $dst } else { $dstHash = '(none)' }

    if ($Check) {
        if ($srcHash -eq $dstHash) {
            Write-Host "[OK] $f  in sync"
        } else {
            Write-Host "[FAIL] $f  OUT OF SYNC (run without -Check to deploy)"
            $failed = $true
        }
        continue
    }

    Copy-Item -Force $src $dst
    $newHash = Get-Md5 $dst
    if ($srcHash -ne $newHash) {
        Write-Host "[FAIL] $f  md5 mismatch after copy!"
        $failed = $true
    } else {
        Write-Host "[OK] $f  deployed"
    }
}

if ($failed) { exit 1 }
if ($Check) {
    Write-Host "All extensions in sync."
} else {
    Write-Host "Done. Run '/reload' in pi to load the extensions."
}
exit 0
