@echo off
setlocal

REM Recomendado: usar um venv
REM python -m venv .venv
REM call .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller certifi

REM Constrói o executável
pyinstaller downvid.spec

echo.
echo Build finalizado. Veja a pasta .\dist\DownVid\
echo Execute ".\dist\DownVid\DownVid.exe"
echo.

endlocal