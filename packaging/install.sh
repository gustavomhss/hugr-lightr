#!/usr/bin/env sh
# install.sh — Unix-first lightr installer.

set -eu

# Owner delivery approval: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5945719224
# Qualified v0.1.1 assets; draft 400899741 awaits owner promotion.
# These download URLs become anonymous only after promotion.
RELEASES_URL='https://github.com/gmhelmold/hugr-lightr/releases/download'
VERSION='0.1.1'

BINARY_NAME="lightr"
DEFAULT_INSTALL_DIR="${HOME}/.local/bin"
FALLBACK_INSTALL_DIR="/usr/local/bin"

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

info() {
    printf '=> %s\n' "$1"
}

case "${RELEASES_URL}:${VERSION}" in
    *__PLACEHOLDER__*) die "no published release configured" ;;
esac

case "$(uname -s):$(uname -m)" in
    Darwin:arm64|Darwin:aarch64) OS_TAG="darwin"; ARCH_TAG="arm64" ;;
    Linux:x86_64|Linux:amd64) OS_TAG="linux"; ARCH_TAG="x86_64" ;;
    Darwin:*) die "unsupported platform: initial public releases support macOS arm64 only" ;;
    Linux:*) die "unsupported platform: initial public releases support Linux x86_64 only" ;;
    *) die "unsupported OS: $(uname -s)" ;;
esac

download() {
    destination="$1"
    url="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --output "$destination" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$destination" "$url"
    else
        die "neither curl nor wget found; cannot download"
    fi
}

TMP_DIR="$(mktemp -d)"
trap "rm -rf '${TMP_DIR}'" EXIT INT TERM

TARBALL="${BINARY_NAME}-${VERSION}-${OS_TAG}-${ARCH_TAG}.tar.gz"
if [ "$OS_TAG" = darwin ]; then
    # Signed name is preferred. Missing signing credentials produce only this
    # explicitly named unsigned alternative, never a falsely signed claim.
    if ! download "${TMP_DIR}/${TARBALL}" "${RELEASES_URL}/v${VERSION}/${TARBALL}"; then
        TARBALL="${BINARY_NAME}-${VERSION}-${OS_TAG}-${ARCH_TAG}-unsigned.tar.gz"
        download "${TMP_DIR}/${TARBALL}" "${RELEASES_URL}/v${VERSION}/${TARBALL}" \
            || die "download failed: ${RELEASES_URL}/v${VERSION}/${TARBALL}"
    fi
else
    download "${TMP_DIR}/${TARBALL}" "${RELEASES_URL}/v${VERSION}/${TARBALL}" \
        || die "download failed: ${RELEASES_URL}/v${VERSION}/${TARBALL}"
fi

CHECKSUM_FILE="${TARBALL}.sha256"
download "${TMP_DIR}/${CHECKSUM_FILE}" "${RELEASES_URL}/v${VERSION}/${CHECKSUM_FILE}" \
    || die "checksum download failed: ${RELEASES_URL}/v${VERSION}/${CHECKSUM_FILE}"

EXPECTED_HASH="$(awk 'NF == 2 { print $1; exit }' "${TMP_DIR}/${CHECKSUM_FILE}")"
EXPECTED_NAME="$(awk 'NF == 2 { print $2; exit }' "${TMP_DIR}/${CHECKSUM_FILE}")"
[ -n "${EXPECTED_HASH}" ] && [ "${EXPECTED_NAME}" = "${TARBALL}" ] \
    || die "invalid checksum entry for ${TARBALL}"

if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_HASH="$(sha256sum "${TMP_DIR}/${TARBALL}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
    ACTUAL_HASH="$(shasum -a 256 "${TMP_DIR}/${TARBALL}" | awk '{print $1}')"
else
    die "no sha256 utility found (sha256sum or shasum required)"
fi
[ "${ACTUAL_HASH}" = "${EXPECTED_HASH}" ] \
    || die "checksum mismatch — download may be corrupt or tampered"

tar -xzf "${TMP_DIR}/${TARBALL}" -C "${TMP_DIR}" || die "failed to extract tarball"
EXTRACTED_BIN="${TMP_DIR}/${BINARY_NAME}"
[ -f "${EXTRACTED_BIN}" ] || die "binary '${BINARY_NAME}' not found in tarball"
chmod +x "${EXTRACTED_BIN}"

if [ -d "${DEFAULT_INSTALL_DIR}" ] || mkdir -p "${DEFAULT_INSTALL_DIR}" 2>/dev/null; then
    INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
else
    printf "Cannot write to %s. Install to %s? (requires sudo) [y/N] " "$DEFAULT_INSTALL_DIR" "$FALLBACK_INSTALL_DIR"
    read -r ANSWER
    case "${ANSWER}" in
        y|Y) INSTALL_DIR="${FALLBACK_INSTALL_DIR}" ;;
        *) die "installation cancelled" ;;
    esac
fi

if [ "${INSTALL_DIR}" = "${FALLBACK_INSTALL_DIR}" ]; then
    sudo install -m 755 "${EXTRACTED_BIN}" "${INSTALL_DIR}/${BINARY_NAME}" || die "sudo install failed"
else
    install -m 755 "${EXTRACTED_BIN}" "${INSTALL_DIR}/${BINARY_NAME}" \
        || cp "${EXTRACTED_BIN}" "${INSTALL_DIR}/${BINARY_NAME}" || die "install failed"
fi

info "${BINARY_NAME} installed to ${INSTALL_DIR}/${BINARY_NAME}"
