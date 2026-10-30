"""Reject invalid header encodings before they can escape the WS parser."""
from uvicorn.protocols.websockets.wsproto_impl import WSProtocol


class LocalWebSocketProtocol(WSProtocol):
    def data_received(self, data):
        try:
            super().data_received(data)
        except UnicodeError:
            # wsproto's handshake token decoder can raise UnicodeDecodeError
            # for non-ASCII protocol/extension fields rather than a protocol
            # rejection. Always close, including partially parsed upgrades.
            self.close_sent = True
            if not self.handshake_complete and not self.response_started:
                self.transport.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            self.transport.close()
