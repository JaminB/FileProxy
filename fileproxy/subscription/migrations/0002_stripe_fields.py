from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscription", "0001_initial"),
    ]

    operations = [
        # ── SubscriptionPlan: new Stripe / pricing fields ──────────────────
        migrations.AddField(
            model_name="subscriptionplan",
            name="stripe_product_id",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="stripe_price_id",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="price_cents",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="currency",
            field=models.CharField(default="usd", max_length=3),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="billing_interval",
            field=models.CharField(
                blank=True,
                choices=[("month", "Monthly"), ("year", "Yearly")],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="billing_interval_count",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="trial_days",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        # ── UserSubscription: rename cycle/cancel fields ───────────────────
        migrations.RenameField(
            model_name="usersubscription",
            old_name="cycle_started_at",
            new_name="current_period_start",
        ),
        migrations.RenameField(
            model_name="usersubscription",
            old_name="cycle_ends_at",
            new_name="current_period_end",
        ),
        migrations.RenameField(
            model_name="usersubscription",
            old_name="cancels_at",
            new_name="cancel_at",
        ),
        # ── UserSubscription: expand status choices ────────────────────────
        migrations.AlterField(
            model_name="usersubscription",
            name="status",
            field=models.CharField(
                choices=[
                    ("trialing", "Trialing"),
                    ("active", "Active"),
                    ("past_due", "Past Due"),
                    ("canceled", "Canceled"),
                    ("incomplete", "Incomplete"),
                    ("incomplete_expired", "Incomplete Expired"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        # ── UserSubscription: new Stripe / billing fields ──────────────────
        migrations.AddField(
            model_name="usersubscription",
            name="stripe_customer_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=255, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="stripe_subscription_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=255, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="trial_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="trial_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="cancel_at_period_end",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="canceled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
