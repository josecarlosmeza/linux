#!/bin/bash
# Limitador OpenSSH + Guardián de DB — Entorno AlmaLinux / RHEL
# Requiere: root, OpenSSH con UsePAM, systemd

set -e
if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta este script como root: sudo bash $0"
    exit 1
fi

echo "--- 🛠️  INSTALACIÓN DEL LIMITADOR OPENSSH + GUARDIÁN DE DB (AlmaLinux/RHEL) ---"
echo ""

# --- CONFIGURACIÓN DE RUTAS ---
# /root: coincide con tu instalación (usuarios.db, usuarios-limitador.db en ~)
LIMITADOR_DIR="/root"
DB_MASTER="$LIMITADOR_DIR/usuarios.db"
DB_LIMITER="$LIMITADOR_DIR/usuarios-limitador.db"
DB_BACKUP="$LIMITADOR_DIR/usuarios.backup"

LIMITER_PATH="/usr/bin/check_ssh_limits.sh"
SCR_PATH="/usr/local/bin/db-guardian.sh"
GHOST_CLEANUP_PATH="/usr/local/bin/sshd-ghost-cleanup.sh"
SVC_PATH="/etc/systemd/system/db-guardian.service"
PAM_SSHD_FILE="/etc/pam.d/sshd"
CRON_GHOST="/etc/cron.d/sshd-ghost-cleanup"

# --- 1. DIRECTORIO Y BASE DE DATOS MAESTRA ---
echo "--- 1. Configurando $LIMITADOR_DIR y base de datos de usuarios ---"
# /root existe; si usas otro dir, créalo antes
[ -d "$LIMITADOR_DIR" ] || mkdir -p "$LIMITADOR_DIR"
if [ ! -f "$DB_MASTER" ]; then
    tee "$DB_MASTER" > /dev/null <<EOF
# USUARIO LIMITE
* 3
REDLIBRE 10
EOF
    echo "✅ Archivo de límites creado."
else
    echo "✅ El archivo de límites ya existe."
fi
chmod 644 "$DB_MASTER"

# Asegurar que existan limitador y backup para el guardián
touch "$DB_LIMITER" "$DB_BACKUP"
cp "$DB_MASTER" "$DB_LIMITER" 2>/dev/null || true
chmod 644 "$DB_LIMITER"

# --- 2. CREAR SCRIPT DEL GUARDIÁN ---
echo "--- 2. Creando Guardián de DB en $SCR_PATH ---"
tee "$SCR_PATH" > /dev/null <<GUARDIAN_EOF
#!/bin/bash
# Script: Guardian de Sincronización y Recuperación
# Master: $DB_MASTER (Editable)
# Limiter: $DB_LIMITER (Solo Lectura para PAM)

while true; do
    if [ -f "$DB_MASTER" ]; then
        lineas=\$(wc -l < "$DB_MASTER")

        # Si el maestro tiene contenido (2+ líneas), sincronizamos
        if [ "\$lineas" -gt 1 ]; then
            cp "$DB_MASTER" "$DB_LIMITER"
            cp "$DB_MASTER" "$DB_BACKUP"
            chmod 644 "$DB_LIMITER"

        # Si el maestro se vació o corrompió (0-1 líneas), restauramos del backup
        elif [ "\$lineas" -le 1 ]; then
            if [ -f "$DB_BACKUP" ]; then
                cp "$DB_BACKUP" "$DB_MASTER"
                cp "$DB_BACKUP" "$DB_LIMITER"
                logger "DB-GUARDIAN: Se detectó borrado en Master. Restaurando datos..."
            fi
        fi
    fi
    sleep 5
done
GUARDIAN_EOF

chmod +x "$SCR_PATH"
echo "✅ Guardián de DB instalado."

# --- 3. CREAR SERVICIO SYSTEMD DEL GUARDIÁN ---
echo "--- 3. Creando servicio db-guardian ---"
tee "$SVC_PATH" > /dev/null <<SVC_EOF
[Unit]
Description=Guardian de Base de Datos RedLibre
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash $SCR_PATH
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVC_EOF

