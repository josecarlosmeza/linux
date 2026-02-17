# Análisis del proyecto RedLibre para AlmaLinux 8 y 9

## Resumen del proyecto

- **Nombre**: RedLibre (instalador Plus2-centos).
- **Función**: Conjunto de scripts para gestionar usuarios SSH, límites de conexión, proxies (Squid), OpenVPN, BadVPN, Dropbear, banners, backups, etc.
- **Origen**: Diseñado para CentOS (yum) y con partes pensadas para Debian/Ubuntu (apt, dpkg, `/etc/default/`).

## Estado actual respecto a AlmaLinux 8/9

| Componente | Estado | Notas |
|------------|--------|--------|
| **Plus2-centos** (RedLibre) | Parcial | Usa `yum` y `service sshd`; en AlmaLinux 8/9 se usa `dnf` y `systemctl`. `python-pip` → `python3-pip`. |
| **list** (instalador) | Incompatible | `dpkg-reconfigure tzdata`, `service cron/apache2/sshd`; en RHEL: `timedatectl`, `crond`, `httpd`, `sshd` con systemctl. Descarga jq binario; en AlmaLinux `jq` está en repos. |
| **limitador-completo.sh** | ✅ Listo | Ya preparado para AlmaLinux/RHEL (PAM, systemd, restorecon). |
| **badvpn-almalinux** | ✅ Listo | Instala badvpn-udpgw con systemd en AlmaLinux. |
| **criarusuario** | ✅ Listo | Optimizado para AlmaLinux (useradd, dnf, /bin/false). |
| **criarteste** | ✅ Listo | AlmaLinux/RHEL 8 y 9 (nologin, systemctl atd). |
| **menu** | Parcial | Usa `/etc/issue.net` (válido en AlmaLinux). Dropbear en `/etc/default/dropbear` es opcional; en AlmaLinux suele usarse solo OpenSSH. |
| **conexao** | Parcial | Detecta `centos` por `/etc/redhat-release` (AlmaLinux también lo tiene). Muchas opciones usan `apt-get`, `service`, Dropbear, Stunnel, etc.; hace falta rama dnf/systemctl para AlmaLinux. |
| **reiniciarservicos** | Incompatible | Todo con `service`; en AlmaLinux: `systemctl restart sshd`, `squid`, `crond`, etc. |
| **reiniciarsistema** | ✅ OK | `shutdown -r now` es universal. |
| **badvpn** (módulo) | Parcial | Busca `/bin/badvpn-udpgw` y usa screen; en AlmaLinux el script instala en `/usr/local/bin` y como servicio systemd. |
| **banner** | Incompatible | `/etc/default/dropbear`, `service ssh/dropbear`; en AlmaLinux solo sshd. |
| **blockt** | Incompatible | `apt-get install iptables`; en AlmaLinux: `dnf install iptables`. |
| **delscript** | Incompatible | Solo `apt-get purge`; en AlmaLinux: `dnf remove`. |
| **otimizar** | Incompatible | `apt-get update/upgrade`, dpkg; en AlmaLinux: `dnf update`, sin dpkg. |
| **userbackup** | Incompatible | `apt-get install apache2`; en AlmaLinux: `dnf install httpd`. |
| **addhost / delhost** | Parcial | `service squid/squid3 reload`; en AlmaLinux: `systemctl reload squid`. |
| **Usuarios-expirados_v3-dropbear.sh** | Parcial | Pensado para AlmaLinux 9; revisar crontab y rutas. |

## Diferencias clave AlmaLinux 8/9 vs Debian/CentOS antiguo

- **Gestor de paquetes**: `dnf` (no `yum` ni `apt`).
- **Servicios**: `systemctl start|restart|enable <servicio>` (no `service <servicio> start`).
- **Nombres de servicio**: `sshd` (no `ssh`), `crond` (no `cron`), `httpd` (no `apache2`), `squid` igual.
- **Timezone**: `timedatectl set-timezone America/Sao_Paulo` o enlace en `/etc/localtime`; no `dpkg-reconfigure tzdata`.
- **OpenSSH**: Puerto y configuración en `/etc/ssh/sshd_config`; servicio `sshd`.
- **SELinux**: Presente; usar `restorecon` cuando se creen scripts en `/usr/bin` o `/usr/local/bin`.
- **Python**: `python3` y `pip3` (o `dnf install python3-pip`); no `python-pip`.
- **jq**: Disponible en repos: `dnf install jq`.

## Plan de edición (orden sugerido)

1. **Plus2-centos** – ✅ Hecho: dnf, systemctl sshd, python3-pip / pip3.
2. **list** – ✅ Hecho: timezone (timedatectl), systemctl sshd/crond, jq (dnf o wget), apache2/httpd condicional.
3. **reiniciarservicos** – ✅ Hecho: systemctl para sshd, squid, crond, dropbear, openvpn, httpd/apache2.
4. **menu** – ✅ Hecho: Detección AlmaLinux/Rocky/RHEL en `/etc/redhat-release`; indicador BAD VPN con systemd.
5. **banner, blockt, delscript, otimizar, userbackup, addhost, delhost** – ✅ Hecho: dnf + systemctl cuando aplica.
6. **conexao** – ⏳ Pendiente: archivo muy largo; añadir ramas dnf/systemctl para Squid, OpenVPN, Dropbear, etc.
7. **badvpn** (módulo) – ✅ Hecho: soporte systemd y `/usr/local/bin/badvpn-udpgw`; detección de servicio activo.

## Notas adicionales

- En AlmaLinux mínimo no suele estar Apache/Dropbear/Stunnel; los scripts deben comprobar si el servicio existe antes de reiniciarlo.
- El limitador de conexiones ya está cubierto por `limitador-completo.sh` (PAM + systemd); el módulo "limiter" (screen) puede convivir o usarse solo en entornos sin PAM.
- **usuarios.db**: En el proyecto está en `$HOME/usuarios.db` (p. ej. `/root/usuarios.db`); el limitador-completo y los módulos ya lo referencian así.
