@echo off
setlocal

REM Recomendado: usar um venv
REM python -m venv .venv
REM call .venv\Scripts\activate

REM
if exist ".\dist" (
    echo Removendo .\dist...
    rmdir /s /q ".\dist"
)
if exist ".\build" (
    echo Removendo .\build...
    rmdir /s /q ".\build"
)

python -m pip install --upgrade pip
python -m pip install PySide6 requests pyinstaller certifi pywin32

REM Constrói o executável do instalador
python -m PyInstaller downvid_installer.spec

echo.
echo Build finalizado. Veja a pasta .\dist\DownVid-Setup\
echo Execute ".\dist\DownVid-Setup\DownVid-Setup.exe"
echo.



endlocal