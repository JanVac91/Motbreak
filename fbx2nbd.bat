@echo off
rem Trascina uno o piu' file .fbx su questo file per convertirli in .nbd
rem (fbx2nbd.py deve stare nella stessa cartella). Serve Python 3: https://www.python.org
setlocal
if "%~1"=="" (
  echo Trascina un file .fbx su fbx2nbd.bat oppure usa:  py fbx2nbd.py modello.fbx modello.nbd
  pause
  exit /b 1
)
:loop
if "%~1"=="" goto end
echo.
py -3 "%~dp0fbx2nbd.py" "%~1" "%~dpn1.nbd" || python "%~dp0fbx2nbd.py" "%~1" "%~dpn1.nbd"
shift
goto loop
:end
echo.
pause
