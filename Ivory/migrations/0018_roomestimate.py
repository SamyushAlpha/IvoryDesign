import uuid
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("Ivory", "0017_alter_supportattachment_file")]
    operations = [
        migrations.CreateModel(
            name="RoomEstimate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("customer_name", models.CharField(max_length=120)),
                ("room_count", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("rooms", models.JSONField(help_text="Room dimensions and calculated areas.")),
                ("rate_per_sq_ft", models.DecimalField(decimal_places=2, max_digits=6)),
                ("total_area_sq_ft", models.DecimalField(decimal_places=2, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Room estimate", "verbose_name_plural": "Room estimates", "ordering": ["-created_at"]},
        )
    ]
