from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField("department", "description", models.TextField(blank=True)),
        migrations.AddField("department", "sort_order", models.PositiveIntegerField(default=0)),
        migrations.AddField("department", "is_enabled", models.BooleanField(default=True)),
        migrations.AddField("department", "updated_at", models.DateTimeField(auto_now=True)),
        migrations.AddField("role", "description", models.TextField(blank=True)),
        migrations.AddField(
            "role",
            "data_scope",
            models.CharField(
                choices=[("ALL", "全部"), ("DEPARTMENT", "本部门"), ("SELF", "本人")],
                default="SELF",
                max_length=20,
            ),
        ),
        migrations.AddField("role", "is_enabled", models.BooleanField(default=True)),
        migrations.AddField("role", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AddField("role", "updated_at", models.DateTimeField(auto_now=True)),
    ]
