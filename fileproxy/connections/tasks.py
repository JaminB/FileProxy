from __future__ import annotations

import logging

from celery import shared_task
from django.core.exceptions import ValidationError

from core.backends.base import BackendConnectionError
from core.backends.factory import backend_from_config

from .models import Connection, ConnectionKind

logger = logging.getLogger(__name__)

_OAUTH2_KINDS = {ConnectionKind.GDRIVE_OAUTH2, ConnectionKind.DROPBOX_OAUTH2}


@shared_task(name="connections.refresh_oauth2_connection")
def refresh_oauth2_connection(connection_id: str) -> None:
    """Refresh OAuth2 credentials for a single connection.

    Loads the connection by ID, instantiates the backend, and calls
    refresh_credentials(). All errors are caught and logged — the task
    never crashes the worker.

    Args:
        connection_id: UUID string of the Connection to refresh.
    """
    try:
        conn = Connection.objects.get(id=connection_id)
    except Connection.DoesNotExist:
        logger.warning("refresh_oauth2_connection: connection %s not found", connection_id)
        return
    except (ValidationError, ValueError, TypeError):
        logger.warning("refresh_oauth2_connection: invalid connection id %r", connection_id)
        return

    if conn.kind not in _OAUTH2_KINDS:
        logger.warning(
            "refresh_oauth2_connection: connection %s has non-OAuth2 kind %s, skipping",
            connection_id,
            conn.kind,
        )
        return

    try:
        backend = backend_from_config(conn.to_backend_config())
        backend.refresh_credentials()
        logger.info("refresh_oauth2_connection: refreshed %s (%s)", connection_id, conn.kind)
    except BackendConnectionError as e:
        logger.error(
            "refresh_oauth2_connection: auth failure for %s (%s/%s): %s",
            connection_id,
            conn.kind,
            conn.scope,
            e,
        )
    except Exception:
        logger.exception("refresh_oauth2_connection: unexpected error for %s", connection_id)


@shared_task(name="connections.refresh_all_oauth2_connections")
def refresh_all_oauth2_connections() -> None:
    """Fan out refresh tasks for all OAuth2 connections.

    Queries all gdrive_oauth2 and dropbox_oauth2 connections and enqueues
    a refresh_oauth2_connection task for each one.
    """
    ids = Connection.objects.filter(kind__in=_OAUTH2_KINDS).values_list("id", flat=True)
    count = 0
    for conn_id in ids:
        refresh_oauth2_connection.delay(str(conn_id))
        count += 1
    logger.info("refresh_all_oauth2_connections: enqueued %d tasks", count)
