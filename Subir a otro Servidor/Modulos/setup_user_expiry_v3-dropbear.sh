#!/bin/bash

# Script de configuración para el sistema de expiración de usuarios en AlmaLinux.

# --- 1. Definición de Variables ---
VERIFY_SCRIPT="/usr/local/bin/check_expired_users.sh"
LOG_FILE="/var/log/user_expiry.log"
USERS_DB="/root/usuarios.db" # RUTA DE LA BASE DE DATOS EXISTENTE

# --- 2. Verificación de Permisos ---
if [ "$(id -u)" -ne 0 ]; then
    echo "🚨 Este script debe ejecutarse como root (usando sudo)."
    exit 1
fi

# --- 3. Verificación de la Base de Datos Existente ---
echo "⚙️ Verificando la base de datos en $USERS_DB..."
if [ ! -f "$USERS_DB" ]; then
    echo "❌ ERROR: El archivo de base de datos '$USERS_DB' NO EXISTE."
    echo "Por favor, crea el archivo con los usuarios (uno por línea, ej: REDLIBRE 50) y vuelve a ejecutar."
    exit 1
fi
echo "✅ Base de datos encontrada. Continuando."
echo "---"

# --- 4. Creación del Script de Verificación (check_expired_users.sh) ---
echo "⚙️ Creando el script de verificación en $VERIFY_SCRIPT con la lógica para leer la primera palabra..."

cat << EOF > "$VERIFY_SCRIPT"
#!/bin/bash

# RUTA AL ARCHIVO DE LA BASE DE DATOS (Lista de usuarios)
USERS_DB="$USERS_DB"
LOG_FILE="$LOG_FILE"

echo "--- \$(date) ---" >> "$LOG_FILE"

if [ -f "\$USERS_DB" ]; then
    # Leer usuarios del archivo, línea por línea.
    while IFS= read -r LINE || [[ -n "\$LINE" ]]; do
        
        # Extraer solo el nombre de usuario (la primera palabra, ignorando el número)
        USERNAME=\$(echo "\$LINE" | awk '{print \$1}')
        
        # Limpiar y saltar si la línea está vacía, es un comentario o el nombre está vacío.
        if [[ -z "\$USERNAME" || "\$USERNAME" =~ ^# ]]; then
            continue
        fi
        
        # Verificar si el usuario realmente existe en el sistema
        if ! id "\$USERNAME" &>/dev/null; then
            echo "Usuario \$USERNAME: No existe en el sistema. Saltando." >> "\$LOG_FILE"
            continue
        fi
        
        # Obtener la fecha de expiración
        EXPIRY_DATE_STR=\$(chage -l "\$USERNAME" 2>/dev/null | grep "Account expires" | awk -F': ' '{print \$2}')
        
        # Comprobar si la cuenta tiene una fecha definida
        if [[ "\$EXPIRY_DATE_STR" == "never" || "\$EXPIRY_DATE_STR" == "nunca" ]]; then
            echo "Usuario \$USERNAME: Sin fecha de expiración definida. Saltando." >> "\$LOG_FILE"
            continue
        fi

        # Convertir y comparar las fechas
        EXPIRY_TIMESTAMP=\$(date -d "\$EXPIRY_DATE_STR" +%s)
        CURRENT_TIMESTAMP=\$(date +%s)

        if (( CURRENT_TIMESTAMP > EXPIRY_TIMESTAMP )); then
            echo "Usuario \$USERNAME: ¡EXPIRADO! Bloqueando la cuenta..." >> "\$LOG_FILE"
            
            # Bloquear la contraseña
            usermod -L "\$USERNAME"
            
            echo "Usuario \$USERNAME bloqueado." >> "\$LOG_FILE"
        else
            echo "Usuario \$USERNAME: Válido hasta \$EXPIRY_DATE_STR." >> "\$LOG_FILE"
        fi

    done < "\$USERS_DB"
else
    echo "🚨 ERROR: Archivo de base de datos no encontrado en \$USERS_DB. Fallo en la verificación." >> "\$LOG_FILE"
fi
EOF

# --- 5. Configuración de Permisos y Cron (09:00 AM) ---
echo "🔐 Dando permisos de ejecución al script..."
chmod +x "$VERIFY_SCRIPT"

# Se añade la tarea a crontab del usuario root para ejecutarse a las 09:00 AM.
CRON_JOB="00 09 * * * $VERIFY_SCRIPT"
(crontab -l 2>/dev/null | grep -v "$VERIFY_SCRIPT" ; echo "$CRON_JOB") | crontab -

echo "🗓️ Tarea de Cron agregada/actualizada. Se ejecutará diariamente a las 09:00 AM."
echo "---"

# --- 6. Finalización ---
echo "🎉 ¡Implementación de la configuración completada!"
echo "➡️ Prueba manual: sudo $VERIFY_SCRIPT"
echo "📍 Log: ta
il -f $LOG_FILE"
