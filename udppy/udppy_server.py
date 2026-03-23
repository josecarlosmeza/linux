#!/usr/bin/env python3
"""
udppy — servidor compatible con badvpn udpgw (PacketProto + formato udpgw).

Sustituye al binario `udpgw` del proyecto ambrop72/badvpn: los clientes tun2socks
se conectan por TCP (a menudo vía SOCKS) y envían tráfico UDP encapsulado.

En Linux (AlmaLinux, RHEL, etc.) se aplican por defecto ajustes de socket
(TCP_NODELAY, TCP_QUICKACK, buffers); use --no-linux-tune para desactivarlos.
En Linux se usa uvloop por defecto si está instalado (pip install uvloop); use --no-uvloop para asyncio estándar.

Uso típico:
  python udppy_server.py --listen-addr 0.0.0.0:7300 --dns 8.8.8.8:53

En Windows conviene fijar --dns; en Linux también si no hay resolv.conf usable.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import struct
import sys
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional

import linux_tune
import udppy_proto as P

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

CLIENT_DISCONNECT_TIMEOUT = 20.0

# En main() se fija si uvloop.install() se aplicó antes de asyncio.run
_uvloop_installed = False

# PacketProto: uint16 LE longitud + payload (protocol/packetproto.h)
PACKETPROTO_MAXPAYLOAD = 0xFFFF


class PacketProtoReader:
    """Decodifica flujo TCP en mensajes PacketProto."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)

    def pop_packets(self) -> list[bytes]:
        out: list[bytes] = []
        while len(self._buf) >= 2:
            plen = struct.unpack_from("<H", self._buf, 0)[0]
            if plen > PACKETPROTO_MAXPAYLOAD:
                raise ValueError(f"PacketProto: longitud inválida {plen}")
            if len(self._buf) < 2 + plen:
                break
            payload = bytes(self._buf[2 : 2 + plen])
            del self._buf[: 2 + plen]
            out.append(payload)
        return out


def _addr_equal(
    a_ip: str, a_port: int, b_ip: str, b_port: int, *, ipv6: bool
) -> bool:
    """Equivalente a BAddr_Compare == 1 (direcciones iguales)."""
    if a_port != b_port:
        return False
    if ipv6:
        return (
            socket.inet_pton(socket.AF_INET6, a_ip)
            == socket.inet_pton(socket.AF_INET6, b_ip)
        )
    return socket.inet_aton(a_ip) == socket.inet_aton(b_ip)


class UdppyConnection:
    """Conexión lógica udppy (conid) con un socket UDP hacia el destino (protocolo udpgw)."""

    def __init__(
        self,
        *,
        client: "TcpClientSession",
        conid: int,
        orig_ip: str,
        orig_port: int,
        orig_ipv6: bool,
        target_ip: str,
        target_port: int,
        udp_mtu: int,
        udppy_mtu: int,
        linux_tune_sockets: bool,
    ) -> None:
        self.client = client
        self.conid = conid
        self.orig_ip = orig_ip
        self.orig_port = orig_port
        self.orig_ipv6 = orig_ipv6
        self.target_ip = target_ip
        self.target_port = target_port
        self.udp_mtu = udp_mtu
        self.udppy_mtu = udppy_mtu
        self._linux_tune_sockets = linux_tune_sockets

        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[asyncio.DatagramProtocol] = None
        self._closed = False
        self._last_use = time.monotonic()
        self._idle_task: Optional[asyncio.Task] = None

    def touch(self) -> None:
        self._last_use = time.monotonic()

    def start_idle_watcher(self) -> None:
        if self._idle_task is not None:
            return

        async def watch() -> None:
            try:
                while not self._closed:
                    await asyncio.sleep(2.0)
                    if self._closed:
                        return
                    if time.monotonic() - self._last_use > CLIENT_DISCONNECT_TIMEOUT:
                        await self.close()
                        return
            except asyncio.CancelledError:
                return

        self._idle_task = asyncio.create_task(watch())

    async def setup_udp(self) -> None:
        loop = asyncio.get_running_loop()
        # create_datagram_endpoint con remote_addr enlaza y conecta (compatible con asyncio)
        t, p = await loop.create_datagram_endpoint(
            lambda: _UdppyUdpProtocol(self),
            remote_addr=(self.target_ip, self.target_port),
        )
        self._transport = t
        self._protocol = p
        if self._linux_tune_sockets:
            usock = t.get_extra_info("socket")
            if usock is not None:
                linux_tune.tune_udp_relay_socket(usock)
        self.start_idle_watcher()

    def send_udp(self, data: bytes) -> None:
        if self._closed or not self._transport:
            return
        self.touch()
        # Python 3.12+: DatagramTransport solo expone sendto(); antes existía send().
        trans = self._transport
        sendto = getattr(trans, "sendto", None)
        if sendto is not None:
            sendto(data)
        else:
            trans.send(data)

    async def recv_from_udp(self, data: bytes) -> None:
        if self._closed:
            return
        self.touch()
        await self.client.send_udppy_reply(
            self,
            flags=0,
            payload=data,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
        if self._transport:
            self._transport.close()
            self._transport = None
        await self.client.remove_connection(self.conid)


class _UdppyUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, con: UdppyConnection) -> None:
        self._con = con

    def datagram_received(self, data: bytes, addr) -> None:
        asyncio.create_task(self._con.recv_from_udp(data))

    def error_received(self, exc: Exception) -> None:
        logging.debug("UDP error conid=%s: %s", self._con.conid, exc)

