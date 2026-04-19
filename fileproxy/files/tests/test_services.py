from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from connections.service import create_s3_credentials
from core.backends.s3 import S3Backend
from files.services import (
    ConnectionNotFound,
    connections_for_user,
    get_backend_for_connection,
    user_scope,
)

User = get_user_model()


class UserScopeTests(TestCase):
    def test_user_scope_format(self):
        user = User.objects.create_user(username="scopeuser", password="pw")
        self.assertEqual(user_scope(user), f"user:{user.id}")


class ConnectionsForUserTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="cfuser1", password="pw")
        self.user2 = User.objects.create_user(username="cfuser2", password="pw")

    def _make_s3(self, user, name):
        return create_s3_credentials(
            scope=f"user:{user.id}",
            name=name,
            settings_obj={"user_id": user.id},
            secrets_obj={"access_key_id": "AKIA", "secret_access_key": "secret", "session_token": None},
        )

    def test_returns_only_own_connections(self):
        self._make_s3(self.user1, "alpha")
        self._make_s3(self.user2, "beta")

        user1_conns = list(connections_for_user(self.user1))
        self.assertEqual(len(user1_conns), 1)
        self.assertEqual(user1_conns[0].name, "alpha")

    def test_ordered_by_name(self):
        self._make_s3(self.user1, "zebra")
        self._make_s3(self.user1, "apple")
        self._make_s3(self.user1, "mango")

        names = [c.name for c in connections_for_user(self.user1)]
        self.assertEqual(names, ["apple", "mango", "zebra"])


class GetBackendForConnectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gbfcuser", password="pw")

    def _make_s3(self, name):
        return create_s3_credentials(
            scope=f"user:{self.user.id}",
            name=name,
            settings_obj={"user_id": self.user.id, "bucket": "test-bucket"},
            secrets_obj={"access_key_id": "AKIAEXAMPLE", "secret_access_key": "secret", "session_token": None},
        )

    def test_missing_name_raises_connection_not_found(self):
        with self.assertRaises(ConnectionNotFound):
            get_backend_for_connection(user=self.user, connection_name="")

    def test_blank_name_raises_connection_not_found(self):
        with self.assertRaises(ConnectionNotFound):
            get_backend_for_connection(user=self.user, connection_name="   ")

    def test_wrong_user_raises_connection_not_found(self):
        self._make_s3("myconn")
        other = User.objects.create_user(username="gbfc_other", password="pw")
        with self.assertRaises(ConnectionNotFound):
            get_backend_for_connection(user=other, connection_name="myconn")

    def test_happy_path_returns_s3_backend(self):
        self._make_s3("myconn")
        with patch("boto3.client", return_value=MagicMock()):
            backend = get_backend_for_connection(user=self.user, connection_name="myconn")
        self.assertIsInstance(backend, S3Backend)
