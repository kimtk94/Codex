@echo off
setlocal
rem Read-only Git file inventory. No Ollama, Codex agent, GitHub auth, or network required.
set "REPO=%USERPROFILE%\Projects\Codex"
if not "%~1"=="" set "REPO=%~1"
if not exist "%REPO%\.git" (
  echo [Local AI] Git repository not found: "%REPO%"
  echo [Local AI] Pass a Git repository folder as the first argument.
  pause
  exit /b 2
)
where python.exe >nul 2>nul
if errorlevel 1 (
  echo [Local AI] Python not found. Install Python 3.10+ or add it to PATH.
  pause
  exit /b 1
)
python.exe "%~dp0repo_reader.py" --repo "%REPO%" --list
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo [Local AI] Git file inventory complete; NO model tools were called.
if not "%RC%"=="0" echo [Local AI] Repository read failed.
pause
exit /b %RC%
