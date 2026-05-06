# SSH: no llegan peticiones cuando juegas (Free Fire, etc.)

Si conectas por **SSH** y al abrir Free Fire (u otro juego) **en el servidor no aparece ninguna conexión** al UDPGW, la causa suele ser que el **cliente no está reenviando el puerto 8443** al servidor.

---

## Cómo tiene que ser el flujo

1. En el **servidor**: UDPGW escucha en `127.0.0.1:8443` (TCP).
2. En el **cliente** (móvil/PC): la app (HTTP Custom, etc.) se conecta por SSH al servidor.
3. Para que el **UDP del juego** llegue al UDPGW, la app debe:
   - Abrir en el cliente un **túnel local** tipo: “puerto local 8443 → servidor 127.0.0.1:8443”.
   - Eso en SSH se hace con **port forwarding**: `-L 8443:127.0.0.1:8443`.
4. La app debe tener configurado el **UDP gateway** en `127.0.0.1:8443` (en el cliente), para que el tráfico UDP pase por ese túnel TCP hasta el servidor.

Si la app **no** hace ese forward de 8443, cuando abres el juego **ninguna conexión TCP** llegará al puerto 8443 del servidor, y por tanto no verás peticiones en el servidor.

---

## Qué revisar en el cliente (HTTP Custom u otra app)

1. **Que exista “UDP” o “UDP gateway”**  
   Debe estar activado o configurado; si solo usas proxy SOCKS/HTTP, el juego (UDP) no pasa por el túnel.

2. **Puerto del UDP gateway = 8443**  
   Si la app usa otro puerto por defecto (por ejemplo 7300 o 7555), cámbialo a **8443** para que coincida con el servidor.

3. **Que la app haga forward del puerto 8443 por SSH**  
   Depende de la app:
   - Algunas tienen opción tipo “Forward port”, “UDP port”, “Local port for UDP gateway” o “Puerto túnel UDP”.
   - Debe quedar algo equivalente a: en el cliente, puerto **8443** reenviado a **127.0.0.1:8443** del servidor (vía SSH).

Si la app **no** permite configurar ese forward, no podrá enviar el tráfico UDP del juego al UDPGW del servidor y seguirás sin ver peticiones por SSH.

---

## Cómo comprobarlo en el servidor

En el servidor ejecuta:

```bash
sudo systemctl stop udpgw-py
/usr/bin/python3 /opt/udp-py/udpgw_server.py --listen-addr 127.0.0.1:8443 --loglevel info --max-connections-for-client 25
```

- Con la **app conectada por SSH** y el **UDP gateway en 127.0.0.1:8443** en el cliente, al abrir Free Fire deberías ver líneas como:
  - `Conexión entrante desde 127.0.0.1:xxxxx`
- Si **nunca** aparece “Conexión entrante”, el túnel del puerto 8443 no se está estableciendo (revisar app/cliente como arriba).

---

## Resumen

| Síntoma | Causa probable |
|--------|-----------------|
| No llega ninguna petición al servidor al jugar | El cliente no hace forward del puerto **8443** por SSH. |
| Solo funciona navegación, no el juego | La app no tiene activado/configurado el **UDP gateway** o no usa el puerto 8443. |

**Acción:** En la app del cliente (HTTP Custom, etc.) activar/ajustar el **UDP gateway** y asegurar que el **puerto 8443** se reenvíe por SSH al servidor (equivalente a `-L 8443:127.0.0.1:8443`).
