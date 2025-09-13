@echo off
setlocal

REM
REM
REM

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller certifi

REM
if exist ".\dist" (
    echo Removendo .\dist...
    rmdir /s /q ".\dist"
)
if exist ".\build" (
    echo Removendo .\build...
    rmdir /s /q ".\build"
)

REM Constrói o executável
python -m PyInstaller downvid.spec

echo.
echo Build finalizado. Veja a pasta .\dist\DownVid\
echo Execute ".\dist\DownVid\DownVid.exe"
echo.

REM
if not exist ".\dist" (
    echo Pasta .\dist nao encontrada. Abortando compressao.
) else (
    if exist ".\dist\DownVid-win64.zip" (
        echo Removendo .\dist\DownVid-win64.zip antigo...
        del /q ".\dist\DownVid-win64.zip"
    )
    echo Compactando .\dist para .\dist\DownVid.zip...
    powershell -NoLogo -NoProfile -Command "Compress-Archive -Path '.\dist\*' -DestinationPath '.\dist\DownVid-win64.zip' -Force"
    if %ERRORLEVEL% EQU 0 (
        echo Zip criado em .\dist\DownVid.zip
    ) else (
        echo Falha ao criar o zip.
    )
)

echo.

endlocal