systemctl daemon-reload
systemctl enable db-guardian.service
systemctl restart db-guardian.service
echo "✅ Servicio db-guardian activado y en ejecución."

# --- 4. CREAR SCRIPT LIMITADOR (PAM usa DB_LIMITER) ---
echo "--- 4. Creando Script Limitador en $LIMITER_PATH ---"
tee "$LIMITER_PATH" > /dev/null <<LIMITER_EOF
#!/bin/bash
# Limitador SSH por PAM — lee \$DB_SOURCE
DB_SOURCE="$DB_LIMITER"
USER="\$PAM_USER"

# Debug (ver con: journalctl -t ssh_limiter -f)
logger -t ssh_limiter "CHECK user=\$USER"

# 1. EXCEPCIÓN ROOT
if [ "\$USER" = "root" ] || [ -z "\$USER" ]; then
    exit 0
fi

# 2. DB LEGIBLE
if [ ! -r "\$DB_SOURCE" ]; then
    logger -t ssh_limiter "WARN: \$DB_SOURCE no readable; permitiendo."
    exit 0
fi

# 3. LÍMITE DEL USUARIO (usuario N, luego * N, por defecto 3)
MAX_ALLOWED=\$(grep "^\$USER " "\$DB_SOURCE" 2>/dev/null | awk '{print \$2}')
if [ -z "\$MAX_ALLOWED" ]; then
    MAX_ALLOWED=\$(grep "^\* " "\$DB_SOURCE" 2>/dev/null | awk '{print \$2}')
fi
MAX_ALLOWED=\${MAX_ALLOWED:-3}

# 4. SESIONES: mismo criterio que infousers (ps). pgrep «sshd:» + ss en Alma 9/OpenSSH reciente suele descontar frente al panel.
CURRENT_SESSIONS=\$(ps -u "\$USER" 2>/dev/null | grep -c '[s]shd' || true)
CURRENT_SESSIONS=\${CURRENT_SESSIONS:-0}

# 5. BLOQUEO: denegar si supera el límite (-gt alinea con la sesión que ya aparece en ps durante PAM)
if [ "\$CURRENT_SESSIONS" -gt "\$MAX_ALLOWED" ]; then
    logger -t ssh_limiter "DENIED: \$USER límite=\$MAX_ALLOWED activas_ps=\$CURRENT_SESSIONS"
    exit 1
fi

exit 0
LIMITER_EOF

chmod +x "$LIMITER_PATH"
echo "✅ Script limitador instalado (lee de $DB_LIMITER, protege root)."

# --- 4b. LIMPIADOR DE SESIONES FANTASMA (sshd: sin TCP ESTABLISHED) ---
echo "--- 4b. Limpiador de sesiones fantasma ---"
tee "$GHOST_CLEANUP_PATH" > /dev/null <<'GHOST_EOF'
#!/bin/bash
# Mata sesiones sshd: huérfanas (sin TCP ESTABLISHED).
# No debe matar el daemon en escucha: en OpenSSH reciente el master aparece como "sshd: ... [listener]"
# y no tiene líneas ESTABLISHED en ss, solo LISTEN.
command -v ss &>/dev/null || exit 0
killed=0
for pid in $(pgrep -f "sshd:" 2>/dev/null); do
  if ss -tlnp 2>/dev/null | grep -qE "pid=${pid}[,)]"; then
    continue
  fi
  if ! ss -tnp state established 2>/dev/null | grep -qE "pid=${pid}[,)]"; then
    kill -TERM "$pid" 2>/dev/null && { logger -t ssh_ghost_cleanup "Killed ghost sshd PID $pid"; killed=$((killed+1)); }
  fi
done
[ "$killed" -gt 0 ] && logger -t ssh_ghost_cleanup "Cleaned $killed ghost session(s)"
GHOST_EOF
chmod +x "$GHOST_CLEANUP_PATH"
echo "SHELL=/bin/bash" > "$CRON_GHOST"
echo "*/5 * * * * root $GHOST_CLEANUP_PATH" >> "$CRON_GHOST"
chmod 644 "$CRON_GHOST"
$GHOST_CLEANUP_PATH 2>/dev/null || true
echo "✅ Limpiador instalado; cron cada 5 min."

