from django.db import migrations, models


def bind_existing_rules(apps, schema_editor):
    AlertRule = apps.get_model("alerts", "AlertRule")
    Monitor = apps.get_model("monitors", "Monitor")
    NotificationChannel = apps.get_model("alerts", "NotificationChannel")
    monitors = list(Monitor.objects.values_list("pk", flat=True))
    channels = list(NotificationChannel.objects.values_list("pk", flat=True))
    for rule in AlertRule.objects.all():
        rule.monitors.set(monitors)
        rule.channels.set(channels)


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0002_notificationchannel_serverchan"),
        ("monitors", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertrule",
            name="monitors",
            field=models.ManyToManyField(
                related_name="alert_rules", to="monitors.monitor"
            ),
        ),
        migrations.AddField(
            model_name="alertrule",
            name="channels",
            field=models.ManyToManyField(
                related_name="alert_rules", to="alerts.notificationchannel"
            ),
        ),
        migrations.RunPython(bind_existing_rules, migrations.RunPython.noop),
    ]
