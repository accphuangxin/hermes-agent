#!/usr/bin/env bash
# packaging/macos/build-pkg.sh
# Builds a self-contained macOS .pkg installer for hermes-agent.
# Auto-detects the build machine architecture (arm64 or x86_64).
#
# Requirements:
#   - macOS, Xcode Command Line Tools (pkgbuild, productbuild), uv, curl, tar, shasum
#
# Output: dist/hermes-agent-<version>-macos-<arch>.pkg
#
# Signing (optional):
#   Set DEVELOPER_ID_INSTALLER to your "Developer ID Installer: ..." cert name.
#
# Usage:
#   ./packaging/macos/build-pkg.sh
#   DEVELOPER_ID_INSTALLER="Developer ID Installer: Acme Inc (XXXXXXXX)" \
#     ./packaging/macos/build-pkg.sh

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

# ── Config ────────────────────────────────────────────────────────────────────
VERSION=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

# Auto-detect architecture
HOST_ARCH="$(uname -m)"   # arm64 or x86_64
if [[ "${HOST_ARCH}" == "arm64" ]]; then
    ARCH="arm64"
    PBS_PBS_TRIPLE="aarch64-apple-darwin"
    PBS_SHA256="03bcedae9b19a48888d7dc8ba064f73f6efaaf2b13f6a8e1a1bcc062df13e855"
elif [[ "${HOST_ARCH}" == "x86_64" ]]; then
    ARCH="x86_64"
    PBS_PBS_TRIPLE="x86_64-apple-darwin"
    PBS_SHA256="5e388e3db8b59c8487ddd1423330b90fc7f0c6ef7eadec945441a180d0dd4bc4"
else
    echo "error: unsupported architecture: ${HOST_ARCH}" >&2
    exit 1
fi

INSTALL_PREFIX="/usr/local/hermes"
BIN_DIR="/usr/local/bin"

# python-build-standalone release to embed.
PBS_VERSION="20260510"
PBS_PYTHON_VERSION="3.11.15"
PBS_TARBALL="cpython-${PBS_PYTHON_VERSION}+${PBS_VERSION}-${PBS_PBS_TRIPLE}-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_VERSION}/${PBS_TARBALL}"

BUILD_DIR="$(pwd)/build/macos-pkg"
PAYLOAD_DIR="${BUILD_DIR}/payload"
PKG_COMPONENT="${BUILD_DIR}/hermes-agent-${VERSION}-macos-${ARCH}.pkg"
DIST_DIR="$(pwd)/dist"
OUTPUT_PKG="${DIST_DIR}/hermes-agent-${VERSION}-macos-${ARCH}.pkg"

echo "==> Building hermes-agent ${VERSION} pkg (macos-${ARCH})"

# ── Sanity checks ─────────────────────────────────────────────────────────────
if ! command -v pkgbuild &>/dev/null; then
    echo "error: pkgbuild not found. Install Xcode Command Line Tools." >&2
    exit 1
fi
if ! command -v uv &>/dev/null; then
    echo "error: uv not found. Install from https://docs.astral.sh/uv/" >&2
    exit 1
fi

# ── Clean build dir ───────────────────────────────────────────────────────────
rm -rf "${BUILD_DIR}"
mkdir -p "${PAYLOAD_DIR}${INSTALL_PREFIX}"
mkdir -p "${PAYLOAD_DIR}${BIN_DIR}"
mkdir -p "${DIST_DIR}"

# ── Step 1: Download python-build-standalone ──────────────────────────────────
echo "==> Downloading Python ${PBS_PYTHON_VERSION} (${ARCH})"
PBS_CACHE="${BUILD_DIR}/${PBS_TARBALL}"
if [[ ! -f "${PBS_CACHE}" ]]; then
    curl -fL --progress-bar -o "${PBS_CACHE}" "${PBS_URL}"
fi

# Checksum verification
echo "==> Verifying Python tarball checksum"
ACTUAL_SHA=$(shasum -a 256 "${PBS_CACHE}" | awk '{print $1}')
if [[ "${ACTUAL_SHA}" != "${PBS_SHA256}" ]]; then
    echo "error: SHA-256 mismatch for ${PBS_TARBALL}" >&2
    echo "  expected: ${PBS_SHA256}" >&2
    echo "  actual:   ${ACTUAL_SHA}" >&2
    echo "Update PBS_SHA256 in build-pkg.sh with the value above if you intentionally bumped PBS_VERSION." >&2
    exit 1
fi

echo "==> Extracting Python"
tar -xzf "${PBS_CACHE}" -C "${PAYLOAD_DIR}${INSTALL_PREFIX}" --strip-components=1
PYTHON_BIN="${PAYLOAD_DIR}${INSTALL_PREFIX}/bin/python3"

# ── Step 2: Build sdist, create venv and install on the build machine ────────
# The venv is created here (not in postinstall) so the package is fully
# self-contained — the target machine needs neither Python nor internet access.
# postinstall rewrites the build-machine absolute paths to /usr/local/hermes.
echo "==> Building hermes-agent sdist"
uv build --sdist --out-dir "${BUILD_DIR}/sdist" .

