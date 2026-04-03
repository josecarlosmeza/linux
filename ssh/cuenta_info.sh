#!/bin/bash
# Información de cuenta al conectar por SSH (compatible con HTTP Custom: salida texto plano).
# Uso:
#   - Ejecutable: /ruta/cuenta_info.sh
#   - En el servidor: enlace en /etc/profile.d/ (solo sesiones login) o al final de ~/.bash_profile
#
# Variables opcionales:
#   SSH_CUENTA_INFO_COLOR=1  — colores si la salida es una TTY
#   SSH_CUENTA_INFO_QUIET=1  — no mostrar nada (útil para pruebas)

if [[ "${SSH_CUENTA_INFO_QUIET:-0}" == "1" ]]; then
  [[ "${BASH_SOURCE[0]}" == "${0}" ]] && exit 0 || return 0 2>/dev/null || exit 0
fi

_u="${USER:-$(id -un)}"
[[ -z "$_u" || "$_u" == "root" ]] && { [[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0 || exit 0; }

_db="/root/usuarios.db"
_color=0
[[ -n "${SSH_CUENTA_INFO_COLOR:-}" && -t 1 ]] && _color=1

_lim="1"
if [[ -r "$_db" ]] && grep -qE "^${_u}[[:space:]]" "$_db" 2>/dev/null; then
  _lim="$(grep -E "^${_u}[[:space:]]" "$_db" 2>/dev/null | head -1 | awk '{print $2}')"
fi
[[ -z "$_lim" || ! "$_lim" =~ ^[0-9]+$ ]] && _lim="1"

_exp_raw="$(LANG=en_US.UTF-8 chage -l "$_u" 2>/dev/null | grep "Account expires" | awk -F': ' '{print $2}' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
_dias=""
_fecha=""
_estado="sin_fecha"

if [[ -z "$_exp_raw" || "$_exp_raw" == "never" ]]; then
  _fecha="Nunca"
  _dias="N/A"
  _estado="sin_vencimiento"
else
  _fecha="$(date --date="$_exp_raw" '+%d/%m/%Y' 2>/dev/null || date -d "$_exp_raw" '+%d/%m/%Y' 2>/dev/null || echo "$_exp_raw")"
  _exp_sec="$(date +%s --date="$_exp_raw" 2>/dev/null || date +%s -d "$_exp_raw" 2>/dev/null)"
  _now_sec="$(date +%s)"
  if [[ -n "$_exp_sec" ]]; then
    if [[ "$_now_sec" -ge "$_exp_sec" ]]; then
      _dias="0"
      _estado="expirada"
    else
      _dias=$(( (_exp_sec - _now_sec) / 86400 ))
      _estado="activa"
    fi
  else
    _dias="?"
    _estado="desconocida"
  fi
fi

# Sesiones SSH activas (OpenSSH: proceso sshd bajo el usuario)
_act="$(pgrep -u "$_u" -f "sshd:" 2>/dev/null | wc -l)"
_act="${_act//[[:space:]]/}"

if [[ "$_color" == "1" ]]; then
  echo ""
  echo -e "\033[0;36m────────── Información de cuenta ──────────\033[0m"
  echo -e " \033[1;37mUsuario:\033[0m           $_u"
  echo -e " \033[1;37mVencimiento:\033[0m       $_fecha"
  echo -e " \033[1;37mDías restantes:\033[0m    $_dias"
  echo -e " \033[1;37mSesiones admitidas:\033[0m $_lim"
  echo -e " \033[1;37mSesiones activas:\033[0m  $_act"
  case "$_estado" in
    expirada) echo -e " \033[1;37mEstado:\033[0m            \033[1;31mCuenta expirada\033[0m" ;;
    activa)   echo -e " \033[1;37mEstado:\033[0m            \033[1;32mActiva\033[0m" ;;
    *)        echo -e " \033[1;37mEstado:\033[0m            $_estado" ;;
  esac
  echo -e "\033[0;36m──────────────────────────────────────────\033[0m"
  echo ""
else
  echo ""
  echo "========== Información de cuenta =========="
  echo "usuario=$_u"
  echo "vencimiento=$_fecha"
  echo "dias_restantes=$_dias"
  echo "sesiones_admitidas=$_lim"
  echo "sesiones_activas=$_act"
  echo "estado=$_estado"
  echo "==========================================="
  echo ""
fi

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
exit 0
