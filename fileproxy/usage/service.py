from __future__ import annotations


def record_event(
    scope: str,
    vault_item_name: str,
    vault_item_kind: str,
    operation: str,
    object_path: str = "",
    ok: bool = True,
    bytes_transferred: int = 0,
) -> None:
    try:
        from .models import UsageEvent

        UsageEvent.objects.create(
            scope=scope,
            vault_item_name=vault_item_name,
            vault_item_kind=vault_item_kind,
            operation=operation,
            object_path=object_path,
            ok=ok,
            bytes_transferred=bytes_transferred,
        )
    except Exception:  # noqa: BLE001
        pass
