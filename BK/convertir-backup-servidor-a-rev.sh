#!/bin/bash
#===============================================================================
# Convierte un backup de servidor RedLibre (backup.vps del menú raíz) al formato
# que importa el revendedor: panel revendedor → opción 7 → Importar.
#
# Uso (ejecutar en Linux, en la misma carpeta o con ruta completa):
#   ./convertir-backup-servidor-a-rev.sh backup_servidor.vps [salida.vps] [filtro.txt]
#
# - backup_servidor.vps : tar creado con usuarios.db + /etc/shadow (+ passwd…)
# - salida.vps          : por defecto redlibre-rev-import.vps en el directorio actual
# - filtro.txt          : opcional; un nombre de usuario por línea (# = comentario)
#                         Solo esos usuarios se incluyen (útil para asignar un rev).
#
# Resultado: súbalo al home del revendedor (scp desde admin) o indique la ruta
# al importar. El archivo es un tar con usuarios.db, senha/, expiry.txt y metadatos.
#===============================================================================
set -euo pipefail

_usage() {
    echo "Uso: $0 <backup_servidor.vps> [salida_rev.vps] [filtro_usuarios.txt]" >&2
    exit 1
}

[[ "${1:-}" ]] || _usage
BACKUP="$1"
OUT="${2:-redlibre-rev-import.vps}"
FILTER="${3:-}"

[[ -f "$BACKUP" ]] || { echo "No existe: $BACKUP" >&2; exit 1; }
[[ -z "$FILTER" || -f "$FILTER" ]] || { echo "No existe filtro: $FILTER" >&2; exit 1; }

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

tar -xf "$BACKUP" -C "$tmpdir" 2>/dev/null || {
    echo "No se pudo leer el tar (¿es backup.vps válido?)." >&2
    exit 1
}

DB=$(find "$tmpdir" -name usuarios.db -type f 2>/dev/null | head -n1)
SHADOW=$(find "$tmpdir" \( -path '*/etc/shadow' -o -path '*/shadow' \) -type f 2>/dev/null | grep -E '/etc/shadow$' | head -n1)
[[ -z "$SHADOW" ]] && SHADOW=$(find "$tmpdir" -name shadow -type f 2>/dev/null | head -n1)

[[ -n "$DB" ]] || { echo "No se encontró usuarios.db dentro del backup." >&2; exit 1; }
[[ -n "$SHADOW" ]] || { echo "No se encontró etc/shadow dentro del backup." >&2; exit 1; }

# Ruta base .../etc para localizar RedLibre/senha si el tar la trae
ETC_ROOT=$(dirname "$SHADOW")

declare -A ALLOW=()
if [[ -n "$FILTER" ]]; then
    while IFS= read -r fu || [[ -n "$fu" ]]; do
        fu="${fu%$'\r'}"
        [[ -z "$fu" || "$fu" =~ ^[[:space:]]*# ]] && continue
        fu="${fu%%[[:space:]]*}"
        ALLOW["$fu"]=1
    done < "$FILTER"
fi

work=$(mktemp -d)
trap 'rm -rf "$tmpdir" "$work"' EXIT
mkdir -p "$work/senha"
: >"$work/usuarios.db"
: >"$work/expiry.txt"

_shadow_exp_to_ymd() {
    local d="${1:-}"
    d="${d//$'\r'/}"
    [[ -z "$d" || "$d" == "0" ]] && { echo "never"; return 0; }
    date -u -d "1970-01-01 UTC + ${d} days" '+%Y-%m-%d' 2>/dev/null \
        || date -u -d "@$((d * 86400))" '+%Y-%m-%d' 2>/dev/null \
        || echo "never"
}

_count=0
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//$'\r'/}"
    [[ -z "${line// }" ]] && continue
    u=$(awk '{print $1}' <<<"$line")
    [[ -z "$u" ]] && continue
    if ((${#ALLOW[@]} > 0)) && [[ "${ALLOW[$u]:-}" != "1" ]]; then
        continue
    fi

    _sp_line=$(awk -F: -v "name=$u" '$1==name {print; exit}' "$SHADOW" || true)
    [[ -n "$_sp_line" ]] || { echo "(Aviso) Sin entrada en shadow: $u — omitido." >&2; continue; }
    _hash=$(awk -F: -v "name=$u" '$1==name {print $2; exit}' "$SHADOW")
    [[ -n "$_hash" && "$_hash" != '!' && "$_hash" != '*' && "$_hash" != '!!' ]] || {
        echo "(Aviso) Cuenta bloqueada o sin hash en shadow: $u — omitido." >&2
        continue
    }

    _expd=$(awk -F: -v "name=$u" '$1==name {print $8; exit}' "$SHADOW")
    _ymd=$(_shadow_exp_to_ymd "$_expd")

    _plain="$ETC_ROOT/RedLibre/senha/$u"
    if [[ -f "$_plain" ]]; then
        install -m 600 "$_plain" "$work/senha/$u"
    else
        printf '%s\n' "$_hash" >"$work/senha/$u"
        chmod 600 "$work/senha/$u" 2>/dev/null || true
    fi

    echo "$line" >>"$work/usuarios.db"
    echo "${u}|${_ymd}" >>"$work/expiry.txt"
    _count=$((_count + 1))
done <"$DB"

[[ "$_count" -gt 0 ]] || { echo "No quedó ningún usuario para exportar (¿filtro demasiado estricto?)." >&2; exit 1; }

echo "1" >"$work/.redlibre_rev_backup_version"
echo "convertido-desde-servidor|$(date '+%Y-%m-%d %H:%MUTC' -u 2>/dev/null || date -u)" >"$work/.redlibre_rev_backup_info"

rm -f "$OUT"
tar -cf "$OUT" -C "$work" \
    usuarios.db senha expiry.txt .redlibre_rev_backup_version .redlibre_rev_backup_info

echo "OK: $_count usuario(s) → $(readlink -f "$OUT" 2>/dev/null || echo "$OUT")"
echo "Copie el archivo al servidor y el revendedor lo importa desde la opción 7 (indique la ruta completa)."
