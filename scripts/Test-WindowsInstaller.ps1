param([string]$Installer)

$ErrorActionPreference = 'Stop'
if (-not $Installer) {
    $installers = @(Get-ChildItem -LiteralPath "$PSScriptRoot\..\dist\installer" -Filter '*-Setup-x64.exe')
    if ($installers.Count -ne 1) { throw 'Provide exactly one installer to test.' }
    $Installer = $installers[0].FullName
}
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$installDir = Join-Path $env:TEMP ("AdvisorInstallerTest-" + [guid]::NewGuid().ToString('N'))
$application = $null
try {
    $setup = Start-Process -FilePath $Installer -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`""
    ) -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer exited with code $($setup.ExitCode)." }
    $executable = Join-Path $installDir 'AzureSavingsPlanAdvisor.exe'
    if (-not (Test-Path -LiteralPath $executable)) { throw 'Installed application executable is missing.' }
    if (-not (Test-Path -LiteralPath "$installDir\samples\hourly-costs.csv")) { throw 'Sample CSV is missing.' }
    $application = Start-Process -FilePath $executable -PassThru
    $deadline = (Get-Date).AddSeconds(30)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $application.Refresh()
        if ($application.HasExited) { throw "Desktop app exited before opening its window: $($application.ExitCode)." }
        if ($application.MainWindowTitle -eq 'Azure Savings Plan Advisor') {
            $ready = $true
            break
        }
    }
    if (-not $ready) { throw 'Installed app did not open its desktop window within 30 seconds.' }
    if (-not $application.CloseMainWindow()) { throw 'Could not close installed desktop app.' }
    if (-not $application.WaitForExit(10000)) { throw 'Desktop app did not exit cleanly.' }
    $application.Dispose()
    $application = $null
    'Verified installed desktop app opens and closes successfully.'
} finally {
    if ($application -and -not $application.HasExited) {
        Stop-Process -Id $application.Id -Force
    }
    if ($application) {
        $application.Dispose()
        $application = $null
    }
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstallLog = "$installDir-uninstall.log"
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
            '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$uninstallLog`""
        ) -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) { throw "Uninstaller exited with code $($uninstall.ExitCode)." }
        # Inno Setup's temporary uninstaller helper can outlive its launcher.
        $deadline = (Get-Date).AddSeconds(30)
        while ((Test-Path -LiteralPath "$installDir\AzureSavingsPlanAdvisor.exe") -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
        }
        if (Test-Path -LiteralPath "$installDir\AzureSavingsPlanAdvisor.exe") { throw "Uninstall did not remove the application. See $uninstallLog." }
        Remove-Item -LiteralPath $uninstallLog
        'Verified app uninstall.'
    }
}
