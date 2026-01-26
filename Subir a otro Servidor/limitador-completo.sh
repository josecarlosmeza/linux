#!/bin/bash

echo "--- 🛠️  INSTALACIÓN DEL LIMITADOR OPENSSH + GUARDIÁN DE DB (VERSIÓN SEGURA) ---"
echo ""

# --- CONFIGURACIÓN DE RUTAS ---
LIMITADOR_DIR="/etc/limitador"
DB_MASTER="$LIMITADOR_DIR/usuarios.db"
DB_LIMITER="$LIMITADOR_DIR/usuarios-limitador.db"
DB_BACKUP="$LIMITADOR_DIR/usuarios.backup"

LIMITER_PATH="/usr/local/bin/check_ssh_limits.sh"
SCR_PATH="/usr/local/bin/db-guardian.sh"
SVC_PATH="/etc/systemd/system/db-guardian.service"
PAM_SSHD_FILE="/etc/pam.d/sshd"

# --- 1. CREAR DIRECTORIO Y BASE DE DATOS MAESTRA ---
echo "--- 1. Configurando $LIMITADOR_DIR y base de datos de usuarios ---"
sudo mkdir -p "$LIMITADOR_DIR"
if [ ! -f "$DB_MASTER" ]; then
    sudo tee "$DB_MASTER" > /dev/null <<EOF
# USUARIO LIMITE
* 3
REDLIBRE 10
EOF
    echo "✅ Archivo de límites creado."
else
    echo "✅ El archivo de límites ya existe."
fi
sudo chmod 644 "$DB_MASTER"

# Asegurar que existan limitador y backup para el guardián
sudo touch "$DB_LIMITER"
sudo touch "$DB_BACKUP"
sudo cp "$DB_MASTER" "$DB_LIMITER" 2>/dev/null || true
sudo chmod 644 "$DB_LIMITER"

# --- 2. CREAR SCRIPT DEL GUARDIÁN ---
echo "--- 2. Creando Guardián de DB en $SCR_PATH ---"
sudo tee "$SCR_PATH" > /dev/null <<GUARDIAN_EOF
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

sudo chmod +x "$SCR_PATH"
echo "✅ Guardián de DB instalado."

# --- 3. CREAR SERVICIO SYSTEMD DEL GUARDIÁN ---
echo "--- 3. Creando servicio db-guardian ---"
sudo tee "$SVC_PATH" > /dev/null <<SVC_EOF
[Unit]
Description=Guardian de Base de Datos SSHPlus
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash $SCR_PATH
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVC_EOF

sudo systemctl daemon-reload
sudo systemctl enable db-guardian.service
sudo systemctl restart db-guardian.service
echo "✅ Servicio db-guardian activado y en ejecución."

# --- 4. CREAR SCRIPT LIMITADOR (PAM usa DB_LIMITER) ---
echo "--- 4. Creando Script Limitador en $LIMITER_PATH ---"
sudo tee "$LIMITER_PATH" > /dev/null <<LIMITER_EOF
#!/bin/bash
# Script de límite ejecutado por PAM (lee de usuarios-limitador.db)
DB_SOURCE="$DB_LIMITER"
USER="\$PAM_USER"

# 1. EXCEPCIÓN TOTAL PARA ROOT (Seguridad ante bloqueos)
if [ "\$USER" == "root" ] || [ -z "\$USER" ]; then
    exit 0
fi

# 2. SI NO EXISTE LA DB, PERMITIR (evitar bloquear por error de instalación)
if [ ! -r "\$DB_SOURCE" ]; then
    logger -t ssh_limiter "WARN: \$DB_SOURCE no existe o no readable; permitiendo login."
    exit 0
fi

# 3. OBTENER LÍMITE DEL ARCHIVO
MAX_ALLOWED=\$(grep "^\$USER " "\$DB_SOURCE" 2>/dev/null | awk '{print \$2}')
if [ -z "\$MAX_ALLOWED" ]; then
    MAX_ALLOWED=\$(grep "^\* " "\$DB_SOURCE" 2>/dev/null | awk '{print \$2}')
fi
MAX_ALLOWED=\${MAX_ALLOWED:-3}

# 4. CONTAR SESIONES ACTUALES (sshd por usuario)
CURRENT_SESSIONS=\$(pgrep -u "\$USER" -f "sshd:" 2>/dev/null | wc -l)

# 5. APLICAR LÓGICA DE BLOQUEO
if [ "\$CURRENT_SESSIONS" -gt "\$MAX_ALLOWED" ]; then
    logger -t ssh_limiter "DENIED: \$USER excedió el límite de \$MAX_ALLOWED (Activas: \$CURRENT_SESSIONS)"
    exit 1
fi

exit 0
LIMITER_EOF

sudo chmod +x "$LIMITER_PATH"
echo "✅ Script limitador instalado (lee de $DB_LIMITER, protege root)."

# --- 5. CONFIGURAR PAM ---
echo "--- 5. Configurando PAM ($PAM_SSHD_FILE) ---"
sudo sed -i "\|$LIMITER_PATH|d" "$PAM_SSHD_FILE"
sudo sed -i "/^account[[:space:]]*required[[:space:]]*pam_unix.so/i account\trequired\t\tpam_exec.so $LIMITER_PATH" "$PAM_SSHD_FILE"
echo "✅ PAM configurado."

# --- 6. REINICIAR OPENSSH ---
echo "--- 6. Reiniciando OpenSSH ---"
if systemctl is-active --quiet sshd 2>/dev/null; then
    sudo systemctl restart sshd
elif systemctl is-active --quiet ssh 2>/dev/null; then
    sudo systemctl restart ssh
else
    echo "⚠️  No se encontró sshd ni ssh. Reinicia el servicio SSH manualmente."
fi
echo "✅ OpenSSH reiniciado (o revisa el servicio ssh/sshd)."
echo ""
echo "--- Instalación completada ---"
echo ""
echo "Resumen:"
echo "  • Editar límites: $DB_MASTER (el guardián sincroniza a $DB_LIMITER)"
echo "  • Limitador PAM:  $LIMITER_PATH (lee $DB_LIMITER)"
echo "  • root tiene acceso total; límites aplicados al resto de usuarios."
echo ""
echo "Comandos útiles:"
echo "  systemctl status db-guardian     # Ver si el guardián está corriendo"
echo "  journalctl -u db-guardian -f     # Logs del guardián en tiempo real"
echo "  grep ssh_limiter /var/log/syslog # Ver denegaciones del limitador (o journalctl -k)"
echo ""
echo "Comprobar que el limitador funciona:"
echo "  1. Editar límites: sudo nano $DB_MASTER   (ej.: usuario 1 = 1 sesión)"
echo "  2. Abrir 2+ sesiones SSH con ese usuario; la 2.ª debe denegarse."
echo "  3. Revisar: journalctl -t ssh_limiter -f"
