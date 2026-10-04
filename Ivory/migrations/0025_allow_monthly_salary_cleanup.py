import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0024_payroll_admin_labels"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salarypayment",
            name="salary_record",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payments",
                to="Ivory.salaryrecord",
            ),
        ),
    ]
