from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitors", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="monitor",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
