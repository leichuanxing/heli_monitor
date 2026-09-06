from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SystemSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("brand_logo_text", models.CharField(default="合力数据", max_length=32)),
                (
                    "monitor_wall_title",
                    models.CharField(default="合力数据业务监控系统", max_length=64),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
