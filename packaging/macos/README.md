# macOS .pkg Installer

Builds a self-contained macOS `.pkg` installer for hermes-agent (Apple Silicon / arm64).

## What it does

1. Downloads **python-build-standalone** (CPython 3.11, arm64) and verifies its SHA-256.
2. Builds a source distribution (`sdist`) of the current repo with `uv build`.
3. Installs the sdist into an embedded venv at `build/macos-pkg/payload/usr/local/hermes/venv/`.
4. Writes thin shell launchers for `hermes`, `hermes-agent`, and `hermes-acp` into `build/macos-pkg/payload/usr/local/bin/`.
5. Runs `pkgbuild` to create a component package, then `productbuild` to wrap it with the installer UI (welcome / license / conclusion pages).

Final output: `dist/hermes-agent-<version>-arm64.pkg`

## Requirements (build machine)

- macOS (any version; Rosetta 2 is fine for arm64 builds on Intel)
- Xcode Command Line Tools: `xcode-select --install`
- [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Build

```bash
# From the repo root:
./packaging/macos/build-pkg.sh
```

With code-signing (required for Notarization / distribution outside your team):

```bash
DEVELOPER_ID_INSTALLER="Developer ID Installer: Your Name (TEAMID)" \
  ./packaging/macos/build-pkg.sh
```

## Installed layout

```
/usr/local/hermes/
  bin/python3          ← python-build-standalone runtime
  lib/...              ← stdlib
  venv/
    bin/hermes         ← actual entry point
    bin/hermes-agent
    bin/hermes-acp
    lib/python3.x/site-packages/   ← hermes-agent + bundled extras

/usr/local/bin/
  hermes               ← thin launcher (sets HERMES_MANAGED=pkg)
  hermes-agent
  hermes-acp
```

## Updating the bundled Python

1. Pick a new release from https://github.com/astral-sh/python-build-standalone/releases
2. Update `PBS_VERSION`, `PBS_PYTHON_VERSION`, and `PBS_SHA256` in `build-pkg.sh`.
3. The SHA-256 is in the `SHA256SUMS` asset of each release.

## Uninstall

```bash
sudo rm -rf /usr/local/hermes
sudo rm /usr/local/bin/hermes /usr/local/bin/hermes-agent /usr/local/bin/hermes-acp
```
