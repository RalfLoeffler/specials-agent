param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $repoRoot "dist\excel-tools"
$buildRoot = Join-Path $repoRoot "build\excel-tools"

Write-Host "[INFO] Ensuring PyInstaller is available..."
& $Python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller installation failed. Check network/pip access, then retry."
}

& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is still unavailable after install."
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

Write-Host "[INFO] Building watchlist_excel_export.exe..."
& $Python @commonArgs `
    "--name" "watchlist_excel_export" `
    (Join-Path $repoRoot "src\watchlist_excel_export.py")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build watchlist_excel_export.exe"
}

Write-Host "[INFO] Building watchlist_excel_import.exe..."
& $Python @commonArgs `
    "--name" "watchlist_excel_import" `
    (Join-Path $repoRoot "src\watchlist_excel_import.py")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build watchlist_excel_import.exe"
}

$exportExe = Join-Path $distRoot "watchlist_excel_export.exe"
$importExe = Join-Path $distRoot "watchlist_excel_import.exe"
if (-not (Test-Path $exportExe) -or -not (Test-Path $importExe)) {
    throw "Build finished without producing the expected executable files."
}

Write-Host "[INFO] Build complete. Output:"
Write-Host "  $exportExe"
Write-Host "  $importExe"
