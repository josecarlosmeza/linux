#!/usr/bin/env bash
# Instalación mínima en servidor: descarga install.py desde GitHub y ejecuta
# --install-from-github (el ZIP completo de udppy/ se obtiene desde el mismo repo).
#
# Variables de entorno:
#   UDPPY_DEST     Directorio de instalación (por defecto: /opt/udppy)
#   UDPPY_RAW_BASE URL del directorio udppy/ en raw.githubusercontent.com
#
# Ejemplos:
#   sudo ./bootstrap.sh
#   sudo ./bootstrap.sh --install-systemd --enable-systemd
#   sudo ./bootstrap.sh --install-systemd --enable-systemd --systemd-dns 8.8.8.8:53
#   UDPPY_DEST="$HOME/udppy" ./bootstrap.sh
#
# Sin git en el servidor; solo bash, curl o wget, y python3.

set -euo pipefail

UDPPY_RAW_BASE="${UDPPY_RAW_BASE:-https://raw.githubusercontent.com/josecarlosmeza/linux/main/udppy}"
UDPPY_DEST="${UDPPY_DEST:-/opt/udppy}"

usage() {
  cat <<EOF
Uso: $0 [argumentos que se pasan a install.py]

Descarga install.py desde GitHub y ejecuta --install-from-github (ZIP de udppy/).

Variables de entorno:
  UDPPY_DEST     Directorio destino (por defecto: /opt/udppy)
  UDPPY_RAW_BASE URL del directorio udppy/ en raw.githubusercontent.com

Ejemplos:
  sudo $0
  sudo $0 --install-systemd --enable-systemd
  UDPPY_DEST="\$HOME/udppy" $0
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

_download() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    echo "bootstrap.sh: se requiere curl o wget." >&2
    exit 1
  fi
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "bootstrap.sh: se requiere python3 en PATH." >&2
  exit 1
fi

TMPDIR="${TMPDIR:-/tmp}"
WORKDIR=$(mktemp -d "${TMPDIR%/}/udppy-bootstrap.XXXXXX")
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

INSTALL_PY="${WORKDIR}/install.py"
_download "${UDPPY_RAW_BASE%/}/install.py" "$INSTALL_PY"

exec python3 "$INSTALL_PY" --install-from-github --dest "$UDPPY_DEST" "$@"
