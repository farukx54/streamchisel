@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Streamchisel
if not exist .venv\Scripts\python.exe (
  echo Once kur.bat ile kurulum yapin.
  pause
  exit /b 1
)
echo Streamchisel aciliyor... Bu pencereyi kapatirsaniz program da kapanir.
.venv\Scripts\python -m klipo_app
pause
