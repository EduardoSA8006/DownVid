@echo off
setlocal

REM Recomendado: usar um venv
REM python -m venv .venv
REM call .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install PySide6 requests pyinstaller

REM Constrói o executável do instalador
pyinstaller downvid_installer.spec

echo.
echo Build finalizado. Veja a pasta .\dist\DownVid-Setup\
echo Execute ".\dist\DownVid-Setup\DownVid-Setup.exe"
echo.

endlocal