@echo off
rem Convenience only. If Bitdefender blocks .bat files, run the PyInstaller
rem command below directly from the app\ folder instead (see README.md).
cd /d "%~dp0"
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --noconsole --name YANBF-CBC --hidden-import gltflib --hidden-import PIL.Image --hidden-import argparse --add-data "..\banner.blend;." yanbf_cbc.py
if errorlevel 1 exit /b 1
copy /y dist\YANBF-CBC.exe ..\YANBF-CBC.exe
