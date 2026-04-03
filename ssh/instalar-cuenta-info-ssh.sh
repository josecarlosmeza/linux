#!/bin/bash
# Instalación completa: información de cuenta al conectar por SSH (AlmaLinux / RHEL y derivados).
# Ejecutar como root:  bash /ruta/instalar-cuenta-info-ssh.sh

set -euo pipefail

INSTALL_BIN="/usr/local/bin/cuenta_info.sh"
PROFILE_SNIPPET="/etc/profile.d/cuenta-info-ssh.sh"
DB_FILE="/root/usuarios.db"

die() { echo "Error: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "Ejecuta como root: sudo bash $0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_SCRIPT="${SCRIPT_DIR}/cuenta_info.sh"
[[ -f "$SRC_SCRIPT" ]] || die "No se encuentra cuenta_info.sh junto a este instalador: $SRC_SCRIPT"

_pkg_install() {
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y "$@"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "$@"
  else
    die "No se encontró dnf ni yum. Instala manualmente: shadow-utils procps-ng"
  fi
}

echo "=== Dependencias (chage, pgrep) ==="
for pkg in shadow-utils procps-ng; do
  if rpm -q "$pkg" >/dev/null 2>&1; then
    echo "  OK: $pkg"
  else
    echo "  Instalando: $pkg"
    _pkg_install "$pkg"
  fi
done

echo "=== Copiando script a $INSTALL_BIN ==="
install -m 0755 "$SRC_SCRIPT" "$INSTALL_BIN"

echo "=== Base de datos de límites $DB_FILE ==="
if [[ ! -f "$DB_FILE" ]]; then
  umask 022
  cat >"$DB_FILE" <<'EOF'
# Formato por línea: usuario limite_sesiones
# Ejemplo: redlibre 10
EOF
  echo "  Creado archivo vacío con comentarios (añade usuarios con tu panel o a mano)."
else
  echo "  Ya existe; no se modifica."
fi

echo "=== Perfil de login $PROFILE_SNIPPET ==="
umask 022
cat >"$PROFILE_SNIPPET" <<'PROFILE_EOF'
# Cuenta SSH — instalado por instalar-cuenta-info-ssh.sh
# Se muestra en: sesión SSH (SSH_CONNECTION) o consola con TTY. Silenciar: SSH_CUENTA_INFO_QUIET=1
if [ -x /usr/local/bin/cuenta_info.sh ] && [ "$(id -u)" -ne 0 ]; then
  if [ "${SSH_CUENTA_INFO_QUIET:-0}" = "1" ]; then
    :
  elif [ -n "${SSH_CONNECTION:-}" ] || [ -t 1 ]; then
    /usr/local/bin/cuenta_info.sh
  fi
fi
PROFILE_EOF
chmod 644 "$PROFILE_SNIPPET"

echo ""
echo "=== Instalación terminada ==="
echo "  Script:     $INSTALL_BIN"
echo "  Profile.d:  $PROFILE_SNIPPET"
echo "  Límites:    $DB_FILE"
echo ""
echo "Prueba en el servidor (usuario normal con shell de login):"
echo "  bash -l -c true"
echo "O conecta por SSH y revisa el mensaje tras el banner."
echo "Usuarios con shell /bin/false o /sbin/nologin: no ejecutan profile.d;"
echo "  usa shell de login (p. ej. /bin/bash) para ver el mensaje, o un ForceCommand/PAM según tu panel."
echo ""
