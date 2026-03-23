"""
Ajustes opcionales de sockets para Linux (AlmaLinux, RHEL, Fedora, etc.):
menor latencia en el túnel TCP y buffers más amplios para muchos datagramas UDP.

No tiene efecto en Windows u otros sistemas.
"""

from __future__ import annotations

import socket
import sys

_TCP_QUICKACK = getattr(socket, "TCP_QUICKACK", 12)


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def tune_tcp_client_for_udppy(sock: socket.socket) -> None:
    """Conexión TCP hacia tun2socks (udppy): paquetes pequeños, ida y vuelta frecuente."""
    if not is_linux():
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, _TCP_QUICKACK, 1)
    except OSError:
        pass
    try:
        size = 4 * 1024 * 1024
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    except OSError:
        pass


def tune_udp_relay_socket(sock: socket.socket) -> None:
    """Socket UDP conectado hacia el destino remoto."""
    if not is_linux():
        return
    try:
        size = 4 * 1024 * 1024
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    except OSError:
        pass
