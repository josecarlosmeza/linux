# Solución: No funciona tras instalación

## Problema con puerto 53

El puerto **53** suele estar en uso por DNS. El proyecto usa por defecto el **puerto 8443**.

## Pasos en tu servidor

### 1. Actualizar archivos
Sube de nuevo la carpeta `udp-py` y el módulo `badvpn` al servidor.

### 2. Detener el servicio anterior (puerto 53)
```bash
sudo systemctl stop udpgw-py
```

### 3. Reinstalar / actualizar configuración
```bash
cd /ruta/a/udp-py
sudo python3 instalar.py
```

O, si solo quieres cambiar el puerto manualmente:

```bash
sudo systemctl stop udpgw-py
sudo nano /etc/systemd/system/udpgw-py.service
```

Modifica la línea `ExecStart` para usar `127.0.0.1:8443`:

```
ExecStart=/usr/bin/python3 /opt/udp-py/udpgw_server.py --loglevel error --listen-addr 127.0.0.1:8443 --max-clients 1000 --max-connections-for-client 10
```

Luego:
```bash
sudo systemctl daemon-reload
sudo systemctl start udpgw-py
```

### 4. Comprobar que escucha en 8443
```bash
ss -tlnp | grep 8443
```

Debe aparecer algo como:
```
LISTEN  0  64  127.0.0.1:8443  0.0.0.0:*  users:(("python3",pid=...))
```

### 5. Firewall
Con `127.0.0.1`, el servicio solo acepta conexiones locales (por ejemplo, vía túnel SSH). No hace falta abrir el puerto 8443 en el firewall para tráfico externo.

Si en algún momento quisieras escuchar en todas las interfaces (`0.0.0.0:8443`), entonces sí habría que abrir **TCP 8443** (no UDP) en el firewall.

## ¿Por qué no funcionaba?

1. **Puerto 53**: Suele estar ocupado por DNS.
2. **Puerto**: El menú y udpgw-py usan el puerto configurado (por defecto 8443). El cliente/tun2socks debe hacer túnel al mismo puerto.
3. **TCP vs UDP**: UDPGW usa **TCP**; abrir solo UDP 53 no sirve.
