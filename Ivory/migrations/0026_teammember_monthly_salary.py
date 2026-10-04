import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0025_allow_monthly_salary_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="teammember",
            name="monthly_salary",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Default salary used automatically when creating this member's monthly salary record.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))],
                verbose_name="Monthly salary (NPR)",
            ),
        ),
    ]
