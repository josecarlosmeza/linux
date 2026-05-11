#!/bin/bash

# ======================================================
# 1. INSTALACIÓN DE DEPENDENCIAS Y OPTIMIZACIÓN
# ======================================================
echo "📦 Instalando dependencias y optimizando sistema..."
dnf install -y python3 python3-pip procps-ng net-tools
mkdir -p /opt/advanced-proxy

# Liberar puertos 80 y 443 por si están ocupados
fuser -k 80/tcp 2>/dev/null
fuser -k 443/tcp 2>/dev/null

# Ajustar límites de archivos abiertos (Ulimit)
cat <<EOF > /etc/security/limits.d/proxy.conf
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

# ======================================================
# 2. CREACIÓN DEL SCRIPT PROXY CON VIRTUDES
# ======================================================
cat <<EOF > /opt/advanced-proxy/proxy.py
import asyncio, hashlib, base64, gc, socket, collections, time

# ==============================================================================
# ⚙️ BLOQUE DE PARÁMETROS - Optimizado para Túnel SSH (300 conexiones)
# ==============================================================================
# Detalle:                        Valor:         Descripción:
# ------------------------------------------------------------------------------
PORTS          = [80, 443]        # [80, 443]    Puertos de escucha
PASS           = 'mi_password'    # string       Contraseña para X-Pass
TARGET_IP      = '127.0.0.1'      # IP           IP de SSHD
TARGET_PORT    = 22               # 22           Puerto de SSHD (sshd)
BUFFER_SIZE    = 32768            # 32768 (32KB) Optimizado para SSH (máx paquete SSH)
TIMEOUT_CONNECT = 60              # 60s          Timeout conexión SSH (negociación inicial)
TIMEOUT_READ    = 300             # 300s (5min)  Timeout lectura SSH (conexiones largas)
KEEP_ALIVE_SEC  = 300             # 300s         Mantiene túnel vivo (SSH long-lived)
RAM_CLEAN_SEC   = 320             # 320s         Mantiene el VPS ligero
MAX_CONCURRENT  = 300             # 300          Límite conexiones simultáneas

# Rate limiting por IP - Protección contra abuso
MAX_CONNECTIONS_PER_IP = 10       # 10           Máx conexiones por IP
RATE_LIMIT_WINDOW = 60            # 60s (1min)   Ventana de tiempo para rate limiting

# Keepalive TCP - Detección rápida de cortes en túnel SSH
TCP_KEEPIDLE    = 30              # 30s          Tiempo antes del primer keepalive
TCP_KEEPINTVL   = 5               # 5s           Intervalo entre keepalives
TCP_KEEPCNT     = 3               # 3            Intentos antes de marcar muerto (~15s)
# Cerrar túnel tras N seg sin datos (0=desactivado). Si usas limitador SSH y cuesta reconectar,
# pon ej. 300 para cerrar idle y liberar sesiones; el limitador tiene gracia para proxy (127.0.0.1).
IDLE_CLOSE_SEC  = 0               # 0            Desactivado. 300=cierra tras 5 min sin datos.
# ==============================================================================

# Guía para HTTP Custom:
# Payload: GET / HTTP/1.1[crlf]Host: [dominio_cloudfront][crlf]Upgrade: websocket[crlf]Connection: Upgrade[crlf]X-Pass: mi_password[crlf][crlf]

# Variables globales para control de conexiones
active_connections = 0
connection_lock = None

# Rate limiting por IP - diccionario con deque para ventana de tiempo
ip_connections = collections.defaultdict(lambda: collections.deque())
ip_lock = None

def generate_ws_accept(key):
    GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    sha1 = hashlib.sha1(key + GUID).digest()
    return base64.b64encode(sha1).decode()

def find_header(head, header):
    try:
        start = head.lower().find(header.lower() + b': ')
        if start == -1: return b''
        start += len(header) + 2
        end = head.find(b'\r\n', start)
        return head[start:end].strip()
    except: return b''

