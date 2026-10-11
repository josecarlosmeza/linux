#!/bin/bash
# Llamado por pam_exec en /etc/pam.d/sshd (session). Corre como root; el usuario real va en PAM_USER.
# No mostrar para root ni fuera del servicio sshd.

[[ "${PAM_SERVICE:-}" == "sshd" ]] || exit 0
[[ -n "${PAM_USER:-}" ]] || exit 0
[[ "${PAM_USER}" == "root" ]] && exit 0

export SSH_CUENTA_INFO_FROM_PAM=1
exec /usr/local/bin/cuenta_info.sh
