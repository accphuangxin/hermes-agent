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

# Launchers use {app} which Inno Setup expands to $INSTDIR at install time.
# For the staging copy we use a placeholder; Inno Setup rewrites them via
# the [Files] + AfterInstall hook below.
foreach ($cmd in @("hermes", "hermes-agent", "hermes-acp")) {
    Set-Content -Path "$BinDir\$cmd.cmd" `
        -Value "@echo off`r`n`"{app}\venv\Scripts\$cmd.exe`" %*`r`n" `
        -NoNewline
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

// Rewrite launcher .cmd files with the actual install path.
procedure FixLaunchers();
var
  appDir, cmdName, content: String;
  i: Integer;
  cmds: array[0..2] of String;
begin
  appDir := ExpandConstant('{app}');
  cmds[0] := 'hermes';
  cmds[1] := 'hermes-agent';
  cmds[2] := 'hermes-acp';
  for i := 0 to 2 do begin
    cmdName := cmds[i];
    content := '@echo off' + #13#10 +
               '"' + appDir + '\venv\Scripts\' + cmdName + '.exe" %*' + #13#10;
    SaveStringToFile(appDir + '\bin\' + cmdName + '.cmd', content, False);
  end;
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
    FixLaunchers();
    AddToPath();
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
