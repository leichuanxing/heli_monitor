from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0001_system_setting")]

    operations = [
        migrations.AddField(
            model_name="systemsetting",
            name="home_page_title",
            field=models.CharField(default="合力数据业务监控系统", max_length=64),
        ),
    ]
