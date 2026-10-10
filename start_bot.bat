@echo off
title eToro Autonomous Trading Bot
color 0A
cd /d "%~dp0"
echo ===================================================
echo   Starting eToro Autonomous Trading Bot on PC
echo ===================================================
echo.
python bot.py
pause
