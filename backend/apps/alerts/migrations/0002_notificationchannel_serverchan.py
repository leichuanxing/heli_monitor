from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="notificationchannel",
            name="channel_type",
            field=models.CharField(
                choices=[
                    ("EMAIL", "EMAIL"),
                    ("WECHAT", "WECHAT"),
                    ("DINGTALK", "DINGTALK"),
                    ("WEBHOOK", "WEBHOOK"),
                    ("SERVERCHAN", "SERVERCHAN"),
                ],
                max_length=20,
            ),
        ),
    ]
