@echo off
chcp 65001 >nul
setlocal
echo Streamchisel kuruluyor...

rem Uygun Python'u bul: once py baslaticisi ile 3.12 / 3.11 / 3.10, sonra PATH'teki python
set "PY="
for %%V in (3.12 3.11 3.10 3.13) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo HATA: Python 3.10 veya ustu bulunamadi. Bilgisayarinizdaki Python cok eski.
  echo https://www.python.org/downloads/ adresinden Python 3.12 kurun,
  echo kurulumda "Add python.exe to PATH" kutusunu isaretleyin, sonra bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)
echo Kullanilan Python:
%PY% --version

if exist .venv (
  echo Eski .venv klasoru siliniyor...
  rmdir /s /q .venv
)
%PY% -m venv .venv || (pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (pause & exit /b 1)
if not exist bin\ffmpeg.exe (
  echo.
  echo UYARI: bin\ffmpeg.exe ve bin\ffprobe.exe bulunamadi.
  echo https://www.gyan.dev/ffmpeg/builds/ adresinden "ffmpeg-release-full" dosyasini indirin,
  echo icindeki bin klasorundeki ffmpeg.exe ve ffprobe.exe dosyalarini bu klasordeki bin\ icine koyun.
)
echo.
echo Kurulum bitti. Ornek kullanim icin README.md dosyasina bakin.
pause
