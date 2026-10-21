#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{7AD40C31-D6C5-45CE-AF99-FC90FA34F28E}
AppName=Azure Savings Plan Advisor
AppVersion={#AppVersion}
AppPublisher=jwgmpi-wolff
AppPublisherURL=https://github.com/jwgmpi-wolff/azure-savings-plan-advisor
DefaultDirName={localappdata}\Programs\Azure Savings Plan Advisor
DefaultGroupName=Azure Savings Plan Advisor
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=AzureSavingsPlanAdvisor-{#AppVersion}-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AzureSavingsPlanAdvisor.exe
CloseApplications=yes
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\AzureSavingsPlanAdvisor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\samples\hourly-costs.csv"; DestDir: "{app}\samples"; Flags: ignoreversion

[Icons]
Name: "{group}\Azure Savings Plan Advisor"; Filename: "{app}\AzureSavingsPlanAdvisor.exe"
Name: "{group}\Uninstall Azure Savings Plan Advisor"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Azure Savings Plan Advisor"; Filename: "{app}\AzureSavingsPlanAdvisor.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AzureSavingsPlanAdvisor.exe"; Description: "Launch Azure Savings Plan Advisor"; Flags: nowait postinstall skipifsilent
