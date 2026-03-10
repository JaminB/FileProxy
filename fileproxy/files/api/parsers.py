from rest_framework.parsers import BaseParser


class OctetStreamParser(BaseParser):
    media_type = "application/octet-stream"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()  # request.data becomes raw bytes


class _ByteCountingStream:
    """Wraps a binary readable, counting bytes read through it."""

    def __init__(self, stream):
        self._stream = stream
        self.bytes_read: int = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size) if size != -1 else self._stream.read()
        self.bytes_read += len(chunk)
        return chunk
