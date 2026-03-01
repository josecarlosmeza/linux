# UDP-PY - Modo de Uso Detallado

Guía completa de parámetros y configuración del servidor UDPGW.

---

## Ejecución básica

```bash
python3 udpgw_server.py [PARÁMETROS]
```

O con systemd:
```bash
systemctl start udpgw-py
```

---

## Parámetros detallados

### `--listen-addr DIRECCION:PUERTO`
**Por defecto:** `127.0.0.1:53`

**Descripción:** Dirección IP y puerto TCP donde el servidor escuchará conexiones.

- `127.0.0.1:53` – Solo acceso local (ideal cuando hay proxy/SSH delante).
- `0.0.0.0:53` – Escucha en todas las interfaces (acceso externo).
- `192.168.1.10:7300` – Escucha en una IP concreta y puerto distinto.

**Detalle:** El protocolo UDPGW funciona sobre TCP. Los clientes (tun2socks, etc.) se conectan a esta dirección. Si usas un túnel SSH, normalmente se hace port-forward del puerto local al servidor.

---

### `--loglevel NIVEL`
**Por defecto:** `error`

**Valores:** `debug` | `info` | `warning` | `error` | `none`

**Descripción:** Nivel de verbosidad de los logs.

| Valor    | Uso |
|----------|-----|
| `debug`  | Todo el tráfico y decisiones internas. Solo para depuración. |
| `info`   | Eventos importantes (inicio, estadísticas, cierre). |
| `warning`| Advertencias (máx. clientes, errores recuperables). |
| `error`  | Solo errores. Recomendado en producción. |
| `none`   | Sin logs. Mínimo uso de CPU. |

---

### `--max-clients N`
**Por defecto:** `1000`

**Descripción:** Número máximo de conexiones TCP simultáneas aceptadas.

Cada usuario VPN suele abrir 1 conexión TCP. Si superas este límite, las nuevas conexiones se rechazan y se registra un warning.

**Para 300 usuarios:** `350` o `400` (margen de seguridad).

---

### `--max-connections-for-client N`
**Por defecto:** `10`

**Descripción:** Número máximo de port-forwards UDP (destinos distintos) por cada cliente TCP.

Cada conexión DNS, juego, videollamada, etc., puede crear un port-forward. Si un cliente supera este valor, las nuevas solicitudes se ignoran.

**Para 300 usuarios:** `8` a `12`. Valores más altos permiten más apps por usuario; más bajos reducen recursos.

---

### `--client-timeout SEGUNDOS`
**Por defecto:** `300` (5 minutos)

**Valor 0:** Sin timeout (conexión abierta hasta que el cliente cierre).

**Descripción:** Tiempo máximo de inactividad (sin recibir datos) antes de cerrar la conexión del cliente.

Sirve para liberar conexiones de clientes que se desconectaron sin cerrar bien (móvil en sleep, corte de red, etc.).

**Para 300 usuarios:** `300` a `600` (5–10 min). Más tiempo mantiene conexiones largas; menos libera recursos antes.

---

### `--udp-timeout SEGUNDOS`
**Por defecto:** `30.0`

**Descripción:** Timeout del socket UDP que reenvía datos a destinos externos (DNS, juegos, etc.).

Si un destino no responde en ese tiempo, el `recv` del socket UDP hace timeout y se reintenta en la siguiente interacción. Evita bloqueos indefinidos.

**Para 300 usuarios:** `30` está bien. En redes lentas puedes subir a `45`.

---

### `--stats-interval SEGUNDOS`
**Por defecto:** `0` (desactivado)

**Descripción:** Si es mayor que 0, cada N segundos se escribe en el log: clientes activos y total desde el inicio.

Útil para monitoreo sin añadir herramientas externas.

**Para 300 usuarios:** `60` o `120` para ver tendencias sin saturar logs.

---

### `--tcp-buffer BYTES`
**Por defecto:** `262144` (256 KB)

**Valor 0:** Usa el valor por defecto del sistema operativo.

**Descripción:** Tamaño del buffer de recepción y envío del socket TCP.

Buffers grandes ayudan en picos de tráfico y evitan pérdida de paquetes. Buffers pequeños reducen memoria por conexión.

**Para 300 usuarios:** `524288` (512 KB) o `1048576` (1 MB).

---

### `--udp-buffer BYTES`
**Por defecto:** `131072` (128 KB)

**Valor 0:** Usa el valor por defecto del sistema operativo.

**Descripción:** Tamaño del buffer de cada socket UDP que reenvía tráfico hacia destinos externos.

Influye en la capacidad de absorber ráfagas de tráfico (juegos, streaming) sin descartar paquetes.

**Para 300 usuarios:** `262144` (256 KB).

---

### `--no-tcp-nodelay`
**Por defecto:** No activado (TCP_NODELAY sí está activo).

**Descripción:** Desactiva TCP_NODELAY (vuelve a usar el algoritmo de Nagle).

Con Nagle, los paquetes pequeños se agrupan, lo que aumenta la latencia. Solo recomendable si tienes problemas concretos de rendimiento.

---

### `--no-keepalive`
**Por defecto:** No activado (keepalive activo).

**Descripción:** Desactiva TCP keepalive.

Sin keepalive, las conexiones “colgadas” (cliente caído, red cortada) pueden quedar abiertas mucho tiempo. Solo usar si el entorno ya gestiona esto de otra forma.

---

## Parámetros recomendados para ~300 usuarios

```bash
python3 udpgw_server.py \
  --listen-addr 127.0.0.1:53 \
  --loglevel error \
  --max-clients 350 \
  --max-connections-for-client 10 \
  --client-timeout 600 \
  --udp-timeout 30 \
  --stats-interval 120 \
  --tcp-buffer 524288 \
  --udp-buffer 262144
```

### Resumen para 300 usuarios

| Parámetro                    | Valor  | Motivo |
|-----------------------------|--------|--------|
| `--max-clients`             | 350    | Margen sobre 300 usuarios. |
| `--max-connections-for-client` | 10  | Suficiente para varias apps por usuario. |
| `--client-timeout`          | 600    | 10 min; libera conexiones inactivas. |
| `--tcp-buffer`              | 524288 | 512 KB para picos de tráfico. |
| `--udp-buffer`              | 262144 | 256 KB para reenvío UDP. |
| `--stats-interval`          | 120    | Estadísticas cada 2 min. |
| `--loglevel`                | error  | Menos logs, menos CPU. |

### Línea única para copiar

```bash
python3 udpgw_server.py --listen-addr 127.0.0.1:53 --loglevel error --max-clients 350 --max-connections-for-client 10 --client-timeout 600 --udp-timeout 30 --stats-interval 120 --tcp-buffer 524288 --udp-buffer 262144
```

---

## Integración con systemd

Edita `/etc/systemd/system/udpgw-py.service` y ajusta la línea `ExecStart`:

```ini
ExecStart=/usr/bin/python3 /opt/udp-py/udpgw_server.py --listen-addr 127.0.0.1:53 --loglevel error --max-clients 350 --max-connections-for-client 10 --client-timeout 600 --udp-timeout 30 --stats-interval 120 --tcp-buffer 524288 --udp-buffer 262144
```

Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl restart udpgw-py
```

---

## Ver ayuda en consola

```bash
python3 udpgw_server.py --help
```
