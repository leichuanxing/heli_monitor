from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_systemsetting_home_page_title")]

    operations = [
        migrations.AddField(
            model_name="systemsetting",
            name="browser_title",
            field=models.CharField(default="合力数据业务监控系统", max_length=64),
        ),
        migrations.AddField(
            model_name="systemsetting",
            name="dashboard_refresh_seconds",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name="systemsetting",
            name="login_page_description",
            field=models.CharField(default="企业级业务可用性监控与告警平台", max_length=128),
        ),
        migrations.AddField(
            model_name="systemsetting",
            name="monitor_result_retention_count",
            field=models.PositiveIntegerField(default=10000),
        ),
        migrations.AddField(
            model_name="systemsetting",
            name="monitor_wall_refresh_seconds",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
