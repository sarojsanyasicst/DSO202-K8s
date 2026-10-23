"""The disposable broker behind CLOUDCART_TEST_BROKER_URL speaks AMQP 0-9-1."""

import socket
from urllib.parse import urlsplit

AMQP_0_9_1_PROTOCOL_HEADER = b"AMQP\x00\x00\x09\x01"
AMQP_DEFAULT_PORT = 5672
METHOD_FRAME = 1
CONNECTION_START = (10, 10)  # (class id, method id)


def receive_exactly(connection: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        assert chunk, "broker closed the connection during the AMQP handshake"
        data += chunk
    return data


def test_disposable_broker_starts_an_amqp_handshake(test_broker_url: str) -> None:
    parts = urlsplit(test_broker_url)

    with socket.create_connection((parts.hostname, parts.port or AMQP_DEFAULT_PORT), timeout=5) as connection:
        connection.sendall(AMQP_0_9_1_PROTOCOL_HEADER)
        frame = receive_exactly(connection, 11)

    frame_type, channel = frame[0], int.from_bytes(frame[1:3])
    method = (int.from_bytes(frame[7:9]), int.from_bytes(frame[9:11]))
    assert (frame_type, channel, method) == (METHOD_FRAME, 0, CONNECTION_START)