SDIST_BUILT="${BUILD_DIR}/sdist/hermes_agent-${VERSION}.tar.gz"
if [[ ! -f "${SDIST_BUILT}" ]]; then
    SDIST_BUILT="${BUILD_DIR}/sdist/hermes-agent-${VERSION}.tar.gz"
fi
if [[ ! -f "${SDIST_BUILT}" ]]; then
    echo "error: sdist not found in ${BUILD_DIR}/sdist" >&2
    ls "${BUILD_DIR}/sdist" >&2
    exit 1
fi

echo "==> Creating venv and installing hermes-agent (downloads packages once)"
"${PYTHON_BIN}" -m venv "${PAYLOAD_DIR}${INSTALL_PREFIX}/venv"
VENV_PIP="${PAYLOAD_DIR}${INSTALL_PREFIX}/venv/bin/pip"
"${VENV_PIP}" install --quiet --upgrade pip wheel
# Install core + non-lazy extras.
# Heavy optional backends (anthropic, voice, messaging, modal, etc.) are
# intentionally excluded — they lazy-install at first use via lazy_deps.py.
"${VENV_PIP}" install --quiet \
    "${SDIST_BUILT}[cli,pty,mcp,acp,google,youtube,web,homeassistant,sms]"

# ── Step 3: Write launcher scripts into payload ───────────────────────────────
echo "==> Writing launcher scripts"

# Common launcher preamble: finds the site-packages dir dynamically
# so the path doesn't break if the bundled Python is ever bumped.
LAUNCHER_PREAMBLE='#!/bin/bash
# Launcher installed by hermes-agent.pkg
HERMES_HOME="/usr/local/hermes"
# Resolve site-packages without hard-coding the Python minor version
_SP=$("${HERMES_HOME}/venv/bin/python3" -c "import sysconfig; print(sysconfig.get_path(\"purelib\"))" 2>/dev/null)
if [[ -d "${_SP}/skills" ]]; then
  export HERMES_BUNDLED_SKILLS="${_SP}/skills"
fi
if [[ -d "${_SP}/optional-skills" ]]; then
  export HERMES_OPTIONAL_SKILLS="${_SP}/optional-skills"
fi'

printf '%s\nexec "${HERMES_HOME}/venv/bin/hermes" "$@"\n' "${LAUNCHER_PREAMBLE}" \
    > "${PAYLOAD_DIR}${BIN_DIR}/hermes"
chmod +x "${PAYLOAD_DIR}${BIN_DIR}/hermes"

printf '%s\nexec "${HERMES_HOME}/venv/bin/hermes-agent" "$@"\n' "${LAUNCHER_PREAMBLE}" \
    > "${PAYLOAD_DIR}${BIN_DIR}/hermes-agent"
chmod +x "${PAYLOAD_DIR}${BIN_DIR}/hermes-agent"

printf '%s\nexec "${HERMES_HOME}/venv/bin/hermes-acp" "$@"\n' "${LAUNCHER_PREAMBLE}" \
    > "${PAYLOAD_DIR}${BIN_DIR}/hermes-acp"
chmod +x "${PAYLOAD_DIR}${BIN_DIR}/hermes-acp"

# ── Step 4: Build component pkg ───────────────────────────────────────────────
echo "==> Building component package"
pkgbuild \
    --root "${PAYLOAD_DIR}" \
    --identifier "ai.nousresearch.hermes-agent" \
    --version "${VERSION}" \
    --scripts "$(pwd)/packaging/macos/scripts" \
    "${PKG_COMPONENT}"

# ── Step 5: Assemble distribution pkg with UI ─────────────────────────────────
echo "==> Assembling distribution package"

# Substitute the versioned component package name into a temporary distribution XML.
PKG_COMPONENT_BASENAME="$(basename "${PKG_COMPONENT}")"
DIST_XML_TMP="${BUILD_DIR}/distribution.xml"
sed "s|@COMPONENT_PKG_NAME@|${PKG_COMPONENT_BASENAME}|g" \
    "$(pwd)/packaging/macos/distribution.xml" > "${DIST_XML_TMP}"

SIGN_ARGS=()
if [[ -n "${DEVELOPER_ID_INSTALLER:-}" ]]; then
    SIGN_ARGS=(--sign "${DEVELOPER_ID_INSTALLER}")
    echo "    Signing with: ${DEVELOPER_ID_INSTALLER}"
fi

productbuild \
    --distribution "${DIST_XML_TMP}" \
    --resources "$(pwd)/packaging/macos/resources" \
    --package-path "${BUILD_DIR}" \
    ${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"} \
    "${OUTPUT_PKG}"

echo ""
echo "✓ Package built: ${OUTPUT_PKG}"
echo "  Size: $(du -sh "${OUTPUT_PKG}" | cut -f1)"
if [[ -n "${DEVELOPER_ID_INSTALLER:-}" ]]; then
    echo "  Signed: yes"
    pkgutil --check-signature "${OUTPUT_PKG}" 2>/dev/null | grep "Status:" || true
else
    echo "  Signed: no (set DEVELOPER_ID_INSTALLER to sign)"
fi
