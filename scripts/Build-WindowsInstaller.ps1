param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '0.5.0',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $iscc = if ($compiler) { $compiler.Source } else { "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    if (-not (Test-Path -LiteralPath $iscc)) { throw 'Install Inno Setup 6 before building the Windows installer.' }
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name AzureSavingsPlanAdvisor --collect-all jsonschema_specifications `
        --copy-metadata jsonschema .\desktop_app.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop application packaging failed.' }
    & $iscc "/DAppVersion=$Version" .\installer\advisor.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    $installer = ".\dist\installer\AzureSavingsPlanAdvisor-$Version-Setup-x64.exe"
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $installer -Leaf)" | Set-Content -LiteralPath .\dist\installer\SHA256SUMS.txt -Encoding ascii
} finally {
    Pop-Location
}
