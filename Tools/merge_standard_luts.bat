@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0merge_standard_luts.py"
  exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0merge_standard_luts.py"
  exit /b
)
echo Python 3 was not found. Install Python 3, then run this launcher again.
pause
exit /b 1
