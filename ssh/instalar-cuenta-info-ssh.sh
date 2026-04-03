#!/bin/bash
# Instalación completa: información de cuenta en cada conexión SSH (sin depender de TTY / VPN / HTTP Custom).
# Usa pam_exec en /etc/pam.d/sshd (session), válido cuando no hay shell interactivo.
# Ejecutar como root:  bash /ruta/instalar-cuenta-info-ssh.sh

set -euo pipefail

INSTALL_BIN="/usr/local/bin/cuenta_info.sh"
PAM_WRAPPER="/usr/local/bin/cuenta-info-ssh-pam.sh"
PROFILE_OLD="/etc/profile.d/cuenta-info-ssh.sh"
DB_FILE="/root/usuarios.db"
PAM_SSHD="/etc/pam.d/sshd"
PAM_LINE='session optional pam_exec.so stdout /usr/local/bin/cuenta-info-ssh-pam.sh'

die() { echo "Error: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "Ejecuta como root: sudo bash $0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_SCRIPT="${SCRIPT_DIR}/cuenta_info.sh"
SRC_PAM="${SCRIPT_DIR}/cuenta-info-ssh-pam.sh"
[[ -f "$SRC_SCRIPT" ]] || die "No se encuentra cuenta_info.sh junto a este instalador: $SRC_SCRIPT"
[[ -f "$SRC_PAM" ]] || die "No se encuentra cuenta-info-ssh-pam.sh junto a este instalador: $SRC_PAM"

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

echo "=== Copiando scripts ==="
install -m 0755 "$SRC_SCRIPT" "$INSTALL_BIN"
install -m 0755 "$SRC_PAM" "$PAM_WRAPPER"

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

echo "=== Eliminando profile.d antiguo (evitar duplicados con PAM) ==="
if [[ -f "$PROFILE_OLD" ]]; then
  rm -f "$PROFILE_OLD"
  echo "  Eliminado: $PROFILE_OLD"
else
  echo "  No había $PROFILE_OLD"
fi

echo "=== PAM ($PAM_SSHD) ==="
if [[ ! -f "$PAM_SSHD" ]]; then
  die "No existe $PAM_SSHD (¿OpenSSH con PAM instalado?)."
fi

if grep -qF 'cuenta-info-ssh-pam.sh' "$PAM_SSHD" 2>/dev/null; then
  echo "  La línea de cuenta-info ya está en $PAM_SSHD"
else
  printf '\n# Información de cuenta SSH (instalador cuenta-info)\n%s\n' "$PAM_LINE" >>"$PAM_SSHD"
  echo "  Añadida línea session pam_exec → $PAM_WRAPPER"
fi

if grep -qE '^[[:space:]]*UsePAM[[:space:]]+no' /etc/ssh/sshd_config 2>/dev/null; then
  echo ""
  echo "⚠️  En /etc/ssh/sshd_config está UsePAM no. PAM no se ejecutará hasta que pongas:"
  echo "    UsePAM yes"
  echo "    y reinicies sshd."
  echo ""
elif ! grep -qE '^[[:space:]]*UsePAM[[:space:]]+yes' /etc/ssh/sshd_config 2>/dev/null; then
  echo "⚠️  No se encontró UsePAM yes explícito en sshd_config. Por defecto en RHEL/Alma suele ser yes; si no ves el mensaje, añade UsePAM yes y reinicia sshd."
  echo ""
fi

echo "=== Reiniciando sshd ==="
if command -v systemctl >/dev/null 2>&1; then
  systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || echo "  No se pudo reiniciar con systemctl; reinicia sshd a mano."
else
  echo "  Reinicia el servicio SSH manualmente (service sshd restart)."
fi

echo ""
echo "=== Instalación terminada ==="
echo "  Script:        $INSTALL_BIN"
echo "  Wrapper PAM:   $PAM_WRAPPER"
echo "  Límites:       $DB_FILE"
echo "  PAM (sshd):    línea pam_exec con opción stdout"
echo ""
echo "Conéctate de nuevo por SSH (VPN / sin TTY): debería mostrarse el bloque al abrir sesión."
echo "Silenciar para un usuario: variable SSH_CUENTA_INFO_QUIET=1 (difficulta en PAM; mejor quitar la línea o usar cuentas sin mensaje)."
echo ""
