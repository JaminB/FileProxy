from __future__ import annotations

import io
from typing import BinaryIO, Iterator

from django.test import SimpleTestCase

from core.backends.base import Backend, BackendConfig, EnumeratePage


def _config() -> BackendConfig:
    return BackendConfig(kind="test", settings={}, secrets={})


class _StubBackend(Backend):
    """Minimal concrete Backend for testing default method implementations."""

    def __init__(self, config, pages):
        super().__init__(config)
        self._pages = list(pages)
        self._page_index = 0
        self.written: dict[str, bytes] = {}

    def test(self) -> None:
        pass

    def enumerate_page(self, *, prefix=None, cursor=None, page_size=1000) -> EnumeratePage:
        if self._page_index >= len(self._pages):
            return EnumeratePage(objects=[], next_cursor=None)
        page = self._pages[self._page_index]
        self._page_index += 1
        return page

    def read(self, path: str) -> bytes:
        return b"hello from " + path.encode()

    def write(self, path: str, data: bytes) -> None:
        self.written[path] = data

    def delete(self, path: str) -> None:
        pass


class EnumerateDefaultTests(SimpleTestCase):
    def test_single_page_no_next_cursor(self):
        page = EnumeratePage(objects=["a", "b"], next_cursor=None)
        backend = _StubBackend(_config(), [page])
        results = list(backend.enumerate())
        self.assertEqual(results, ["a", "b"])

    def test_multi_page_loops_until_no_cursor(self):
        page1 = EnumeratePage(objects=["a"], next_cursor="cursor1")
        page2 = EnumeratePage(objects=["b", "c"], next_cursor=None)
        backend = _StubBackend(_config(), [page1, page2])
        results = list(backend.enumerate())
        self.assertEqual(results, ["a", "b", "c"])

    def test_empty_first_page_returns_nothing(self):
        page = EnumeratePage(objects=[], next_cursor=None)
        backend = _StubBackend(_config(), [page])
        results = list(backend.enumerate())
        self.assertEqual(results, [])


class ReadStreamDefaultTests(SimpleTestCase):
    def test_default_read_stream_yields_single_chunk(self):
        backend = _StubBackend(_config(), [])
        chunks = list(backend.read_stream("myfile.txt"))
        self.assertEqual(chunks, [b"hello from myfile.txt"])


class WriteStreamDefaultTests(SimpleTestCase):
    def test_default_write_stream_calls_write_with_stream_content(self):
        backend = _StubBackend(_config(), [])
        data = b"stream content"
        backend.write_stream("output.bin", io.BytesIO(data))
        self.assertEqual(backend.written["output.bin"], data)
