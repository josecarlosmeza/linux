# Juegos (Free Fire y otros) — Configuración recomendada

Si **Free Fire** u otros juegos online no funcionan o se desconectan con la VPN, prueba lo siguiente.

---

## 1. Aumentar conexiones UDP por usuario

Los juegos abren **varias conexiones UDP** a la vez (servidor de partida, voz, etc.). Si el límite es bajo, las nuevas se rechazan y el juego falla.

**En el servidor**, edita el servicio y sube `--max-connections-for-client`:

```bash
sudo nano /etc/systemd/system/udpgw-py.service
```

En la línea `ExecStart`, usa al menos **25** (recomendado para juegos):

```
--max-connections-for-client 25
```

Ejemplo completo:

```
ExecStart=/usr/bin/python3 /opt/udp-py/udpgw_server.py --loglevel error --listen-addr 127.0.0.1:8443 --max-clients 1000 --max-connections-for-client 25
```

Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl restart udpgw-py
```

Si instalas de nuevo con `instalar.py`, ya usa 25 por defecto.

---

## 2. Buffers más grandes (opcional)

Para picos de tráfico (partidas con muchos jugadores), puedes subir los buffers:

```bash
# Añadir al ExecStart:
--tcp-buffer 524288 --udp-buffer 262144
```

---

## 3. Cliente / teléfono

- **Tun2socks**: Debe estar configurado con el mismo puerto que el servidor (8443) en `--udpgw-remote-server-addr`.
- **Proxy / túnel**: El túnel (SSH, etc.) debe hacer forward del puerto **8443** (TCP), no otro.
- **Solo juego por VPN**: Si todo el tráfico va por VPN y falla solo el juego, prueba llevar **solo el juego** por la VPN (split tunneling), si tu cliente lo permite.

---

## 4. Limitación: UDP sobre TCP

El túnel lleva **UDP del juego sobre TCP**. Si la red pierde paquetes, TCP los reenvía y puede retrasar el resto (más latencia o “tirones”). Es una limitación del diseño, no solo de este servidor.

Para **menos lag** en juegos suele ir mejor:

- Buena conexión desde el servidor hasta los servidores del juego.
- Servidor VPN cerca (misma región que el juego).
- Evitar redes muy cargadas o inestables.

---

## 5. Resumen para Free Fire

| Parámetro                     | Valor recomendado |
|------------------------------|-------------------|
| `--max-connections-for-client` | **25** o más      |
| `--max-clients`               | 500–1000          |
| `--udp-buffer`               | 262144 (opcional) |
| `--tcp-buffer`               | 524288 (opcional) |

Si tras subir `max-connections-for-client` a 25 el juego sigue sin conectar, revisa que el **cliente VPN** (tun2socks, app en el móvil) use el puerto **8443** y que el túnel/SSH haga correctamente el forward de ese puerto.
