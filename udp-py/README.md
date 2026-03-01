# UDP-PY - UDPGW Server en Python

Implementación en **Python pura** del servidor UDPGW, compatible con el protocolo de **BadVPN** (badvpn-udpgw).  
Permite túneles UDP sobre TCP sin compilar código C.

## Características

- ✅ **100% Python** – No requiere compiladores (gcc, cmake, make)
- ✅ **Protocolo compatible** – Funciona con tun2socks, OpenVPN sobre SSH, etc.
- ✅ **Mismo formato** – Usa el protocolo UDPGW estándar (puerto 53 por defecto)
- ✅ **Mínimas dependencias** – Solo Python 3.6+
- ✅ **Límites aplicados** – max-clients y max-connections-for-client
- ✅ **Apagado limpio** – Respeta SIGTERM/SIGINT (systemd)
- ✅ **Timeouts** – Cierre de clientes inactivos y protección frente a bloqueos
- ✅ **Estadísticas** – Opción de logs periódicos (activos/total)

## Estructura

```
udp-py/
├── udpgw_server.py   # Servidor UDPGW (implementación del protocolo)
├── instalar.py       # Script de instalación para AlmaLinux/RHEL
├── MODO-USO.md       # Guía detallada de parámetros y uso
└── README.md         # Este archivo
```

## Instalación en AlmaLinux / RHEL

1. Copia la carpeta `udp-py` al servidor.
2. Ejecuta como root:

```bash
cd udp-py
sudo python3 instalar.py
```

El script instalará el servidor en `/opt/udp-py` y creará el servicio systemd `udpgw-py`.

## Uso manual (sin systemd)

```bash
python3 udpgw_server.py --listen-addr 127.0.0.1:53 --max-clients 1000 --max-connections-for-client 10
```

### Parámetros

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--listen-addr` | 127.0.0.1:53 | Dirección y puerto TCP |
| `--loglevel` | error | debug, info, warning, error, none |
| `--max-clients` | 1000 | Máximo de conexiones TCP simultáneas |
| `--max-connections-for-client` | 10 | Port-forwards UDP por cliente |
| `--client-timeout` | 300 | Segundos de inactividad para cerrar (0=infinito) |
| `--udp-timeout` | 30 | Timeout en socket UDP (segundos) |
| `--stats-interval` | 0 | Mostrar estadísticas cada N segundos (0=desactivado) |
| `--tcp-buffer` | 262144 | Buffer TCP en bytes (reduce pérdida en picos) |
| `--udp-buffer` | 131072 | Buffer UDP en bytes |
| `--no-tcp-nodelay` | - | Desactivar (aumenta latencia, no recomendado) |
| `--no-keepalive` | - | Desactivar detección de conexiones muertas |

> 📖 **Guía completa:** Ver [MODO-USO.md](MODO-USO.md) para descripción detallada de cada parámetro y configuración recomendada para 300 usuarios.

## Compatibilidad con badvpn-almalinux

Este proyecto reemplaza la necesidad de compilar badvpn-udpgw. En tu script o menú VPN:

- **Antes**: `badvpn-udpgw --listen-addr 127.0.0.1:7300 ...`
- **Ahora**: `python3 /opt/udp-py/udpgw_server.py --listen-addr 127.0.0.1:53 ...`

O usa el servicio: `systemctl start udpgw-py`

El protocolo es el mismo; el puerto por defecto es **53**. Si usas tun2socks, configura `--udpgw-remote-server-addr` con el puerto correspondiente.

## Estabilidad de conexión

El servidor aplica por defecto:

- **TCP_NODELAY**: Desactiva Nagle; envía paquetes de inmediato (menor latencia).
- **SO_KEEPALIVE**: Detecta conexiones “colgadas” (cliente caído, red cortada).
- **Buffers aumentados**: 256 KB (TCP) y 128 KB (UDP) para soportar picos de tráfico.

Para reforzar la estabilidad en el servidor, añade en sysctl:

```
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 6
```
