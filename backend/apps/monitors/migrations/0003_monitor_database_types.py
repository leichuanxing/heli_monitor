from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitors", "0002_monitor_is_archived")]

    operations = [
        migrations.AlterField(
            model_name="monitor",
            name="monitor_type",
            field=models.CharField(
                choices=[
                    ("HTTP", "HTTP"),
                    ("API", "API"),
                    ("TCP", "TCP"),
                    ("PING", "PING"),
                    ("DNS", "DNS"),
                    ("SSL", "SSL"),
                    ("MSSQL", "MSSQL"),
                    ("POSTGRESQL", "POSTGRESQL"),
                    ("MYSQL", "MYSQL"),
                    ("MONGODB", "MONGODB"),
                ],
                max_length=16,
            ),
        )
    ]
