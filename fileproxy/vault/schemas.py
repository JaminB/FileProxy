from dataclasses import dataclass
from typing import Any, Dict, Optional, Mapping


@dataclass(frozen=True)
class S3StaticCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "access_key_id": self.access_key_id,
            "secret_access_key": self.secret_access_key,
            "session_token": self.session_token,
        }

    @staticmethod
    def from_payload(p: Dict[str, Any]) -> "S3StaticCredentials":
        return S3StaticCredentials(
            access_key_id=p["access_key_id"],
            secret_access_key=p["secret_access_key"],
            session_token=p.get("session_token"),
        )


@dataclass(frozen=True)
class GoogleDriveOAuth2Credentials:
    client_id: str
    client_secret: str
    refresh_token: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

    @staticmethod
    def from_payload(p: Dict[str, Any]) -> "GoogleDriveOAuth2Credentials":
        return GoogleDriveOAuth2Credentials(
            client_id=p["client_id"],
            client_secret=p["client_secret"],
            refresh_token=p["refresh_token"],
        )
