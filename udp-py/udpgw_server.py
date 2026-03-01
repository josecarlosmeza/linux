#!/usr/bin/env python3
"""
UDPGW Server - Implementación en Python pura compatible con badvpn-udpgw.
Protocolo basado en BadVPN (ambrop72) y Psiphon-Tunnel-Core.
Escucha en TCP y reenvía paquetes UDP sobre el túnel.
"""

import socket
import struct
import threading
import logging
import signal
import sys
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

# Constantes del protocolo UDPGW
FLAG_KEEPALIVE = 1 << 0

# Buffer sizes para estabilidad (bytes)
DEFAULT_TCP_BUFFER = 256 * 1024   # 256 KB
DEFAULT_UDP_BUFFER = 128 * 1024   # 128 KB
FLAG_REBIND = 1 << 1
FLAG_DNS = 1 << 2
FLAG_IPV6 = 1 << 3
MAX_PREAMBLE_SIZE = 23
MAX_PAYLOAD_SIZE = 32768
MAX_MESSAGE_SIZE = MAX_PREAMBLE_SIZE + MAX_PAYLOAD_SIZE


@dataclass
class UdpgwMessage:
    """Mensaje del protocolo UDPGW."""
    conn_id: int
    remote_ip: bytes
    remote_port: int
    discard_existing: bool
    forward_dns: bool
    packet: bytes
    preamble_size: int


def _configure_socket_stability(
    sock: socket.socket,
    tcp_nodelay: bool = True,
    tcp_keepalive: bool = True,
    buffer_size: int = 0,
) -> None:
    """Configura opciones de socket para mayor estabilidad de conexión."""
    try:
        if tcp_nodelay and hasattr(socket, "TCP_NODELAY"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if tcp_keepalive:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if buffer_size > 0:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buffer_size)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, buffer_size)
    except OSError:
        pass


def read_udpgw_message(conn: socket.socket, buffer: bytearray) -> Optional[UdpgwMessage]:
    """
    Lee un mensaje UDPGW del socket.
    Formato: | 2 bytes size (LE) | 1 byte flags | 2 bytes connID (LE) | 6/18 bytes addr | packet |
    """
    try:
        header = conn.recv(2)
        if len(header) < 2:
            return None
        size = struct.unpack_from("<H", header)[0]

        if size < 3 or size > len(buffer) - 2:
            return None

        data = b""
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                return None
            data += chunk

        flags = data[0]
        conn_id = struct.unpack_from("<H", data, 1)[0]

        # Ignorar keepalive
        if flags & FLAG_KEEPALIVE:
            return read_udpgw_message(conn, buffer)

        if flags & FLAG_IPV6:
            if size < 21:
                return None
            remote_ip = bytes(data[5:21])
            remote_port = struct.unpack_from(">H", data, 21)[0]
            header_len = 21  # 1 + 2 + 16 + 2
        else:
            if size < 9:
                return None
            remote_ip = bytes(data[5:9])
            remote_port = struct.unpack_from(">H", data, 9)[0]
            header_len = 9   # 1 + 2 + 4 + 2

        packet = bytes(data[header_len:size])
        # preamble_size = 2 (size) + 1 (flags) + 2 (connID) + addr = 7 + len(remote_ip)
        preamble_size = 7 + len(remote_ip)

        return UdpgwMessage(
            conn_id=conn_id,
            remote_ip=remote_ip,
            remote_port=remote_port,
            discard_existing=bool(flags & FLAG_REBIND),
            forward_dns=bool(flags & FLAG_DNS),
            packet=packet,
            preamble_size=preamble_size
        )
    except (socket.error, struct.error, OSError):
        return None


def write_udpgw_response(
    buffer: bytearray,
    preamble_size: int,
    flags: int,
    conn_id: int,
    remote_ip: bytes,
    remote_port: int,
    packet_size: int
) -> int:
    """Escribe el preámbulo UDPGW en el buffer. Retorna tamaño total del mensaje."""
    size = preamble_size - 2 + packet_size
    struct.pack_into("<H", buffer, 0, size)
    buffer[2] = flags
    struct.pack_into("<H", buffer, 3, conn_id)
    buffer[5:5 + len(remote_ip)] = remote_ip
    struct.pack_into(">H", buffer, 5 + len(remote_ip), remote_port)
    return preamble_size + packet_size


