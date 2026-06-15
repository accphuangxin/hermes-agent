# packaging/windows/build-installer.ps1
# Builds a self-contained Windows installer (.exe) for hermes-agent.
# Uses Inno Setup 6 (must be installed before calling this script).
#
# Requirements:
#   - Python/uv (for building the sdist)
#   - Inno Setup 6 (ISCC.exe) in PATH or default install location
#   - python-build-standalone Windows tarball (downloaded by this script)
#
# Output:
#   dist\hermes-agent-<version>-windows-x64-setup.exe
#
# Usage:
#   .\packaging\windows\build-installer.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Move to repo root ─────────────────────────────────────────────────────────
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..")
Set-Location $RepoRoot

# ── Config ────────────────────────────────────────────────────────────────────
$VERSION = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "==> Building hermes-agent $VERSION (windows-x64)"

$PBS_VERSION       = "20260510"
$PBS_PYTHON_VER    = "3.11.15"
$PBS_TARBALL       = "cpython-${PBS_PYTHON_VER}+${PBS_VERSION}-x86_64-pc-windows-msvc-install_only.tar.gz"
$PBS_URL           = "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_VERSION}/${PBS_TARBALL}"
$PBS_SHA256        = "c0d6d9da1286640790c07f32c74516486c4ccd170a65952eebb3e125c34e6c67"

$BUILD_DIR         = "$RepoRoot\build\windows"
$STAGING_DIR       = "$BUILD_DIR\staging"   # mimics final C:\hermes layout
$DIST_DIR          = "$RepoRoot\dist"
$OUTPUT_EXE        = "$DIST_DIR\hermes-agent-${VERSION}-windows-x64-setup.exe"

# ── Locate ISCC ───────────────────────────────────────────────────────────────
$ISCC = $null
foreach ($candidate in @(
    "ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { $ISCC = $candidate; break }
    if (Test-Path $candidate) { $ISCC = $candidate; break }
}
if (-not $ISCC) {
    Write-Error "ISCC.exe not found. Install Inno Setup 6 first."
    exit 1
}
Write-Host "==> Using ISCC: $ISCC"

# ── Prepare directories ───────────────────────────────────────────────────────
Remove-Item -Recurse -Force $BUILD_DIR -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BUILD_DIR   | Out-Null
New-Item -ItemType Directory -Force -Path $STAGING_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $DIST_DIR    | Out-Null

# ── Step 1: Download & verify python-build-standalone ────────────────────────
Write-Host "==> Downloading Python $PBS_PYTHON_VER (windows x86_64)"
$tarball = "$BUILD_DIR\$PBS_TARBALL"
if (-not (Test-Path $tarball)) {
    curl.exe -fL --progress-bar -o $tarball $PBS_URL
} else {
    Write-Host "    (cached)"
}

Write-Host "==> Verifying SHA-256"
$actualHash = (Get-FileHash -Algorithm SHA256 $tarball).Hash.ToLower()
if ($actualHash -ne $PBS_SHA256.ToLower()) {
    Write-Error "SHA-256 mismatch!`n  expected: $PBS_SHA256`n  actual:   $actualHash"
    exit 1
}
Write-Host "    OK"

# ── Step 2: Extract Python into staging ───────────────────────────────────────
Write-Host "==> Extracting Python"
tar -xzf $tarball -C $STAGING_DIR --strip-components=1
$PythonExe = "$STAGING_DIR\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "python.exe not found after extraction. Check tarball layout."
    exit 1
}
& $PythonExe --version

# ── Step 3: Build sdist ───────────────────────────────────────────────────────
Write-Host "==> Building sdist"
$sdistDir = "$BUILD_DIR\sdist"
New-Item -ItemType Directory -Force -Path $sdistDir | Out-Null
uv build --sdist --out-dir $sdistDir .

$sdist = Get-ChildItem "$sdistDir\hermes*agent*.tar.gz" | Select-Object -First 1
if (-not $sdist) {
    Write-Error "sdist not found in $sdistDir"
    exit 1
}
Write-Host "==> sdist: $($sdist.FullName)"

# ── Step 4: Create venv and install ──────────────────────────────────────────
$VenvDir = "$STAGING_DIR\venv"
Write-Host "==> Creating venv at $VenvDir"
& $PythonExe -m venv $VenvDir

$Pip = "$VenvDir\Scripts\pip.exe"
Write-Host "==> Installing hermes-agent"
& $Pip install --quiet --upgrade pip wheel
& $Pip install --quiet "$($sdist.FullName)[cli,pty,mcp,acp,google,youtube,web,homeassistant,sms]"
& $Pip install --quiet "qrcode==7.4.2"

