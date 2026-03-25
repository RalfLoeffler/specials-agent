param(
    [string]$Python
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $repoRoot "dist\excel-tools"
$buildRoot = Join-Path $repoRoot "build\excel-tools"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($Python)) {
    if (Test-Path $venvPython) {
        $Python = $venvPython
    }
    else {
        $Python = "python"
    }
}

Write-Host "[INFO] Using Python: $Python"
Write-Host "[INFO] Installing build and runtime dependencies..."
& $Python -m pip install -r (Join-Path $repoRoot "requirements.txt") pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Check network/pip access, then retry."
}

& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is still unavailable after install."
}

& $Python -c "import openpyxl, yaml"
if ($LASTEXITCODE -ne 0) {
    throw "Required Python packages are unavailable after install. Ensure requirements.txt can be installed, then retry."
}

Write-Host "[INFO] Cleaning previous build output..."
if (Test-Path $distRoot) {
    Remove-Item -Recurse -Force $distRoot
}
if (Test-Path $buildRoot) {
    Remove-Item -Recurse -Force $buildRoot
}

$commonArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--distpath", $distRoot,
    "--workpath", $buildRoot,
    "--specpath", $buildRoot
)

Write-Host "[INFO] Building export_watchlist_to_excel.exe..."
& $Python @commonArgs `
    "--name" "export_watchlist_to_excel" `
    (Join-Path $repoRoot "src\export_watchlist_to_excel.py")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build export_watchlist_to_excel.exe"
}

Write-Host "[INFO] Building import_watchlist_from_excel.exe..."
& $Python @commonArgs `
    "--name" "import_watchlist_from_excel" `
    (Join-Path $repoRoot "src\import_watchlist_from_excel.py")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build import_watchlist_from_excel.exe"
}

$exportExe = Join-Path $distRoot "export_watchlist_to_excel.exe"
$importExe = Join-Path $distRoot "import_watchlist_from_excel.exe"
if (-not (Test-Path $exportExe) -or -not (Test-Path $importExe)) {
    throw "Build finished without producing the expected executable files."
}

Write-Host "[INFO] Build complete. Output:"
Write-Host "  $exportExe"
Write-Host "  $importExe"
