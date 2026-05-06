#!/usr/bin/env python3
"""
Redirección UDP (relé): reenvía datagramas entre clientes locales y un destino fijo.

Nota (badvpn/udpgw): el daemon oficial usa un protocolo TCP propio para tunelar
UDP a través de SOCKS. Este script hace reenvío UDP directo (puerto a puerto), útil
como proxy/relay en la misma red o cuando no hace falta pasar por SOCKS.

Uso:
  python udp_redirect.py --lport 5353 --target 8.8.8.8 --tport 53
"""

from __future__ import annotations

import argparse
import logging
import select
import socket
import sys
import threading
from typing import Dict

# Clave: dirección tal como la devuelve recvfrom (IPv4 o IPv6 con scope).


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Relé UDP: escucha en LPORT y reenvía a TARGET:TPORT (respuestas vuelven al cliente)."
    )
    p.add_argument(
        "--listen",
        default="0.0.0.0",
        metavar="ADDR",
        help="Dirección donde escuchar (default: 0.0.0.0; con destino IPv6 se usa :: si aplica)",
    )
    p.add_argument(
        "--lport",
        type=int,
        required=True,
        metavar="PUERTO",
        help="Puerto local de escucha",
    )
    p.add_argument(
        "--target",
        required=True,
        metavar="HOST",
        help="Host o IP de destino",
    )
    p.add_argument(
        "--tport",
        type=int,
        required=True,
        metavar="PUERTO",
        help="Puerto UDP de destino",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log de cada datagrama",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        target_ai = socket.getaddrinfo(
            args.target, args.tport, type=socket.SOCK_DGRAM
        )[0]
    except OSError as e:
        logging.error("No se pudo resolver destino %s:%s: %s", args.target, args.tport, e)
        sys.exit(1)

    family = target_ai[0]
    target_sockaddr = target_ai[4]

    relay = UdpRelay(args.listen, args.lport, family, target_sockaddr)
    relay.run()


class UdpRelay:
    """
    Un socket escucha clientes. Por cada cliente se mantiene un socket UDP conectado
    al destino para demultiplexar las respuestas correctamente.
    """

    def __init__(
        self,
        bind_addr: str,
        bind_port: int,
        target_family: int,
        target_sockaddr: tuple,
    ) -> None:
        self._bind_addr = bind_addr
        self._bind_port = bind_port
        self._target_family = target_family
        self._target = target_sockaddr
        self._lock = threading.Lock()
        self._client_to_upstream: Dict[tuple, socket.socket] = {}
        self._fd_to_client: Dict[int, tuple] = {}
        self._inbound: socket.socket | None = None

    def run(self) -> None:
        inbound = socket.socket(self._target_family, socket.SOCK_DGRAM)
        inbound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            if self._target_family == socket.AF_INET6:
                bind_ip = self._bind_addr
                if bind_ip in ("0.0.0.0", ""):
                    bind_ip = "::"
                inbound.bind((bind_ip, self._bind_port, 0, 0))
            else:
                inbound.bind((self._bind_addr, self._bind_port))
        except OSError as e:
            logging.error("No se pudo enlazar %s:%s: %s", self._bind_addr, self._bind_port, e)
            sys.exit(1)

        self._inbound = inbound

        logging.info(
            "Escuchando UDP %s -> %s",
            self._format_local(inbound),
            self._format_peer(self._target),
        )

        while True:
            with self._lock:
                rlist = [inbound] + list(self._client_to_upstream.values())
            try:
                readable, _, _ = select.select(rlist, [], [], 60.0)
            except InterruptedError:
                continue
            except ValueError:
                continue

            for s in readable:
                if s is inbound:
                    try:
                        data, client_addr = s.recvfrom(65535)
                    except OSError as e:
                        logging.warning("recvfrom cliente: %s", e)
                        continue
                    self._forward_to_target(data, client_addr)
                else:
                    self._forward_to_client(s)

    def _format_local(self, sock: socket.socket) -> str:
        try:
            a = sock.getsockname()
            if len(a) >= 2:
                return f"{a[0]}:{a[1]}"
        except OSError:
            pass
        return "?"

    def _format_peer(self, sockaddr) -> str:
        if sockaddr is None:
            return "?"
        host, port = sockaddr[0], sockaddr[1]
        return f"{host}:{port}"

    def _get_upstream(self, client_addr: tuple) -> socket.socket:
        with self._lock:
            up = self._client_to_upstream.get(client_addr)
            if up is not None:
                return up
            up = socket.socket(self._target_family, socket.SOCK_DGRAM)
            try:
                if self._target_family == socket.AF_INET6:
                    up.bind(("::", 0, 0, 0))
                else:
                    up.bind(("", 0))
            except OSError as e:
                up.close()
                raise e
            try:
                up.connect(self._target)
            except OSError as e:
                up.close()
                raise e
            self._client_to_upstream[client_addr] = up
            self._fd_to_client[up.fileno()] = client_addr
            logging.debug("Nuevo upstream para cliente %s (fd=%s)", client_addr, up.fileno())
            return up

    def _forward_to_target(self, data: bytes, client_addr: tuple) -> None:
        try:
            up = self._get_upstream(client_addr)
        except OSError as e:
            logging.error("upstream para %s: %s", client_addr, e)
            return
        try:
            up.send(data)
            logging.debug("%s bytes cliente %s -> destino", len(data), client_addr)
        except OSError as e:
            logging.warning("send a destino (cliente %s): %s", client_addr, e)

    def _forward_to_client(self, upstream: socket.socket) -> None:
        assert self._inbound is not None
        with self._lock:
            client_addr = self._fd_to_client.get(upstream.fileno())
        if client_addr is None:
            return
        try:
            data = upstream.recv(65535)
        except OSError as e:
            logging.warning("recv upstream: %s", e)
            return
        if not data:
            return
        try:
            self._inbound.sendto(data, client_addr)
            logging.debug("%s bytes destino -> cliente %s", len(data), client_addr)
        except OSError as e:
            logging.warning("sendto cliente %s: %s", client_addr, e)


if __name__ == "__main__":
    main()
