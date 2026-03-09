from django.db import migrations


def make_jamin_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.filter(username="jamin").update(is_staff=True, is_superuser=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_notificationpreferences"),
    ]

    operations = [
        migrations.RunPython(make_jamin_admin, migrations.RunPython.noop),
    ]
