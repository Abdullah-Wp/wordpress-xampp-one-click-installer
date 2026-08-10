@echo off
setlocal
py -m pip install --upgrade pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name WordPress-XAMPP-Installer app.py
echo.
echo EXE: dist\WordPress-XAMPP-Installer.exe
pause
