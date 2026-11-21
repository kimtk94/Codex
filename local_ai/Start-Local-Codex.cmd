@echo off
setlocal
cd /d "%~dp0.."
rem Double-click: run persistent 16K Ollama custom model in saved Git repo. Drag a project folder to work there.
rem One-time prerequisite: Fix-Codex-4096.cmd.
if "%~1"=="" (
    powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Start -Model qwen3-codex16k
) else (
    powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Start -Model qwen3-codex16k -ProjectPath "%~1"
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Launch failed. Run Setup-Local-Codex.cmd or check Ollama.
pause
exit /b %RC%
