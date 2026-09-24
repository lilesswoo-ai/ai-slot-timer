; 发条AI时段小组件 安装脚本 (Inno Setup 7)
[Setup]
AppName=发条AI时段小组件
AppVersion=1.1.2
AppPublisher=发条AI
AppId={{8F4E3D2C-1A2B-4C3D-9E8F-0A1B2C3D4E5F}
DefaultDirName={localappdata}\发条AI时段小组件
DefaultGroupName=发条AI时段小组件
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\app.ico
SetupIconFile=assets\deepseek_3.ico
OutputDir=.
OutputBaseFilename=ai-slot-timer-setup-1.1.2
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "autostart"; Description: "开机自动启动（登录 Windows 时自动运行）"; GroupDescription: "附加选项:"; Flags: unchecked

[Files]
Source: "发条AI时段小组件.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "short-notification-sound-for-meizu.mp3"; DestDir: "{app}"; Flags: ignoreversion
Source: "settings.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "启动小组件.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\发条AI时段小组件"; Filename: "{app}\发条AI时段小组件.exe"; IconFilename: "{app}\app.ico"; Tasks: desktopicon
Name: "{autoprograms}\发条AI时段小组件"; Filename: "{app}\发条AI时段小组件.exe"; IconFilename: "{app}\app.ico"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "发条AI时段小组件"; ValueData: """{app}\发条AI时段小组件.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\发条AI时段小组件.exe"; Description: "立即启动 发条AI时段小组件"; Flags: nowait postinstall skipifsilent