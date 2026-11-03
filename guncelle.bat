@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Streamchisel guncelleniyor (yeni kutuphaneler kuruluyor)...
if not exist .venv\Scripts\python.exe (
  echo Once kur.bat ile kurulum yapin.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install -r requirements.txt || (pause & exit /b 1)
echo.
echo Guncelleme tamam. Streamchisel.bat ile programi acabilirsiniz.
pause