class TcpClientSession:
    """Cliente TCP (sesión tun2socks / protocolo udpgw)."""

    def __init__(
        self,
        reader: "StreamReader",
        writer: "StreamWriter",
        *,
        udp_mtu: int,
        udppy_mtu: int,
        dns_host: Optional[str],
        dns_port: Optional[int],
        max_connections: int,
        linux_tune_sockets: bool,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.udp_mtu = udp_mtu
        self.udppy_mtu = udppy_mtu
        self.dns_host = dns_host
        self.dns_port = dns_port
        self.max_connections = max_connections
        self._linux_tune_sockets = linux_tune_sockets

        self._pp = PacketProtoReader()
        self._lock = asyncio.Lock()
        # conid -> conexión (LRU: OrderedDict move_to_end en uso)
        self._by_conid: "OrderedDict[int, UdppyConnection]" = OrderedDict()
        self._closed = False

    async def _resolve_target(
        self, host: str, port: int
    ) -> tuple[str, int, bool]:
        return await _resolve_udp(host, port)

    async def run(self) -> None:
        peer = self.writer.get_extra_info("peername")
        logging.info("Cliente TCP conectado: %s", peer)
        if self._linux_tune_sockets:
            tsock = self.writer.get_extra_info("socket")
            if tsock is not None:
                linux_tune.tune_tcp_client_for_udppy(tsock)
        try:
            while True:
                data = await self.reader.read(65536)
                if not data:
                    break
                self._pp.feed(data)
                try:
                    packets = self._pp.pop_packets()
                except ValueError as e:
                    logging.error("PacketProto: %s", e)
                    break
                for pkt in packets:
                    await self._handle_udppy_payload(pkt)
        finally:
            await self.close_all()

    async def close_all(self) -> None:
        self._closed = True
        for conid in list(self._by_conid.keys()):
            con = self._by_conid.get(conid)
            if con:
                await con.close()

    async def remove_connection(self, conid: int) -> None:
        self._by_conid.pop(conid, None)

    def _touch_lru(self, con: UdppyConnection) -> None:
        self._by_conid.move_to_end(con.conid, last=True)

    async def _evict_lru(self) -> None:
        if not self._by_conid:
            return
        oldest = next(iter(self._by_conid))
        con = self._by_conid[oldest]
        logging.debug("Límite de conexiones: cerrando conid=%s", oldest)
        await con.close()

    async def send_udppy_reply(
        self,
        con: UdppyConnection,
        *,
        flags: int,
        payload: bytes,
    ) -> None:
        if self._closed:
            return
        body = P.pack_udppy_to_client(
            flags,
            con.conid,
            con.orig_ip,
            con.orig_port,
            payload,
            ipv6=con.orig_ipv6,
        )
        if len(body) > self.udppy_mtu:
            logging.warning("respuesta udppy demasiado grande (protocolo udpgw)")
            return
        frame = struct.pack("<H", len(body)) + body
        async with self._lock:
            self.writer.write(frame)
            await self.writer.drain()

    async def _handle_udppy_payload(self, data: bytes) -> None:
        if len(data) < P.HEADER_SIZE:
            logging.error("mensaje de protocolo demasiado corto")
            return
        flags, conid, pos = P.parse_udppy_header(data)
        rest = data[pos:]

        if flags & P.UDPPY_FLAG_KEEPALIVE:
            logging.debug("keepalive")
            return

        ipv6 = bool(flags & P.UDPPY_FLAG_IPV6)
        if ipv6:
            host, port, n = P.parse_udppy_addr_ipv6(rest)
        else:
            host, port, n = P.parse_udppy_addr_ipv4(rest)

        rest = rest[n:]
        if len(rest) > self.udp_mtu:
            logging.error("payload UDP excede udp-mtu")
            return

        orig_ip, orig_port = host, port

        target_ip, target_port = orig_ip, orig_port
        if flags & P.UDPPY_FLAG_DNS:
            if self.dns_host is None or self.dns_port is None:
                logging.warning(
                    "paquete DNS pero no hay servidor DNS (--dns); se ignora"
                )
                return
            target_ip, target_port = self.dns_host, self.dns_port

        try:
            tip, tport, _ = await self._resolve_target(target_ip, target_port)
        except OSError as e:
            logging.error("resolución destino %s:%s: %s", target_ip, target_port, e)
            return

        con = self._by_conid.get(conid)
        if con and (
            (flags & P.UDPPY_FLAG_REBIND)
            or not _addr_equal(
                con.orig_ip,
                con.orig_port,
                orig_ip,
                orig_port,
                ipv6=ipv6,
            )
        ):
            await con.close()
            con = None

        if not con:
            if len(self._by_conid) >= self.max_connections:
                await self._evict_lru()
            con = UdppyConnection(
                client=self,
                conid=conid,
                orig_ip=orig_ip,
                orig_port=orig_port,
                orig_ipv6=ipv6,
                target_ip=tip,
                target_port=tport,
                udp_mtu=self.udp_mtu,
                udppy_mtu=self.udppy_mtu,
                linux_tune_sockets=self._linux_tune_sockets,
            )
            self._by_conid[conid] = con
            try:
                await con.setup_udp()
            except OSError as e:
                logging.error("UDP connect conid=%s: %s", conid, e)
                self._by_conid.pop(conid, None)
                await con.close()
                return

        self._touch_lru(con)
        con.send_udp(rest)


async def _resolve_udp(
    host: str, port: int
) -> tuple[str, int, bool]:
    """Devuelve (ip, puerto, es_ipv6)."""
    loop = asyncio.get_running_loop()
    addrinfos = await loop.getaddrinfo(
        host,
        port,
        type=socket.SOCK_DGRAM,
        proto=socket.IPPROTO_UDP,
    )
    if not addrinfos:
        raise OSError(f"sin direcciones para {host!r}")
    fam, _, _, _, sockaddr = addrinfos[0]
    if fam == socket.AF_INET:
        return sockaddr[0], sockaddr[1], False
    if fam == socket.AF_INET6:
        return sockaddr[0], sockaddr[1], True
    raise OSError(f"familia no soportada: {fam}")


def _parse_listen_addr(s: str) -> tuple[str, int]:
    try:
        if s.startswith("["):
            # [::1]:7300
            end = s.rindex("]")
            host = s[1:end]
            port = int(s[end + 2 :])
            return host, port
        host, _, port_s = s.rpartition(":")
        if not host or not port_s:
            raise ValueError
        return host, int(port_s)
    except (ValueError, IndexError) as e:
        raise argparse.ArgumentTypeError(
            "formato: host:puerto o [ipv6]:puerto"
        ) from e


def _parse_dns(s: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    if not s:
        return None, None
    if s.startswith("["):
        end = s.rindex("]")
        host = s[1:end]
        port = int(s[end + 2 :])
        return host, port
    host, _, p = s.rpartition(":")
    if not host or not p:
        raise ValueError("--dns inválido")
    return host, int(p)


async def _client_connected(
    reader: "StreamReader",
    writer: "StreamWriter",
    *,
    udp_mtu: int,
    udppy_mtu: int,
    dns_host: Optional[str],
    dns_port: Optional[int],
    max_connections: int,
    linux_tune_sockets: bool,
) -> None:
    session = TcpClientSession(
        reader,
        writer,
        udp_mtu=udp_mtu,
        udppy_mtu=udppy_mtu,
        dns_host=dns_host,
        dns_port=dns_port,
        max_connections=max_connections,
        linux_tune_sockets=linux_tune_sockets,
    )
    try:
        await session.run()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _amain() -> None:
    ap = argparse.ArgumentParser(
        description="udppy — servidor compatible con badvpn/udpgw (PacketProto)"
    )
    ap.add_argument(
        "--listen-addr",
        type=str,
        default="0.0.0.0:7300",
        help="Dirección TCP (IPv4 a.b.c.d:puerto o [ipv6]:puerto)",
    )
    ap.add_argument(
        "--udp-mtu",
        type=int,
        default=P.DEFAULT_UDP_MTU,
        help="Tamaño máximo del payload UDP (como --udp-mtu en el daemon udpgw de badvpn)",
    )
    ap.add_argument(
        "--max-connections",
        type=int,
        default=256,
        help="Máximo de conexiones UDP lógicas por cliente TCP",
    )
    ap.add_argument(
        "--dns",
        type=str,
        default=None,
        metavar="HOST:PUERTO",
        help="Reenvío DNS cuando el cliente marca el flag DNS (recomendado en Windows)",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument(
        "--no-linux-tune",
        action="store_true",
        help="Desactivar TCP_NODELAY/buffers en Linux (solo depuración)",
    )
    ap.add_argument(
        "--backlog",
        type=int,
        default=256,
        metavar="N",
        help="Cola del socket de escucha TCP (Linux: suele subirse para muchos clientes)",
    )
    ap.add_argument(
        "--uvloop",
        action="store_true",
        help="Obsoleto: en Linux uvloop ya es el predeterminado si está instalado.",
    )
    ap.add_argument(
        "--no-uvloop",
        action="store_true",
        help="En Linux, no usar uvloop (asyncio estándar).",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if linux_tune.is_linux():
        if args.no_uvloop:
            logging.info("bucle de eventos: asyncio (--no-uvloop)")
        elif _uvloop_installed:
            logging.info("bucle de eventos: uvloop")
        else:
            logging.info(
                "bucle de eventos: asyncio (pip install uvloop recomendado en Linux)"
            )

    udppy_mtu = min(P.udppy_compute_mtu(args.udp_mtu), PACKETPROTO_MAXPAYLOAD)

    try:
        dns_host, dns_port = _parse_dns(args.dns)
    except ValueError as e:
        logging.error("%s", e)
        return

    try:
        host, port = _parse_listen_addr(args.listen_addr)
    except argparse.ArgumentTypeError as e:
        logging.error("%s", e)
        return

    linux_tune_sockets = (
        linux_tune.is_linux() and not args.no_linux_tune
    )

    server = await asyncio.start_server(
        lambda r, w: _client_connected(
            r,
            w,
            udp_mtu=args.udp_mtu,
            udppy_mtu=udppy_mtu,
            dns_host=dns_host,
            dns_port=dns_port,
            max_connections=args.max_connections,
            linux_tune_sockets=linux_tune_sockets,
        ),
        host=host,
        port=port,
        backlog=args.backlog,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("udppy escuchando en %s (udppy_mtu=%s)", addrs, udppy_mtu)

    async with server:
        await server.serve_forever()


def main() -> None:
    global _uvloop_installed
    _uvloop_installed = False
    # uvloop debe instalarse antes de asyncio.run (Linux por defecto si está instalado)
    if (
        linux_tune.is_linux()
        and "--no-uvloop" not in sys.argv
    ):
        try:
            import uvloop

            uvloop.install()
            _uvloop_installed = True
        except ImportError:
            pass
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