class PortForward:
    """Mantiene un port forward UDP activo."""

    def __init__(
        self,
        conn_id: int,
        preamble_size: int,
        remote_ip: bytes,
        remote_port: int,
        udp_socket: socket.socket,
        client_conn: socket.socket,
        write_lock: threading.Lock,
        client_addr: str
    ):
        self.conn_id = conn_id
        self.preamble_size = preamble_size
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.udp_socket = udp_socket
        self.client_conn = client_conn
        self.write_lock = write_lock
        self.client_addr = client_addr
        self._closed = False
        self.relay_thread: Optional[threading.Thread] = None

    def close(self):
        self._closed = True
        try:
            self.udp_socket.close()
        except OSError:
            pass

    def relay_downstream(self):
        """Lee paquetes UDP del destino y los envía al cliente."""
        buffer = bytearray(MAX_MESSAGE_SIZE)
        packet_buffer = buffer[self.preamble_size:MAX_MESSAGE_SIZE]
        try:
            while not self._closed:
                try:
                    size = self.udp_socket.recv_into(packet_buffer)
                except (OSError, ConnectionResetError):
                    break
                if size <= 0:
                    break
                if size > MAX_PAYLOAD_SIZE:
                    continue

                total = write_udpgw_response(
                    buffer, self.preamble_size, 0,
                    self.conn_id, self.remote_ip, self.remote_port, size
                )
                with self.write_lock:
                    try:
                        self.client_conn.sendall(buffer[:total])
                    except (OSError, BrokenPipeError):
                        break
        finally:
            self.close()


class UdpgwHandler:
    """Manejador de conexiones UDPGW."""

    def __init__(self, client_conn: socket.socket, client_addr: Tuple, config: dict):
        self.client_conn = client_conn
        self.client_addr = client_addr
        self.config = config
        self.port_forwards: Dict[int, PortForward] = {}
        self.port_forwards_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.last_activity = time.monotonic()

    def run(self):
        buffer = bytearray(MAX_MESSAGE_SIZE)
        try:
            # Timeout para evitar bloqueo por clientes lentos o inactivos
            ct = self.config.get("client_timeout")
            if ct is not None:
                self.client_conn.settimeout(ct)
            while True:
                msg = read_udpgw_message(self.client_conn, buffer)
                if msg is None:
                    break
                self.last_activity = time.monotonic()

                with self.port_forwards_lock:
                    pf = self.port_forwards.get(msg.conn_id)

                if pf is not None and (
                    msg.discard_existing or
                    pf.remote_ip != msg.remote_ip or
                    pf.remote_port != msg.remote_port
                ):
                    pf.close()
                    if pf.relay_thread and pf.relay_thread.is_alive():
                        pf.relay_thread.join(timeout=2)
                    with self.port_forwards_lock:
                        self.port_forwards.pop(msg.conn_id, None)
                    pf = None

                if pf is None:
                    # Respetar límite de conexiones por cliente
                    max_conn = self.config.get("max_connections", 10)
                    if len(self.port_forwards) >= max_conn:
                        if logging.getLogger().level <= logging.DEBUG:
                            logging.debug("Cliente %s excede max_connections=%d", self.client_addr, max_conn)
                        continue
                    try:
                        udp = socket.socket(
                            socket.AF_INET6 if len(msg.remote_ip) == 16 else socket.AF_INET,
                            socket.SOCK_DGRAM
                        )
                        udp.settimeout(self.config.get("udp_timeout", 30.0))
                        # Buffer mayor para evitar pérdida en picos de tráfico
                        ub = self.config.get("udp_buffer_size", 0)
                        if ub > 0:
                            try:
                                udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, ub)
                                udp.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, ub)
                            except OSError:
                                pass
                    except (OSError, ValueError):
                        continue

                    pf = PortForward(
                        msg.conn_id, msg.preamble_size,
                        msg.remote_ip, msg.remote_port,
                        udp, self.client_conn, self.write_lock, str(self.client_addr)
                    )
                    t = threading.Thread(target=pf.relay_downstream, daemon=True)
                    pf.relay_thread = t
                    with self.port_forwards_lock:
                        self.port_forwards[msg.conn_id] = pf
                    t.start()

                try:
                    pf.udp_socket.sendto(msg.packet, (
                        socket.inet_ntop(
                            socket.AF_INET6 if len(msg.remote_ip) == 16 else socket.AF_INET,
                            msg.remote_ip
                        ),
                        msg.remote_port
                    ))
                except OSError:
                    pf.close()
        finally:
            with self.port_forwards_lock:
                for pf in list(self.port_forwards.values()):
                    pf.close()
                    if pf.relay_thread and pf.relay_thread.is_alive():
                        pf.relay_thread.join(timeout=2)
                self.port_forwards.clear()
        finally:
            try:
                self.client_conn.close()
            except OSError:
                pass


