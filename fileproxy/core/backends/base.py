from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


class BackendError(RuntimeError):
    """Base exception for backend failures."""


class BackendConnectionError(BackendError):
    """Raised when backend connectivity or authentication fails."""


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
            BackendConnectionError: If validation fails.
        """
        raise NotImplementedError

    @abstractmethod
    def enumerate(self, *, prefix: str | None = None) -> Iterable[BackendObject]:
        """List objects in the backend.

        Args:
            prefix: Optional backend-specific path or prefix filter.

        Returns:
            Iterable of backend objects.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read an object from the backend.

        Args:
            path: Backend-specific object path.

        Returns:
            Raw object bytes.
        """
        raise NotImplementedError

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Create or overwrite an object.

        Args:
            path: Backend-specific object path.
            data: Object contents.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete an object.

        Args:
            path: Backend-specific object path.
        """
        raise NotImplementedError