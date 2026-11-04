# Start RAG HTTP server -- single source of truth for RAG launch config.
#
# ASCII ONLY! (PowerShell 5.1 decodes BOM-less UTF-8 .ps1 as GBK -> parser errors)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_rag_server.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start_rag_server.ps1 -IdleTimeoutSec 0
#
# Config knobs (all overridable via parameters; env vars are consumed by rag_server_v2.py):
#   -IdleTimeoutSec   idle seconds before auto-shutdown (0 = never, i.e. resident)  [300]
#   -MemIdleSec       min idle seconds required before the memory-pressure branch   [60]
#   -MemMinMB         free-RAM floor in MB; below this + idle -> shut down          [400]
#   -WatchdogSec      watchdog poll interval in seconds                             [30]
param(
    [int]$IdleTimeoutSec = 300,
    [int]$MemIdleSec     = 60,
    [int]$MemMinMB       = 400,
    [int]$WatchdogSec    = 30
)

# --- Single source of truth -------------------------------------------------
$env:RAG_HOME   = 'D:\class\project-config\langchain-rag'
$env:RAG_PYTHON = 'D:\class\miniconda3\envs\ml_env\python.exe'

# LLM gateway: note .com (NOT .cn -- the .cn endpoint returns 500 get_channel_failed)
$env:RAG_AGNES_API_BASE = 'https://apihub.agnes-ai.com/v1'
$env:RAG_LLM_MODEL      = 'agnes-3.0-flash'

# Idle / memory-aware shutdown knobs
$env:RAG_IDLE_TIMEOUT_SEC = "$IdleTimeoutSec"
$env:RAG_MEM_IDLE_SEC     = "$MemIdleSec"
$env:RAG_MEM_MIN_MB       = "$MemMinMB"
$env:RAG_WATCHDOG_SEC     = "$WatchdogSec"

# Windows console encoding (emoji/print safety on zh-CN)
$env:PYTHONIOENCODING = 'utf-8'

Set-Location $env:RAG_HOME
& $env:RAG_PYTHON 'scripts\rag_server_v2.py'
