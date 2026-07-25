# RAG 自动搜索定时任务 - 直接配置版
# 使用方法：以管理员身份运行此脚本

$ErrorActionPreference = "Stop"

$TaskName = "RAG_AutoSearch"
$PythonPath = "D:\class\miniconda3\envs\ml_env\python.exe"
$ScriptPath = "D:\class\project-config\langchain-rag\scripts\auto_search_import.py"
$LogDir = "D:\class\project-config\langchain-rag\logs\task_scheduler"
$Query = "今日热点"

# 创建日志目录
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  RAG 自动搜索定时任务配置" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 删除已存在的任务
schtasks /delete /tn $TaskName /f 2>$null

# 创建每天上午 9:00 运行的任务
$Command = "& `"$PythonPath`" `"$ScriptPath`" `"$Query`""

schtasks /create /tn $TaskName /tr "$Command" /sc daily /st 09:00 /ru SYSTEM /f

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] 定时任务创建成功！" -ForegroundColor Green
    Write-Host "`n任务信息:" -ForegroundColor Yellow
    Write-Host "  任务名称: $TaskName" -ForegroundColor White
    Write-Host "  执行计划: 每天上午 9:00" -ForegroundColor White
    Write-Host "  搜索关键词: $Query" -ForegroundColor White
    Write-Host "  日志位置: $LogDir" -ForegroundColor White
    Write-Host "`n查看任务:" -ForegroundColor Cyan
    Write-Host "  schtasks /query /fo LIST /v | Select-String -Pattern '$TaskName' -Context 0,5" -ForegroundColor White
} else {
    Write-Host "[ERROR] 创建任务失败，请确保以管理员身份运行 PowerShell" -ForegroundColor Red
}
