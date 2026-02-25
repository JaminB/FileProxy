# Generated migration for subscription plan default+expires_at index

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="subscriptionplan",
            index=models.Index(
                fields=["is_default", "expires_at"], name="sub_plan_default_exp_idx"
            ),
        ),
    ]
