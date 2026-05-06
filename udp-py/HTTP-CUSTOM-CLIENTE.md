# HTTP Custom + UDPGW: no se ven conexiones

Si en el servidor **no aparece ninguna conexión** cuando usas HTTP Custom con “UDP en puerto 8443”, revisa lo siguiente.

---

## 1. UDPGW usa **TCP**, no UDP

El servidor UDPGW escucha en **TCP** puerto 8443. El tráfico UDP del juego va *dentro* de esa conexión TCP.

- En el **servidor**: se aceptan conexiones **TCP** en el puerto 8443.
- En **HTTP Custom**: el “UDP gateway” debe estar configurado como **host:8443** y la conexión al servidor debe ser **TCP** (no “escuchar UDP en 8443” hacia el servidor).

Si en el cliente pones “UDP en 8443” pensando que el servidor escucha UDP, no funcionará: el servidor solo acepta TCP en 8443.

---

## 2. Dónde escucha el servidor: 127.0.0.1 vs 0.0.0.0

- **127.0.0.1:8443** → Solo conexiones **desde el propio servidor** (por ejemplo, un túnel SSH que redirige a 127.0.0.1:8443).
- **0.0.0.0:8443** → Conexiones desde **cualquier interfaz** (incluida la IP pública del VPS).

Si el **cliente (HTTP Custom)** se conecta **directamente a la IP del VPS** (sin SSH u otro túnel en el medio), el servidor debe escuchar en **0.0.0.0** y el firewall debe permitir **TCP 8443**.

Prueba en el servidor:

```bash
/usr/bin/python3 /opt/udp-py/udpgw_server.py --listen-addr 0.0.0.0:8443 --loglevel info --max-connections-for-client 25
```

Y en el firewall (ejemplo con firewalld):

```bash
sudo firewall-cmd --permanent --add-port=8443/tcp
sudo firewall-cmd --reload
```

Si usas **túnel SSH** (el cliente hace -L 8443:127.0.0.1:8443 y HTTP Custom se conecta a 127.0.0.1:8443 en el cliente), entonces en el servidor basta **127.0.0.1:8443** y no hace falta abrir 8443 en el firewall.

---

## 3. Ver conexiones entrantes en el servidor

Para ver cada conexión TCP que llega al UDPGW:

```bash
sudo systemctl stop udpgw-py
/usr/bin/python3 /opt/udp-py/udpgw_server.py --listen-addr 0.0.0.0:8443 --loglevel info --max-connections-for-client 25
```

Deberías ver:

- Al arrancar: `UDPGW Server escuchando en 0.0.0.0:8443`
- Por cada cliente: `Conexión entrante desde <IP>:<puerto>`

Si usas **127.0.0.1** y el cliente se conecta por SSH, la IP que verás será 127.0.0.1 (o la que use el túnel).

---

## 4. Comprobar que el puerto TCP 8443 es alcanzable

Desde **otro equipo** (no el servidor):

```bash
nc -vz IP_DEL_SERVIDOR 8443
```

o:

```bash
telnet IP_DEL_SERVIDOR 8443
```

Si conecta, el TCP 8443 está llegando al servidor. Si no, revisa firewall y que el proceso escuche en **0.0.0.0:8443** (no solo 127.0.0.1).

---

## 5. Resumen para HTTP Custom

| Comprobación | Qué hacer |
|--------------|-----------|
| Servidor solo para conexiones locales (túnel SSH) | `--listen-addr 127.0.0.1:8443` |
| Cliente se conecta a IP pública del VPS | `--listen-addr 0.0.0.0:8443` y abrir **TCP 8443** en firewall |
| Ver conexiones en el servidor | `--loglevel info` y buscar “Conexión entrante desde…” |
| Protocolo correcto | Conexión al servidor siempre **TCP** al puerto 8443; UDP va dentro del túnel |

Ajusta en HTTP Custom que el “UDP gateway” apunte al **host y puerto TCP** correctos (IP o dominio del servidor y 8443), no a “UDP en 8443” como si el servidor escuchara UDP.
