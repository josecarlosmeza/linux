# Proyecto udppy — compatibilidad con protocol/udpgw_proto.h de badvpn (ambrop72/badvpn).
# Valores y tamaños deben coincidir con el daemon udpgw en C.

from __future__ import annotations

import socket
import struct

# Flags (uint8 en el cliente; mismo bit en servidor). Idénticos a UDPGW_CLIENT_FLAG_* en badvpn.
UDPPY_FLAG_KEEPALIVE = 1 << 0
UDPPY_FLAG_REBIND = 1 << 1
UDPPY_FLAG_DNS = 1 << 2
UDPPY_FLAG_IPV6 = 1 << 3

HEADER_SIZE = 3  # uint8 flags + uint16 conid (little-endian, empaquetado)
ADDR_IPV4_SIZE = 6  # uint32 ip + uint16 port (orden de red)
ADDR_IPV6_SIZE = 18  # 16 bytes ip + uint16 port

DEFAULT_UDP_MTU = 65520


def udppy_compute_mtu(dgram_mtu: int) -> int:
    """MTU del mensaje encapsulado (equiv. a udpgw_compute_mtu() en udpgw_proto.h de badvpn)."""
    return HEADER_SIZE + max(ADDR_IPV4_SIZE, ADDR_IPV6_SIZE) + dgram_mtu


def parse_udppy_header(data: bytes) -> tuple[int, int, int]:
    """Devuelve (flags, conid, bytes_consumidos)."""
    if len(data) < HEADER_SIZE:
        raise ValueError("cabecera de protocolo incompleta")
    flags = data[0]
    conid = struct.unpack_from("<H", data, 1)[0]
    return flags, conid, HEADER_SIZE


def pack_udppy_header(flags: int, conid: int) -> bytes:
    return struct.pack("<BH", flags & 0xFF, conid & 0xFFFF)


def parse_udppy_addr_ipv4(data: bytes) -> tuple[str, int, int]:
    """Devuelve (ip_dotted, port_host, bytes_consumidos)."""
    if len(data) < ADDR_IPV4_SIZE:
        raise ValueError("dirección IPv4 incompleta")
    ip_net = data[0:4]
    port = struct.unpack_from("!H", data, 4)[0]

    host = socket.inet_ntoa(ip_net)
    return host, port, ADDR_IPV4_SIZE


def parse_udppy_addr_ipv6(data: bytes) -> tuple[str, int, int]:
    if len(data) < ADDR_IPV6_SIZE:
        raise ValueError("dirección IPv6 incompleta")
    ip6 = data[0:16]
    port = struct.unpack_from("!H", data, 16)[0]
    host = socket.inet_ntop(socket.AF_INET6, ip6)
    return host, port, ADDR_IPV6_SIZE


def pack_udppy_addr_ipv4(host: str, port: int) -> bytes:
    ip = socket.inet_aton(host)
    return ip + struct.pack("!H", port)


def pack_udppy_addr_ipv6(host: str, port: int) -> bytes:
    ip6 = socket.inet_pton(socket.AF_INET6, host)
    return ip6 + struct.pack("!H", port)


def pack_udppy_to_client(
    flags: int,
    conid: int,
    orig_host: str,
    orig_port: int,
    payload: bytes,
    *,
    ipv6: bool,
) -> bytes:
    """Construye un mensaje compatible con udpgw (sin enmarcar PacketProto)."""
    if ipv6:
        flags = flags | UDPPY_FLAG_IPV6
        addr = pack_udppy_addr_ipv6(orig_host, orig_port)
    else:
        addr = pack_udppy_addr_ipv4(orig_host, orig_port)
    return pack_udppy_header(flags, conid) + addr + payload
