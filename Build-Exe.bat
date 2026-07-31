@echo off
REM ===========================================================================
REM  Build DISK / ADVANCED CLEANER TOOL into a standalone .exe  (Windows only)
REM  Double-click this on the Windows PC. Produces:  dist\Disk Cleaner.exe
REM ===========================================================================

title Build Disk Cleaner .exe
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
    echo   [X] Python not found. Install it from https://www.python.org/downloads/
    echo       and tick "Add python.exe to PATH".
    pause & exit /b 1
)

echo.
echo   [1/2] Installing build tools and dependencies...
%PY% -m pip install --user --upgrade pyinstaller python-fasthtml pywebview
if errorlevel 1 ( echo   [X] Install failed. & pause & exit /b 1 )

echo.
echo   [2/2] Building the .exe  (this takes a minute or two)...
%PY% -m PyInstaller --clean --noconfirm disk_cleaner.spec
if errorlevel 1 ( echo   [X] Build failed. See messages above. & pause & exit /b 1 )

echo.
echo   ============================================================
echo    DONE.  Your app is here:
echo        %~dp0dist\Disk Cleaner.exe
echo    You can copy that single .exe anywhere and double-click it.
echo   ============================================================
echo.
pause
