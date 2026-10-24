"""Dependency faults for tests: a loopback TCP proxy that can cut or stall traffic to a disposable dependency.

Point a component at `proxy.url_for(real_url)` instead of the real URL, then
`cut()` (drop every connection and reset new ones, like a stopped server),
`stall()` (accept connections but forward nothing, like a hung server), and
`restore()`. Faults stay inside the test process: the disposable PostgreSQL and
RabbitMQ containers themselves keep running.
"""

import selectors
import socket
import struct
import threading
from urllib.parse import urlsplit, urlunsplit

LOOPBACK = "127.0.0.1"
IDLE_POLL_SECONDS = 0.05
CHUNK_BYTES = 65536


class TcpProxy:
    def __init__(self, target_host: str, target_port: int) -> None:
        self._target = (target_host, target_port)
        self._listener = socket.create_server((LOOPBACK, 0))
        self.port: int = self._listener.getsockname()[1]
        self._mode = "forward"
        self._lock = threading.Lock()
        self._pairs: set[tuple[socket.socket, socket.socket]] = set()
        self._closed = threading.Event()
        self.accepted = 0  # client connections accepted so far, in any mode
        threading.Thread(target=self._accept_loop, name=f"proxy-{self.port}", daemon=True).start()

    @classmethod
    def for_url(cls, url: str) -> "TcpProxy":
        parts = urlsplit(url)
        assert parts.hostname is not None and parts.port is not None
        return cls(parts.hostname, parts.port)

    def url_for(self, url: str) -> str:
        """`url` with its host and port replaced by this proxy's address."""
        parts = urlsplit(url)
        credentials = parts.netloc.rpartition("@")[0]
        netloc = f"{credentials}@{LOOPBACK}:{self.port}" if credentials else f"{LOOPBACK}:{self.port}"
        return urlunsplit(parts._replace(netloc=netloc))

    def cut(self) -> None:
        """Drop every open connection and reset new ones until `restore()`."""
        with self._lock:
            self._mode = "reset"
            pairs, self._pairs = self._pairs, set()
        for pair in pairs:
            _close(*pair)

    def stall(self) -> None:
        """Stop forwarding in both directions, keeping connections open, until `restore()`."""
        with self._lock:
            self._mode = "stall"

    def restore(self) -> None:
        with self._lock:
            self._mode = "forward"

    def close(self) -> None:
        self._closed.set()
        self._listener.close()
        self.cut()

    def _accept_loop(self) -> None:
        while not self._closed.is_set():
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            with self._lock:
                self.accepted += 1
                mode = self._mode
            if mode == "reset":
                _reset(client)
                continue
            try:
                upstream = socket.create_connection(self._target, timeout=5)
            except OSError:
                _reset(client)
                continue
            pair = (client, upstream)
            with self._lock:
                self._pairs.add(pair)
            threading.Thread(target=self._pump, args=(pair,), daemon=True).start()

    def _pump(self, pair: tuple[socket.socket, socket.socket]) -> None:
        client, upstream = pair
        peer = {client: upstream, upstream: client}
        with selectors.DefaultSelector() as selector:
            try:
                for sock in pair:
                    sock.setblocking(False)
                    selector.register(sock, selectors.EVENT_READ)
                while not self._closed.is_set():
                    with self._lock:
                        if pair not in self._pairs:
                            return
                        stalled = self._mode == "stall"
                    if stalled:
                        self._closed.wait(IDLE_POLL_SECONDS)
                        continue
                    for key, _ in selector.select(timeout=IDLE_POLL_SECONDS):
                        data = key.fileobj.recv(CHUNK_BYTES)
                        if not data:
                            return
                        peer[key.fileobj].setblocking(True)
                        peer[key.fileobj].sendall(data)
                        peer[key.fileobj].setblocking(False)
            except (OSError, ValueError):
                return
            finally:
                with self._lock:
                    self._pairs.discard(pair)
                _close(client, upstream)


def _reset(sock: socket.socket) -> None:
    """Close with an immediate RST, which the client sees as a refused or reset connection."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    except OSError:
        pass
    sock.close()


def _close(*sockets: socket.socket) -> None:
    for sock in sockets:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        _reset(sock)
