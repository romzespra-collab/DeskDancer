@echo off
chcp 65001 >nul
rem build_exe.bat  v1.0.0 — сборка DeskDancer.exe
cd /d "%~dp0"

echo === [1/4] Проверка Python ===
python --version || (echo Python не найден & pause & exit /b 1)

echo === [2/4] Библиотеки ===
python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller || (echo Ошибка pip & pause & exit /b 1)

echo === [3/4] PyInstaller ===
python -m PyInstaller --noconfirm --clean deskdancer.spec || (echo Ошибка сборки & pause & exit /b 1)

echo === [4/4] Самопроверка ===
dist\DeskDancer.exe --selftest || (echo Самопроверка не прошла & pause & exit /b 1)

echo Готово: dist\DeskDancer.exe  (рядом положите папки characters и dances)
pause
