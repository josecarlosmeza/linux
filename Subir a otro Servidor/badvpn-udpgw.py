import os
import subprocess
import sys
import shutil
import multiprocessing

# --- Configuración ---
CONFIG = {
    "repo_url": "https://github.com/ambrop72/badvpn.git",
    "service_path": "/etc/systemd/system/badvpn-udpgw.service",
    "bin_path": "/usr/local/bin/badvpn-udpgw",
    "source_dir": "/opt/badvpn_source",
    "port": "7300",
    "max_clients": 1000,
    "max_connections": 10
}

def run_cmd(command):
    """Ejecuta comandos de sistema."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result

def check_root():
    """Verifica permisos de root."""
    if os.getuid() != 0:
        print("🛑 Error: Ejecuta como ROOT (sudo).")
        sys.exit(1)

def install():
    check_root()
    cores = multiprocessing.cpu_count()
    print(f"🚀 Iniciando instalación optimizada ({cores} núcleos)...")

    # 1. Dependencias
    print("📦 Instalando dependencias...")
    run_cmd("dnf install git cmake gcc make util-linux -y")

    # 2. Compilación
    if os.path.exists(CONFIG["source_dir"]):
        shutil.rmtree(CONFIG["source_dir"])
    
    print("🏗️  Descargando y compilando...")
    run_cmd(f"git clone {CONFIG['repo_url']} {CONFIG['source_dir']}")
    
    build_dir = os.path.join(CONFIG["source_dir"], "build")
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)
        
    os.chdir(build_dir)
    run_cmd("cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1")
    run_cmd(f"make -j{cores}")
    
    if os.path.exists("udpgw/badvpn-udpgw"):
        shutil.copy("udpgw/badvpn-udpgw", CONFIG["bin_path"])
        os.chmod(CONFIG["bin_path"], 0o755)
    else:
        print("❌ Error: No se encontró el binario compilado.")
        return

    # 3. Servicio
    print("⚙️  Configurando servicio...")
    exec_line = f"{CONFIG['bin_path']} --loglevel error --listen-addr 127.0.0.1:{CONFIG['port']} --max-clients {CONFIG['max_clients']} --max-connections-for-client {CONFIG['max_connections']}"
    
    service_content = f"""[Unit]
Description=UDP Forwarder Optimized
After=network.target

[Service]
Type=simple
ExecStart={exec_line}
Restart=always

[Install]
WantedBy=multi-user.target
"""
    with open(CONFIG["service_path"], "w") as f:
        f.write(service_content)

    run_cmd("systemctl daemon-reload")
    run_cmd("systemctl enable badvpn-udpgw")
    run_cmd("systemctl restart badvpn-udpgw")
    print("✅ Instalación completada y servicio iniciado.")

def uninstall():
    check_root()
    print("🗑️ Desinstalando y limpiando sistema...")
    
    run_cmd("systemctl stop badvpn-udpgw")
    run_cmd("systemctl disable badvpn-udpgw")
    
    files_to_remove = [CONFIG["service_path"], CONFIG["bin_path"]]
    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print(f"  - Eliminado: {f}")

    if os.path.exists(CONFIG["source_dir"]):
        shutil.rmtree(CONFIG["source_dir"])
        print(f"  - Eliminada carpeta de fuente: {CONFIG['source_dir']}")

    run_cmd("systemctl daemon-reload")
    print("✅ El sistema está limpio.")

def status():
    """Muestra el estado del servicio."""
    subprocess.run(["systemctl", "status", "badvpn-udpgw"])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: sudo python3 udp.py [install | uninstall | status]")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "install":
        install()
    elif action == "uninstall":
        uninstall()
    elif action == "status":
        status()
    else:
        print("❌ Acción no reconocida.")
