from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Ivory", "0020_invoicecounter_roomestimate_invoice_number")]

    operations = [
        migrations.CreateModel(
            name="SecurityThrottle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=160, unique=True)),
                ("count", models.PositiveIntegerField(default=0)),
                ("window_ends", models.DateTimeField(db_index=True)),
            ],
            options={"verbose_name": "Security throttle", "verbose_name_plural": "Security throttles"},
        ),
    ]