# --- 5. SELinux: restaurar contexto en AlmaLinux/RHEL ---
if command -v restorecon &>/dev/null && [ -f /etc/redhat-release ]; then
    echo "--- 5. Ajustando contexto SELinux ---"
    restorecon -v "$LIMITER_PATH" "$SCR_PATH" "$GHOST_CLEANUP_PATH" 2>/dev/null || true
    [ "$LIMITADOR_DIR" = /root ] || restorecon -Rv "$LIMITADOR_DIR" 2>/dev/null || true
    echo "✅ Contexto SELinux aplicado."
else
    echo "--- 5. SELinux: omitido (no restorecon o no RHEL) ---"
fi

# --- 6. CONFIGURAR PAM ---
echo "--- 6. Configurando PAM ($PAM_SSHD_FILE) ---"
if grep -qE '^\s*UsePAM\s+no' /etc/ssh/sshd_config 2>/dev/null; then
    echo "⚠️  UsePAM no en sshd_config. Actívalo (UsePAM yes) y reinicia sshd para que el limitador funcione."
fi
# Quitar cualquier línea pam_exec del limitador (usr/bin o usr/local/bin)
sed -i '/pam_exec\.so.*check_ssh_limits\.sh/d' "$PAM_SSHD_FILE"
# Insertar antes de "account include password-auth" (estructura AlmaLinux/RHEL)
# expose_authtok: compatible con sshd; el script no usa stdin pero PAM lo espera en algunos entornos
sed -i "/^account[[:space:]]*include[[:space:]]*password-auth/i account    required     pam_exec.so expose_authtok $LIMITER_PATH" "$PAM_SSHD_FILE"
echo "✅ PAM configurado."

# --- 7. REINICIAR OPENSSH (AlmaLinux usa sshd) ---
echo "--- 7. Reiniciando OpenSSH ---"
if systemctl is-active --quiet sshd 2>/dev/null; then
    systemctl restart sshd
    echo "✅ sshd reiniciado."
elif systemctl is-active --quiet ssh 2>/dev/null; then
    systemctl restart ssh
    echo "✅ ssh reiniciado."
else
    echo "⚠️  No se encontró sshd ni ssh. Reinicia el servicio SSH manualmente."
fi
echo ""
echo "--- Instalación completada ---"
echo ""
echo "Resumen:"
echo "  • Editar límites: $DB_MASTER (el guardián sincroniza a $DB_LIMITER)"
echo "  • Limitador PAM:  $LIMITER_PATH (lee $DB_LIMITER)"
echo "  • Limpiador fantasmas: $GHOST_CLEANUP_PATH (cron cada 5 min)"
echo "  • root tiene acceso total; límites aplicados al resto de usuarios."
echo ""
echo "Comandos útiles (AlmaLinux):"
echo "  systemctl status db-guardian       # Estado del guardián"
echo "  journalctl -u db-guardian -f       # Logs del guardián"
echo "  journalctl -t ssh_limiter -f       # Denegaciones del limitador"
echo "  journalctl -t ssh_ghost_cleanup -f # Limpieza de sesiones fantasma"
echo "  grep ssh_limiter /var/log/messages # Alternativa (logs tradicionales)"
echo ""
echo "Comprobar que el limitador funciona:"
echo "  1. Editar límites: nano $DB_MASTER   (ej.: usuario 1 = 1 sesión)"
echo "  2. Abrir 2+ sesiones SSH con ese usuario; la 2.ª debe denegarse."
echo "  3. Revisar: journalctl -t ssh_limiter -f"
echo ""
echo "SELinux: si hay denegaciones, revisa 'ausearch -m avc -ts recent'."
echo ""
echo "Sesiones fantasma: el limitador solo cuenta conexiones TCP ESTABLISHED."
echo "El limpiador ($GHOST_CLEANUP_PATH) mata sshd: huérfanos cada 5 min."
