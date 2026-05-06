import os
import subprocess
import sys
import shutil
import multiprocessing

# ==========================================================
#              BLOQUE DE PARÁMETROS MODIFICABLES
# ==========================================================
CONFIG = {
    "PORT": "7300",               # Puerto UDPGW
    "MAX_CLIENTS": 500,           # Máximo de usuarios
    "MAX_CONN_CLIENT": 5,         # Conexiones por usuario
    "LISTEN_ADDR": "0.0.0.0",     # Acceso total
    "LOG_LEVEL": "none",          # 'none' para 0% CPU
    "SERVICE_NAME": "badvpn-udpgw",
    "BIN_PATH": "/usr/local/bin/badvpn-udpgw",
    "SOURCE_DIR": "/opt/badvpn_source" # Carpeta temporal
}

DEPENDENCIES = ["git", "cmake", "gcc", "make", "util-linux"]
# ==========================================================

def run_cmd(command):
    return subprocess.run(command, shell=True, capture_output=True, text=True)

def check_dependencies():
    print("🔍 Verificando e instalando dependencias...")
    run_cmd("dnf update -y")
    for dep in DEPENDENCIES:
        run_cmd(f"dnf install {dep} -y")

def install_badvpn():
    if os.getuid() != 0:
        print("🛑 Error: Ejecuta como ROOT."); sys.exit(1)

    # Detener procesos para liberar el archivo (Evita 'Text file busy')
    run_cmd(f"systemctl stop {CONFIG['SERVICE_NAME']}")
    run_cmd(f"pkill -9 badvpn-udpgw")

    if os.path.exists(CONFIG["SOURCE_DIR"]):
        shutil.rmtree(CONFIG["SOURCE_DIR"])

    print("🏗️  Compilando badvpn (esto puede tardar un poco)...")
    run_cmd(f"git clone https://github.com/ambrop72/badvpn.git {CONFIG['SOURCE_DIR']}")
    
    build_dir = os.path.join(CONFIG["SOURCE_DIR"], "build")
    os.makedirs(build_dir, exist_ok=True)
    os.chdir(build_dir)
    
    run_cmd("cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1")
    run_cmd(f"make -j{multiprocessing.cpu_count()}")
    
    if os.path.exists("udpgw/badvpn-udpgw"):
        if os.path.exists(CONFIG["BIN_PATH"]):
            os.remove(CONFIG["BIN_PATH"])
        shutil.copy("udpgw/badvpn-udpgw", CONFIG["BIN_PATH"])
        os.chmod(CONFIG["BIN_PATH"], 0o755)
        print("✅ Binario instalado correctamente.")
    else:
        print("❌ Error en compilación."); sys.exit(1)

def configure_service():
    print(f"⚙️  Creando servicio systemd...")
    exec_line = (
        f"{CONFIG['BIN_PATH']} --loglevel {CONFIG['LOG_LEVEL']} "
        f"--listen-addr {CONFIG['LISTEN_ADDR']}:{CONFIG['PORT']} "
        f"--max-clients {CONFIG['MAX_CLIENTS']} "
        f"--max-connections-for-client {CONFIG['MAX_CONN_CLIENT']}"
    )
    
    service_content = f"""[Unit]
Description=UDP Forwarder Optimized
After=network.target

[Service]
Type=simple
ExecStart={exec_line}
Restart=always
# Solución definitiva al consumo de CPU
LimitNOFILE=65535
Nice=10

[Install]
WantedBy=multi-user.target
"""
    with open(f"/etc/systemd/system/{CONFIG['SERVICE_NAME']}.service", "w") as f:
        f.write(service_content)

    run_cmd("systemctl daemon-reload")
    run_cmd(f"systemctl enable {CONFIG['SERVICE_NAME']}")
    run_cmd(f"systemctl start {CONFIG['SERVICE_NAME']}")

def optimize_and_clean():
    print("🚀 Optimizando Kernel y limpiando archivos temporales...")
    # Abrir puertos
    run_cmd(f"firewall-cmd --permanent --add-port={CONFIG['PORT']}/tcp")
    run_cmd(f"firewall-cmd --permanent --add-port={CONFIG['PORT']}/udp")
    run_cmd("firewall-cmd --reload")
    
    # BBR y Límites
    with open("/etc/sysctl.conf", "a") as f:
        f.write("\nnet.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\nfs.file-max=65535\n")
    run_cmd("sysctl -p")

    # LIMPIEZA: Borrar código fuente para ahorrar espacio
    if os.path.exists(CONFIG["SOURCE_DIR"]):
        shutil.rmtree(CONFIG["SOURCE_DIR"])
        print(f"🧹 Carpeta {CONFIG['SOURCE_DIR']} eliminada.")

if __name__ == "__main__":
    check_dependencies()
    install_badvpn()
    configure_service()
    optimize_and_clean()
    print(f"\n✨ INSTALACIÓN Y LIMPIEZA COMPLETADA ✨")
    print(f"Puerto activo: {CONFIG['PORT']}")