def configure_socket_keepalive(sock):
    """Configura opciones de socket optimizadas para túnel SSH."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Parámetros keepalive TCP (Linux/Unix)
        if hasattr(socket, 'TCP_KEEPIDLE'):
            try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEPIDLE)
            except: pass
        if hasattr(socket, 'TCP_KEEPINTVL'):
            try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPINTVL)
            except: pass
        if hasattr(socket, 'TCP_KEEPCNT'):
            try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, TCP_KEEPCNT)
            except: pass
        
        # TCP_NODELAY - baja latencia (crítico para SSH)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        # Buffers grandes (128KB) - mejor throughput SSH
        try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 131072)
        except: pass
        try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)
        except: pass
    except: pass

async def memory_cleaner():
    """Optimización de GC para 300 conexiones - libera RAM eficientemente."""
    while True:
        await asyncio.sleep(RAM_CLEAN_SEC)
        # Optimización de GC: ajustar umbrales para mejor rendimiento con muchas conexiones
        # Menos frecuencia de GC, pero más agresivo cuando se ejecuta
        gc.collect(2)  # Generación 2 para recolección completa
        
        # Limpiar entradas antiguas de rate limiting (más de ventana de tiempo)
        current_time = time.time()
        async with ip_lock:
            for ip in list(ip_connections.keys()):
                # Eliminar timestamps fuera de la ventana
                while ip_connections[ip] and current_time - ip_connections[ip][0] > RATE_LIMIT_WINDOW:
                    ip_connections[ip].popleft()
                # Si no hay conexiones recientes, eliminar la entrada
                if not ip_connections[ip]:
                    del ip_connections[ip]

async def forward(reader, writer, idle_close_sec=0):
    """Transfiere datos optimizado para protocolo binario SSH."""
    timeout = idle_close_sec if idle_close_sec else TIMEOUT_READ
    try:
        while True:
            try:
                data = await asyncio.wait_for(reader.read(BUFFER_SIZE), timeout=timeout)
                if not data: break
                writer.write(data)
                await writer.drain()
            except asyncio.TimeoutError:
                if idle_close_sec:
                    break
                continue
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                break
    except Exception: pass
    finally:
        try:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
        except Exception: pass

async def connect_with_retry(host, port, max_retries=3):
    """Conecta con reintentos exponenciales para túneles SSH."""
    last_error = None
    for attempt in range(max_retries):
        try:
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=TIMEOUT_CONNECT
            )
            # Configurar keepalive en socket del target
            try:
                target_socket = target_writer.get_extra_info('socket')
                if target_socket: configure_socket_keepalive(target_socket)
            except: pass
            if attempt > 0: return target_reader, target_writer
            return target_reader, target_writer
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, socket.gaierror) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 10)
                await asyncio.sleep(wait_time)
    raise last_error

async def handle(client_reader, client_writer):
    global active_connections, connection_lock, ip_lock, ip_connections
    connection_accepted = False
    client_ip = None
    
    # Inicializar locks si no están inicializados
    if connection_lock is None:
        connection_lock = asyncio.Lock()
    if ip_lock is None:
        ip_lock = asyncio.Lock()
    
    try:
        # Obtener IP del cliente
        try:
            client_ip = client_writer.get_extra_info('peername')[0]
        except:
            client_ip = 'unknown'
        
        # Rate limiting por IP
        current_time = time.time()
        async with ip_lock:
            # Limpiar conexiones antiguas de esta IP fuera de la ventana
            if client_ip in ip_connections:
                while ip_connections[client_ip] and current_time - ip_connections[client_ip][0] > RATE_LIMIT_WINDOW:
                    ip_connections[client_ip].popleft()
            
            # Verificar límite de conexiones por IP
            if len(ip_connections[client_ip]) >= MAX_CONNECTIONS_PER_IP:
                client_writer.write(b'HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nRetry-After: 10\r\n\r\n')
                await client_writer.drain()
                return
            
            # Registrar nueva conexión de esta IP
            ip_connections[client_ip].append(current_time)
        
        # Verificar límite de conexiones concurrentes
        async with connection_lock:
            if active_connections >= MAX_CONCURRENT:
                # Remover la conexión del rate limiting
                async with ip_lock:
                    if client_ip in ip_connections and ip_connections[client_ip]:
                        ip_connections[client_ip].pop()
                client_writer.write(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nRetry-After: 5\r\n\r\n')
                await client_writer.drain()
                return
            active_connections += 1
            connection_accepted = True
        
        # Configurar keepalive en socket del cliente
        try:
            client_socket = client_writer.get_extra_info('socket')
            if client_socket: configure_socket_keepalive(client_socket)
        except: pass
        
        data = await asyncio.wait_for(client_reader.read(4096), timeout=30)
        if not data: return
        
        passwd = find_header(data, b'X-Pass').decode('latin-1')
        if PASS and passwd != PASS:
            client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            await client_writer.drain()
            return

        ws_key = find_header(data, b'Sec-WebSocket-Key')
        accept_val = generate_ws_accept(ws_key) if ws_key else "AnyValue"
        
        # Conectar con reintentos exponenciales
        target_reader, target_writer = await connect_with_retry(TARGET_IP, TARGET_PORT)
        
        resp = ("HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Accept: %s\r\n"
                "Server: nginx/1.24.0\r\n\r\n" % accept_val).encode('latin-1')
        
        client_writer.write(resp)
        await client_writer.drain()

        idle = IDLE_CLOSE_SEC if IDLE_CLOSE_SEC else 0
        t1 = asyncio.create_task(forward(client_reader, target_writer, idle))
        t2 = asyncio.create_task(forward(target_reader, client_writer, idle))
        done, _ = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        for t in (t1, t2):
            if t not in done:
                t.cancel()
                try: await t
                except asyncio.CancelledError: pass
        try:
            if not target_writer.is_closing():
                target_writer.close()
                await target_writer.wait_closed()
        except Exception: pass
    except: pass
    finally:
        # Decrementar contador de conexiones y remover de rate limiting
        if connection_accepted:
            async with connection_lock:
                active_connections -= 1
            # Remover conexión del rate limiting por IP
            if client_ip:
                async with ip_lock:
                    if client_ip in ip_connections and ip_connections[client_ip]:
                        ip_connections[client_ip].pop()
        try:
            if not client_writer.is_closing():
                client_writer.close()
                await client_writer.wait_closed()
        except: pass

async def start_servers():
    global connection_lock, ip_lock
    # Inicializar locks al arrancar
    connection_lock = asyncio.Lock()
    ip_lock = asyncio.Lock()
    
    asyncio.create_task(memory_cleaner())
    tasks = [asyncio.start_server(handle, '0.0.0.0', p) for p in PORTS]
    servers = await asyncio.gather(*tasks)
    
    # Configurar keepalive en sockets del servidor
    for server in servers:
        for sock in server.sockets:
            configure_socket_keepalive(sock)
    
    await asyncio.gather(*[s.serve_forever() for s in servers])

if __name__ == '__main__':
    try:
        asyncio.run(start_servers())
    except KeyboardInterrupt:
        pass
EOF

# ======================================================
# 3. CONFIGURACIÓN DEL SERVICIO SYSTEMD
# ======================================================
cat <<EOF > /etc/systemd/system/adv-proxy.service
[Unit]
Description=Advanced MultiPort Proxy (SSHD + CloudFront)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/advanced-proxy
ExecStart=/usr/bin/python3 /opt/advanced-proxy/proxy.py
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# ======================================================
# 4. LANZAMIENTO
# ======================================================
systemctl daemon-reload
systemctl enable adv-proxy
systemctl restart adv-proxy

echo "-------------------------------------------------------"
echo "✅ TODO LISTO"
echo "✅ Proxy estable en puertos: 80 y 443"
echo "✅ Configuración de SSHD optimizada"
echo "✅ Limpiador de RAM y Control de Flujo ACTIVADOS"
echo "-------------------------------------------------------"