_shutdown = False
_client_count = 0
_total_connections = 0
_client_count_lock = threading.Lock()
_last_stats_time = 0


def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True


def main():
    import argparse
    global _shutdown, _client_count, _total_connections, _last_stats_time
    parser = argparse.ArgumentParser(description="UDPGW Server en Python")
    parser.add_argument("--listen-addr", default="127.0.0.1:53", help="Dirección:puerto para escuchar")
    parser.add_argument("--loglevel", default="error", choices=["debug", "info", "warning", "error", "none"])
    parser.add_argument("--max-clients", type=int, default=1000)
    parser.add_argument("--max-connections-for-client", type=int, default=10)
    parser.add_argument("--client-timeout", type=int, default=300,
                        help="Segundos de inactividad antes de cerrar cliente (0=infinito)")
    parser.add_argument("--udp-timeout", type=float, default=30.0,
                        help="Timeout en socket UDP para respuestas (segundos)")
    parser.add_argument("--stats-interval", type=int, default=0,
                        help="Intervalo en segundos para mostrar estadísticas (0=desactivado)")
    parser.add_argument("--tcp-buffer", type=int, default=DEFAULT_TCP_BUFFER,
                        help="Buffer TCP en bytes (0=default del SO). Recomendado: 262144")
    parser.add_argument("--udp-buffer", type=int, default=DEFAULT_UDP_BUFFER,
                        help="Buffer UDP en bytes (0=default). Recomendado: 131072")
    parser.add_argument("--no-tcp-nodelay", action="store_true",
                        help="Desactivar TCP_NODELAY (Nagle). Por defecto está activo para menor latencia")
    parser.add_argument("--no-keepalive", action="store_true",
                        help="Desactivar TCP keepalive (detección de conexiones muertas)")
    args = parser.parse_args()

    if args.loglevel != "none":
        logging.basicConfig(
            level=getattr(logging, args.loglevel.upper()),
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
    else:
        logging.disable(logging.CRITICAL)

    host, port_str = args.listen_addr.rsplit(":", 1)
    port = int(port_str)

    config = {
        "max_clients": args.max_clients,
        "max_connections": args.max_connections_for_client,
        "client_timeout": args.client_timeout if args.client_timeout > 0 else None,
        "udp_timeout": args.udp_timeout,
        "tcp_buffer_size": args.tcp_buffer,
        "udp_buffer_size": args.udp_buffer,
        "tcp_nodelay": not args.no_tcp_nodelay,
        "tcp_keepalive": not args.no_keepalive,
    }

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sb = args.tcp_buffer
    if sb > 0:
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, sb)
        except OSError:
            pass
    server.bind((host, port))
    server.listen(64)

    if args.loglevel != "none":
        logging.info("UDPGW Server escuchando en %s:%d", host, port)

    stats_interval = args.stats_interval
    _last_stats_time = time.monotonic()
    while not _shutdown:
        try:
            server.settimeout(1.0)  # Permite revisar _shutdown cada segundo
            conn, addr = server.accept()
        except socket.timeout:
            # Estadísticas periódicas
            if stats_interval > 0 and args.loglevel != "none":
                now = time.monotonic()
                if now - _last_stats_time >= stats_interval:
                    _last_stats_time = now
                    with _client_count_lock:
                        logging.info("Stats: activos=%d total=%d", _client_count, _total_connections)
            continue
        except OSError as e:
            if _shutdown:
                break
            if args.loglevel != "none":
                logging.error("Error aceptando: %s", e)
            continue

        with _client_count_lock:
            if _client_count >= args.max_clients:
                if args.loglevel != "none":
                    logging.warning("Max clientes (%d) alcanzado, rechazando %s", args.max_clients, addr)
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            _client_count += 1
            _total_connections += 1

        # Optimizaciones de estabilidad en la conexión TCP
        _configure_socket_stability(
            conn,
            tcp_nodelay=config.get("tcp_nodelay", True),
            tcp_keepalive=config.get("tcp_keepalive", True),
            buffer_size=config.get("tcp_buffer_size", 0),
        )

        def run_and_decrement():
            global _client_count
            try:
                handler = UdpgwHandler(conn, addr, config)
                handler.run()
            finally:
                with _client_count_lock:
                    _client_count -= 1

        t = threading.Thread(target=run_and_decrement, daemon=True)
        t.start()

    server.close()
    if args.loglevel != "none":
        logging.info("Servidor detenido correctamente (SIGTERM/SIGINT)")


if __name__ == "__main__":
    main()
