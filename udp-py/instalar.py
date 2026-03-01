#!/usr/bin/env python3
"""
Script de instalación para UDPGW Server (Python) en AlmaLinux/RHEL.
Equivalente funcional de badvpn-almalinux pero usando la implementación Python pura.
NO requiere compilar C - solo Python 3.
"""

import os
import sys
import shutil
import subprocess

# ==========================================================
#              BLOQUE DE PARÁMETROS MODIFICABLES
# ==========================================================
CONFIG = {
    "PORT": "53",
    "MAX_CLIENTS": 1000,
    "MAX_CONNECTIONS": 10,
    "LISTEN_ADDR": "127.0.0.1",
    "LOG_LEVEL": "error",
    "SERVICE_NAME": "udpgw-py",
    "INSTALL_DIR": "/opt/udp-py",
    "PYTHON_MIN": (3, 6),
}
# ==========================================================


def run_cmd(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Ejecuta un comando en shell."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Error ejecutando: {cmd}")
        print(result.stderr or result.stdout)
        sys.exit(1)
    return result


def check_root():
    """Verifica ejecución como root."""
    if os.getuid() != 0:
        print("🛑 Error: Ejecuta como root (sudo python3 instalar.py)")
        sys.exit(1)


def check_python():
    """Verifica versión de Python."""
    ver = sys.version_info[:2]
    if ver < CONFIG["PYTHON_MIN"]:
        print(f"❌ Se requiere Python {CONFIG['PYTHON_MIN'][0]}.{CONFIG['PYTHON_MIN'][1]}+, tienes {ver[0]}.{ver[1]}")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detectado.")


def install_dependencies():
    """Instala dependencias del sistema (solo Python, sin compiladores)."""
    print("\n--- 1. Verificando sistema ---")
    run_cmd("dnf update -y")
    # Python3 suele estar preinstalado en AlmaLinux; instalar si falta
    run_cmd("dnf install -y python3 2>/dev/null || true")
    print("✅ Sistema listo (sin compilación C necesaria).")


def install_udpgw():
    """Copia el servidor Python al directorio de instalación."""
    print("\n--- 2. Instalando UDPGW Server (Python) ---")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "udpgw_server.py")

    if not os.path.exists(server_path):
        print(f"❌ No se encuentra udpgw_server.py en {script_dir}")
        sys.exit(1)

    os.makedirs(CONFIG["INSTALL_DIR"], exist_ok=True)
    dest = os.path.join(CONFIG["INSTALL_DIR"], "udpgw_server.py")
    shutil.copy(server_path, dest)
    os.chmod(dest, 0o755)
    print(f"✅ Servidor instalado en {dest}")


def configure_service():
    """Crea e inicia el servicio systemd."""
    print("\n--- 3. Configurando servicio systemd ---")

    exec_line = (
        f"/usr/bin/python3 {CONFIG['INSTALL_DIR']}/udpgw_server.py "
        f"--loglevel {CONFIG['LOG_LEVEL']} "
        f"--listen-addr {CONFIG['LISTEN_ADDR']}:{CONFIG['PORT']} "
        f"--max-clients {CONFIG['MAX_CLIENTS']} "
        f"--max-connections-for-client {CONFIG['MAX_CONNECTIONS']}"
    )

    service_content = f"""[Unit]
Description=UDPGW Server (Python) - Túnel UDP sobre TCP compatible con badvpn
After=network.target

[Service]
Type=simple
ExecStart={exec_line}
Restart=always
WorkingDirectory={CONFIG['INSTALL_DIR']}
LimitNOFILE=65535
Nice=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""

    service_file = f"/etc/systemd/system/{CONFIG['SERVICE_NAME']}.service"
    with open(service_file, "w") as f:
        f.write(service_content)

    run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {CONFIG['SERVICE_NAME']}")
    run_cmd(f"systemctl stop {CONFIG['SERVICE_NAME']} 2>/dev/null; systemctl start {CONFIG['SERVICE_NAME']}")
    print(f"✅ Servicio {CONFIG['SERVICE_NAME']} habilitado e iniciado.")


def optimize_sysctl():
    """Aplica optimizaciones de red (opcional)."""
    print("\n--- 4. Optimizando parámetros de red (sysctl) ---")
    sysctl_conf = "/etc/sysctl.conf"
    marker = "# udp-py optimizations"
    block = f"""
{marker}
net.ipv4.tcp_tw_reuse = 1
net.core.somaxconn = 65535
net.ipv4.tcp_fastopen = 3
net.core.default_qdisc = fq
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 6
"""

    with open(sysctl_conf, "r") as f:
        content = f.read()
    if marker not in content:
        with open(sysctl_conf, "a") as f:
            f.write(block)
        run_cmd("sysctl -p 2>/dev/null || true")
    print("✅ Parámetros sysctl configurados.")


def optimize_ssh():
    """Optimiza SSH para túneles (opcional)."""
    print("\n--- 5. Optimizando SSH (sshd_config) ---")
    ssh_conf = "/etc/ssh/sshd_config"
    if os.path.exists(ssh_conf):
        run_cmd(f"grep -q '^Compression no' {ssh_conf} || echo 'Compression no' >> {ssh_conf}")
        run_cmd(f"sed -i '/^Ciphers/d' {ssh_conf}; echo 'Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com' >> {ssh_conf}")
        run_cmd(f"sed -i '/^KexAlgorithms/d' {ssh_conf}; echo 'KexAlgorithms curve25519-sha256@libssh.org' >> {ssh_conf}")
        run_cmd("systemctl restart sshd 2>/dev/null || true")
    print("✅ SSH optimizado.")


def verify():
    """Verifica el estado final."""
    print("\n" + "=" * 60)
    print("           ✅ INSTALACIÓN COMPLETADA ✅")
    print("=" * 60)
    run_cmd(f"systemctl status {CONFIG['SERVICE_NAME']}", check=False)
    print(f"  - Puerto: {CONFIG['PORT']} (TCP)")
    print(f"  - Escucha en: {CONFIG['LISTEN_ADDR']}")
    print(f"  - Compatible con tun2socks/SSH VPN (mismo protocolo que badvpn-udpgw)")
    print("=" * 60)


def main():
    print("=" * 60)
    print("  Instalación UDPGW Server (Python) - AlmaLinux/RHEL")
    print("  Sin compilación C - 100% Python")
    print("=" * 60)

    check_root()
    check_python()
    install_dependencies()
    install_udpgw()
    configure_service()
    optimize_sysctl()
    optimize_ssh()
    verify()


if __name__ == "__main__":
    main()
