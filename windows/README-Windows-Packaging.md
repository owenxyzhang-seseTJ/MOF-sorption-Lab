# Windows Packaging

This folder contains the build configuration for producing a Windows desktop app and installer.

## What it builds

1. A desktop app executable using PyInstaller
2. A Windows installer `setup.exe` using Inno Setup
3. Windows executable metadata such as icon, product version, and uninstall information

## Files

- `MOFSorptionLab.spec`: PyInstaller build definition
- `installer.iss`: Inno Setup script
- `build_windows.ps1`: one-command build script
- `version_info.txt`: Windows EXE version metadata

## How to build on Windows

1. Install Python 3
2. Install Inno Setup 6
3. Open PowerShell in the project root
4. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build_windows.ps1
```

## Output

- Portable app: `dist\MOF Sorption Lab\`
- Installer: `dist-installer\MOF-Sorption-Lab-Setup-1.2.exe`

## Installer experience in v1.2

- Simplified Chinese installer interface
- Desktop shortcut created automatically
- Start menu entry for the app and a dedicated uninstall shortcut
- Version number `1.2` shown in installer metadata
- Add/Remove Programs shows app name, icon, publisher, and uninstall entry
