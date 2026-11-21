@echo off
setlocal
cd /d "%~dp0.."
rem Double-click: open Codex repo root. Drag a different project folder onto this file to open it instead.
if "%~1"=="" (
    powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Start -Model qwen3:4b
) else (
    powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Start -Model qwen3:4b -ProjectPath "%~1"
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Launch failed. Run Setup-Local-Codex.cmd or check Ollama.
pause
exit /b %RC%