Write-Host "==> Verifying install"
& "$VenvDir\Scripts\hermes.exe" --version 2>&1 | Write-Host

# ── Step 5: Write launcher .cmd files ────────────────────────────────────────
$BinDir = "$STAGING_DIR\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# Launchers call the embedded python.exe directly (not hermes.exe) to avoid
# the "Unable to create process" error caused by pip-generated .exe launchers
# embedding the build-machine Python path.  Using python.exe -m ensures the
# correct interpreter is used regardless of where the package was installed.
$EntryPoints = @{
    "hermes"              = "hermes_cli.main:main"
    "hermes-agent"        = "run_agent:main"
    "hermes-acp"          = "acp_adapter.entry:main"
    "hermes-agent-manager" = "hermes_agent_manager.__main__:main"
    "ham"                 = "hermes_agent_manager.__main__:main"
    "hks"                 = "hermes_kanban_server.__main__:main"
    "hermes-kanban-server" = "hermes_kanban_server.__main__:main"
}
foreach ($name in $EntryPoints.Keys) {
    $module = $EntryPoints[$name] -replace ":.*", ""
    $func   = $EntryPoints[$name] -replace ".*:", ""
    # Use {app} placeholder — Inno Setup's FixLaunchers() replaces it with real install path.
    # venv\Scripts\python.exe auto-activates the venv so site-packages are on sys.path.
    $cmdContent = "@echo off`r`n`"{app}\venv\Scripts\python.exe`" -c `"import sys; from $module import $func; sys.exit($func())`" %*`r`n"
    Set-Content -Path "$BinDir\$name.cmd" -Value $cmdContent -NoNewline
}
Write-Host "==> Launchers written to $BinDir"

# ── Step 6: Generate Inno Setup script ───────────────────────────────────────
Write-Host "==> Generating Inno Setup script"
$NsiScript = @"
; hermes-agent Windows installer — generated by packaging/windows/build-installer.ps1
[Setup]
AppName=Hermes Agent
AppVersion=$VERSION
AppPublisher=Nous Research
AppPublisherURL=https://github.com/NousResearch/hermes-agent
DefaultDirName={autopf}\Hermes Agent
DefaultGroupName=Hermes Agent
OutputDir=$DIST_DIR
OutputBaseFilename=hermes-agent-${VERSION}-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Copy entire staging directory into {app}
Source: "$STAGING_DIR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Hermes Agent"; Filename: "{app}\venv\Scripts\hermes.exe"
Name: "{group}\Uninstall Hermes Agent"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  PathRegKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

// Relocate the venv: rewrite pyvenv.cfg and all Scripts/*.exe launchers so
// they point to the real install dir instead of the build-machine staging path.
// Also rewrites the .cmd launchers' {app} placeholder.
procedure RelocateVenv();
var
  appDir, pyExe, relocScript, tmpScript: String;
  ResultCode: Integer;
