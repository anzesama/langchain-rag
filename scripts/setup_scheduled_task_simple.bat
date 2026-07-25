@echo off
chcp 65001 >nul
echo ==========================================
echo   RAG 自动搜索定时任务配置 (简单版)
echo ==========================================
echo.

REM 配置参数
set PYTHON_PATH=D:\class\miniconda3\envs\ml_env\python.exe
set SCRIPT_PATH=D:\class\project-config\langchain-rag\scripts\auto_search_import.py
set LOG_DIR=D:\class\project-config\langchain-rag\logs\task_scheduler
set TASK_NAME=RAG_AutoSearch
set QUERY=今日热点

REM 创建日志目录
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [INFO] 检查 Python 路径...
if not exist "%PYTHON_PATH%" (
    echo [ERROR] Python 路径不存在: %PYTHON_PATH%
    pause
    exit /b 1
)

echo [OK] Python 路径存在: %PYTHON_PATH%
echo.

echo 请选择计划类型:
echo 1. 每天运行（推荐）
echo 2. 每周运行
echo 3. 每月运行
echo.
set /p CHOICE="请输入选项 (1-3): "

if "%CHOICE%"=="1" (
    echo [OK] 计划：每天上午 9:00
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
    schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" \"%QUERY%\"" /sc daily /st 09:00 /ru SYSTEM /f >nul 2>&1
) else if "%CHOICE%"=="2" (
    echo [OK] 计划：每周一上午 9:00
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
    schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" \"%QUERY%\"" /sc weekly /d MON /st 09:00 /ru SYSTEM /f >nul 2>&1
) else if "%CHOICE%"=="3" (
    echo [OK] 计划：每月 1 日上午 9:00
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
    schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" \"%QUERY%\"" /sc monthly /m jan /mo first /st 09:00 /ru SYSTEM /f >nul 2>&1
) else (
    echo [ERROR] 无效选项
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   定时任务创建完成！
echo ==========================================
echo.
echo 任务名称：%TASK_NAME%
echo 执行时间：每天上午 9:00
echo 日志位置：%LOG_DIR%
echo.
echo 查看任务列表:
echo   schtasks /query /fo LIST | findstr "%TASK_NAME%"
echo.
echo 手动执行任务:
echo   schtasks /run /tn "%TASK_NAME%"
echo.
pause
