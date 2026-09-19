from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("Ivory", "0018_roomestimate"),
    ]

    operations = [
        migrations.AddField(
            model_name="roomestimate",
            name="phone_number",
            field=models.CharField(default="", max_length=20),
            preserve_default=False,
        ),
    ]
