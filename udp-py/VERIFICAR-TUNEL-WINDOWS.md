# Verificar túnel desde Windows: no aparece "Conexión entrante"

Si `Test-NetConnection 127.0.0.1 -Port 8443` da **True** pero en el VPS **no** sale "Conexión entrante desde 127.0.0.1:xxxx", suele ser que en el PC **no** está entrando por el túnel SSH.

---

## 1. Comprobar quién usa el puerto 8443 en Windows

En **PowerShell**:

**A) Sin tener abierto ningún SSH:**

```powershell
netstat -an | findstr 8443
```

- Si sale alguna línea con `8443` → otro programa está usando el puerto. Cierra ese programa o usa otro puerto (ej. 9443).

**B) Con el túnel SSH abierto** (`ssh -L 8443:127.0.0.1:8443 usuario@IP_VPS`):

```powershell
netstat -an | findstr 8443
```

Deberías ver algo como `127.0.0.1:8443` en estado **LISTENING**. Si no aparece, el `-L 8443` no se aplicó (revisa el comando SSH).

---

## 2. Orden correcto de la prueba

1. **En el VPS:** arrancar el servidor y dejarlo corriendo:
   ```bash
   /usr/bin/python3 /opt/udp-py/udpgw_server.py --listen-addr 127.0.0.1:8443 --loglevel info
   ```

2. **En Windows:** abrir **una** PowerShell y ejecutar (y no cerrar):
   ```powershell
   ssh -L 8443:127.0.0.1:8443 root@IP_DEL_VPS
   ```
   Dejar esta ventana abierta y conectada.

3. **En Windows:** abrir **otra** PowerShell y ejecutar:
   ```powershell
   Test-NetConnection -ComputerName 127.0.0.1 -Port 8443
   ```

4. **En el VPS:** en la consola del `udpgw_server.py` debe aparecer:
   ```text
   Conexión entrante desde 127.0.0.1:xxxxx
   ```

Si en el paso 2 no usas `-L 8443:127.0.0.1:8443`, la conexión del paso 3 no llega al UDPGW y por eso no aparece la línea.

---

## 3. Si sigue sin aparecer

- Confirma en el VPS que **no** haya otro proceso escuchando en 8443:
  ```bash
  ss -tlnp | grep 8443
  ```
  Debe salir solo el proceso de `udpgw_server.py`.

- En Windows, prueba a usar **otro puerto local** por si 8443 está ocupado:
  ```powershell
  ssh -L 9443:127.0.0.1:8443 root@IP_DEL_VPS
  ```
  Luego:
  ```powershell
  Test-NetConnection -ComputerName 127.0.0.1 -Port 9443
  ```
  En el VPS debería seguir apareciendo "Conexión entrante desde 127.0.0.1:xxxx" (el servidor sigue en 8443).
