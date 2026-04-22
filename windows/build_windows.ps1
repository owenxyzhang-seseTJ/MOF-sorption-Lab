$ErrorActionPreference = "Stop"
$Version = "1.2"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Please install Python 3 for Windows."
}

if (-not (Test-Path ".venv-win")) {
    py -3 -m venv .venv-win
}

$Python = Join-Path $ProjectRoot ".venv-win\\Scripts\\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-desktop.txt
Write-Host "Building MOF Sorption Lab v$Version ..."
& $Python -m PyInstaller --noconfirm --clean windows\\MOFSorptionLab.spec

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\\Inno Setup 6\\ISCC.exe",
    "${env:ProgramFiles}\\Inno Setup 6\\ISCC.exe"
)

$ISCC = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($ISCC) {
    & $ISCC windows\\installer.iss
    Write-Host ""
    Write-Host "Installer created in dist-installer\\MOF-Sorption-Lab-Setup-$Version.exe"
} else {
    Write-Warning "Inno Setup was not found. Portable app folder is available in dist\\MOF Sorption Lab"
}
