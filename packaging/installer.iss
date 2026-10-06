; Inno Setup script for Stress & Aero.  Compile with:  iscc /DAppVersion=0.1.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6E0D3B7A-5C2B-4D61-9A8E-5A1F2C3D4E5F}
AppName=Stress & Aero
AppVersion={#AppVersion}
AppPublisher=Stress & Aero team
DefaultDirName={localappdata}\Programs\StressAero
DefaultGroupName=Stress & Aero
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=StressAero-Setup-{#AppVersion}
SetupIconFile=assets\stressaero.ico
UninstallDisplayIcon={app}\StressAero.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "assocork"; Description: "Open OpenRocket .ork files with Stress && Aero"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "..\dist\StressAero\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Stress & Aero"; Filename: "{app}\StressAero.exe"
Name: "{group}\Stress & Aero (demo rocket)"; Filename: "{app}\StressAero.exe"; Parameters: "--demo"
Name: "{group}\Uninstall Stress & Aero"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Stress & Aero"; Filename: "{app}\StressAero.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.saproj"; ValueType: string; ValueName: ""; ValueData: "StressAero.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\StressAero.Project"; ValueType: string; ValueName: ""; ValueData: "Stress & Aero project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\StressAero.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\StressAero.exe,0"
Root: HKA; Subkey: "Software\Classes\StressAero.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\StressAero.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.ork\OpenWithProgids"; ValueType: string; ValueName: "StressAero.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocork

[Run]
Filename: "{app}\StressAero.exe"; Parameters: "--demo"; Description: "Launch Stress & Aero with the demo rocket"; Flags: nowait postinstall skipifsilent
