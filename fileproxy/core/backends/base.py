from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, Protocol, runtime_checkable


class BackendError(RuntimeError):
    """Base exception for backend failures."""


class BackendConnectionError(BackendError):
    """Raised when backend connectivity or authentication fails."""


class BackendTestError(BackendConnectionError):
    """Raised when backend test/health check fails."""


class BackendEnumerateError(BackendError):
    """Raised when enumeration/listing fails."""


class BackendReadError(BackendError):
    """Raised when reading an object fails."""


class BackendWriteError(BackendError):
    """Raised when creating/updating an object fails."""


class BackendDeleteError(BackendError):
    """Raised when deleting an object fails."""


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Backend configuration and secrets."""

    kind: str
    settings: Mapping[str, Any]
    secrets: Mapping[str, Any]


@runtime_checkable
class BackendObject(Protocol):
    """Represents an object returned by backend enumeration."""

    name: str
    path: str
    size: int | None


@dataclass(frozen=True, slots=True)
class EnumeratePage:
    """One page of results from enumerate_page()."""

    objects: list[BackendObject]
    next_cursor: str | None


class Backend(ABC):
    """Base interface for external storage backends."""

    def __init__(self, config: BackendConfig):
        """Initialize backend.

        Args:
            config: Backend configuration and secrets.
        """
        self.config = config

    @abstractmethod
    def test(self) -> None:
        """Validate connectivity and credentials.

        Raises:
            BackendTestError: If validation fails.
        """
        raise NotImplementedError

    @abstractmethod
    def enumerate_page(
        self,
        *,
        prefix: str | None = None,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> EnumeratePage:
        """Return one page of objects. cursor=None starts from the beginning."""
        raise NotImplementedError

    def enumerate(self, *, prefix: str | None = None) -> Iterable[BackendObject]:
        """Full scan — loops enumerate_page for backwards compatibility."""
        cursor: str | None = None
        while True:
            page = self.enumerate_page(prefix=prefix, cursor=cursor, page_size=1000)
            yield from page.objects
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read an object from the backend.

        Args:
            path: Backend-specific object path.

        Returns:
            Raw object bytes.

        Raises:
            BackendReadError: If reading fails.
        """
        raise NotImplementedError

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Create or overwrite an object.

        Args:
            path: Backend-specific object path.
            data: Object contents.

        Raises:
            BackendWriteError: If write fails.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete an object.

        Args:
            path: Backend-specific object path.

        Raises:
            BackendDeleteError: If delete fails.
        """
        raise NotImplementedError

    def read_stream(self, path: str) -> Iterator[bytes]:
        """Yield object bytes as chunks. Default: reads all at once."""
        yield self.read(path)

    def write_stream(self, path: str, stream: BinaryIO) -> None:
        """Write from a file-like stream. Default: reads all and calls write()."""
        self.write(path, stream.read())
