; Inno Setup kurulum sihirbazı. Derleme: iscc /DSurum=0.9.0 paketleme\kurulum.iss
#ifndef Surum
  #define Surum "0.0.0"
#endif

[Setup]
AppId={{6F2C7B1E-4A8D-4C2E-9B51-5C1A7E3D9F20}
AppName=Streamchisel
AppVersion={#Surum}
AppVerName=Streamchisel {#Surum}
AppPublisher=Streamchisel
AppPublisherURL=https://streamchisel.store
AppSupportURL=https://streamchisel.store
DefaultDirName={autopf}\Streamchisel
DefaultGroupName=Streamchisel
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Streamchisel-Setup
SetupIconFile=..\assets\brand\streamchisel.ico
UninstallDisplayIcon={app}\Streamchisel.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"

[Files]
Source: "..\dist\Streamchisel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Streamchisel"; Filename: "{app}\Streamchisel.exe"
Name: "{group}\Streamchisel'i kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Streamchisel"; Filename: "{app}\Streamchisel.exe"; Tasks: masaustu

[Run]
Filename: "{app}\Streamchisel.exe"; Description: "Streamchisel'i başlat"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
