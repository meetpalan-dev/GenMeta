@echo off
title GenMeta Build
echo ============================================================
echo  GenMeta v20.1 — Build Script
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Installing / updating dependencies...
python -m pip install --upgrade pyinstaller flask pywebview pillow transformers torch imagehash
echo.

echo [2/3] Running PyInstaller...
python -m PyInstaller genmeta.spec --clean --noconfirm
echo.

if not exist "dist\GenMeta\GenMeta.exe" (
  echo ERROR: Build failed — dist\GenMeta\GenMeta.exe not found.
  pause
  exit /b 1
)

echo [3/3] Build complete!
echo.
echo Output:  dist\GenMeta\
echo.
echo Next step: Open installer.iss in Inno Setup and press Ctrl+F9
echo            to create the installer at installer_output\GenMeta_Setup_v20.1.exe
echo.
pause
