# Build TeleTurbo to standalone .exe
# Run: powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"

# Install deps if missing
pip install -r requirements.txt

# Clean previous builds
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Build with PyInstaller
pyinstaller --onefile --windowed --name TeleTurbo `
    --hidden-import telethon `
    --hidden-import cryptg `
    --hidden-import PIL `
    --hidden-import PIL._tkinter_finder `
    --collect-all telethon `
    --collect-all cryptg `
    --collect-all PIL `
    main.py

Write-Host ""
Write-Host "Build complete! Executable at: dist\TeleTurbo.exe"
Write-Host "Note: Copy TeleTurbo.exe to an empty folder before running."
Write-Host "      It will create sessions/ and config.json on first use."
