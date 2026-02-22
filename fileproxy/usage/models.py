from django.db import models


class OperationKind(models.TextChoices):
    TEST = "test"
    ENUMERATE = "enumerate"
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class UsageEvent(models.Model):
    scope = models.CharField(max_length=200, db_index=True)
    vault_item_name = models.CharField(max_length=200)
    vault_item_kind = models.CharField(max_length=50)
    operation = models.CharField(max_length=20, choices=OperationKind.choices)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    object_path = models.CharField(max_length=1000, blank=True, default="")
    ok = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["scope", "occurred_at"])]