begin
  appDir := ExpandConstant('{app}');
  pyExe  := appDir + '\python.exe';

  // Inline Python relocation script — same logic as macOS postinstall
  relocScript :=
    'import os, sys' + #10 +
    'install_dir = sys.argv[1]' + #10 +
    'venv_dir = os.path.join(install_dir, "venv")' + #10 +
    'pyvenv_cfg = os.path.join(venv_dir, "pyvenv.cfg")' + #10 +
    'build_prefix = None' + #10 +
    'try:' + #10 +
    '    with open(pyvenv_cfg) as f:' + #10 +
    '        for line in f:' + #10 +
    '            if line.startswith("home = "):' + #10 +
    '                home = line.split("=",1)[1].strip()' + #10 +
    '                build_prefix = home.replace("\\\\Scripts","").replace("/Scripts","")' + #10 +
    '                break' + #10 +
    'except Exception as e:' + #10 +
    '    print("warn: pyvenv.cfg read failed:", e)' + #10 +
    'if not build_prefix or build_prefix == install_dir:' + #10 +
    '    print("paths already correct")' + #10 +
    '    sys.exit(0)' + #10 +
    'print("relocating:", build_prefix, "->", install_dir)' + #10 +
    'old = build_prefix.encode()' + #10 +
    'new = install_dir.encode()' + #10 +
    'scripts = os.path.join(venv_dir, "Scripts")' + #10 +
    'rewritten = 0' + #10 +
    'for name in os.listdir(scripts):' + #10 +
    '    p = os.path.join(scripts, name)' + #10 +
    '    if not os.path.isfile(p): continue' + #10 +
    '    try:' + #10 +
    '        data = open(p,"rb").read()' + #10 +
    '        if old not in data: continue' + #10 +
    '        open(p,"wb").write(data.replace(old,new))' + #10 +
    '        rewritten += 1' + #10 +
    '        print("  rewrote:", name)' + #10 +
    '    except Exception as e:' + #10 +
    '        print("  skip:", name, e)' + #10 +
    'for dirpath, _, files in os.walk(os.path.join(venv_dir,"Lib")):' + #10 +
    '    for name in files:' + #10 +
    '        if not name.endswith((".pth",".json","RECORD")): continue' + #10 +
    '        p = os.path.join(dirpath,name)' + #10 +
    '        try:' + #10 +
    '            data = open(p,"rb").read()' + #10 +
    '            if old not in data: continue' + #10 +
    '            open(p,"wb").write(data.replace(old,new))' + #10 +
    '            rewritten += 1' + #10 +
    '        except: pass' + #10 +
    'try:' + #10 +
    '    data = open(pyvenv_cfg,"rb").read()' + #10 +
    '    open(pyvenv_cfg,"wb").write(data.replace(old,new))' + #10 +
    'except: pass' + #10 +
    'print("done, rewrote", rewritten, "files")' + #10;

  tmpScript := appDir + '\relocate_venv.py';
  SaveStringToFile(tmpScript, relocScript, False);
  Exec(pyExe, '"' + tmpScript + '" "' + appDir + '"', appDir,
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  DeleteFile(tmpScript);
end;

// Rewrite .cmd launcher {app} placeholders with real install path.
procedure FixOneLauncher(appDir, cmdName: String);
var
  oldContent, newContent: String;
begin
  if FileExists(appDir + '\bin\' + cmdName + '.cmd') then begin
    LoadStringFromFile(appDir + '\bin\' + cmdName + '.cmd', oldContent);
    newContent := oldContent;
    StringChangeEx(newContent, '{app}', appDir, True);
    SaveStringToFile(appDir + '\bin\' + cmdName + '.cmd', newContent, False);
  end;
end;

procedure FixLaunchers();
var
  appDir: String;
begin
  appDir := ExpandConstant('{app}');
  FixOneLauncher(appDir, 'hermes');
  FixOneLauncher(appDir, 'hermes-agent');
  FixOneLauncher(appDir, 'hermes-acp');
  FixOneLauncher(appDir, 'hermes-agent-manager');
  FixOneLauncher(appDir, 'ham');
  FixOneLauncher(appDir, 'hks');
  FixOneLauncher(appDir, 'hermes-kanban-server');
end;

// Add {app}\bin to system PATH (skip if already present).
procedure AddToPath();
var
  pathVal, appBin: String;
begin
  appBin := ExpandConstant('{app}\bin');
  if not RegQueryStringValue(HKLM, PathRegKey, 'Path', pathVal) then
    pathVal := '';
  if Pos(LowerCase(appBin), LowerCase(pathVal)) = 0 then begin
    if (pathVal <> '') and (pathVal[Length(pathVal)] <> ';') then
      pathVal := pathVal + ';';
    pathVal := pathVal + appBin;
    RegWriteExpandStringValue(HKLM, PathRegKey, 'Path', pathVal);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    RelocateVenv();   // rewrite build-machine paths in venv Scripts/*.exe
    FixLaunchers();   // replace {app} in .cmd launchers
    AddToPath();      // add {app}\bin to system PATH
  end;
end;

// Remove PATH entry on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  pathVal, appBin, newPath: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    appBin := ExpandConstant('{app}\bin');
    if RegQueryStringValue(HKLM, PathRegKey, 'Path', pathVal) then begin
      newPath := pathVal;
      StringChangeEx(newPath, ';' + appBin, '', True);
      StringChangeEx(newPath, appBin + ';', '', True);
      StringChangeEx(newPath, appBin,       '', True);
      if newPath <> pathVal then
        RegWriteExpandStringValue(HKLM, PathRegKey, 'Path', newPath);
    end;
  end;
end;
"@

$InnoScript = "$BUILD_DIR\hermes-agent.iss"
Set-Content -Path $InnoScript -Value $NsiScript -Encoding UTF8
Write-Host "==> Script: $InnoScript"

# ── Step 7: Compile installer ─────────────────────────────────────────────────
Write-Host "==> Running ISCC"
& $ISCC $InnoScript
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC failed with exit code $LASTEXITCODE"
    exit 1
}

if (-not (Test-Path $OUTPUT_EXE)) {
    Write-Error "Expected installer not found: $OUTPUT_EXE"
    Get-ChildItem $DIST_DIR
    exit 1
}

$sizeMB = [math]::Round((Get-Item $OUTPUT_EXE).Length / 1MB, 1)
Write-Host ""
Write-Host "OK Installer built: $OUTPUT_EXE"
Write-Host "   Size: ${sizeMB} MB"
