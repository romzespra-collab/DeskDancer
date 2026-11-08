@echo off
chcp 65001 >nul
rem build_exe.bat  v1.1.0 — сборка DeskDancer.exe
cd /d "%~dp0"

echo === [1/5] Проверка Python ===
python --version || (echo Python не найден & pause & exit /b 1)

echo === [2/5] Библиотеки ===
python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller || (echo Ошибка pip & pause & exit /b 1)

echo === [3/5] PyInstaller ===
python -m PyInstaller --noconfirm --clean deskdancer.spec || (echo Ошибка сборки & pause & exit /b 1)

echo === [4/5] Девушки и танцы рядом с exe ===
xcopy /e /i /y characters dist\characters >nul
xcopy /e /i /y dances dist\dances >nul

echo === [5/5] Самопроверка ===
dist\DeskDancer.exe --selftest || (echo Самопроверка не прошла & pause & exit /b 1)

echo Готово: dist\DeskDancer.exe
pause
