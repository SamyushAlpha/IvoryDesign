import decimal
import uuid

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0022_teammember_website_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalaryInvoiceCounter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveSmallIntegerField(unique=True)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Salary invoice counter",
                "verbose_name_plural": "Salary invoice counters",
            },
        ),
        migrations.CreateModel(
            name="SalaryRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("salary_month", models.DateField(help_text="Choose any date in the salary month. It will be saved as the first day of that month.")),
                ("salary_amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="salary_records", to="Ivory.teammember")),
            ],
            options={
                "verbose_name": "Salary record",
                "verbose_name_plural": "Salary records",
                "ordering": ["-salary_month", "member__name"],
            },
        ),
        migrations.CreateModel(
            name="SalaryAdvance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
                ("given_on", models.DateField(default=django.utils.timezone.localdate)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("salary_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="advances", to="Ivory.salaryrecord")),
            ],
            options={
                "verbose_name": "Salary advance",
                "verbose_name_plural": "Salary advances",
                "ordering": ["given_on", "pk"],
            },
        ),
        migrations.CreateModel(
            name="SalaryPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
                ("paid_on", models.DateField(default=django.utils.timezone.localdate)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("invoice_year", models.PositiveSmallIntegerField(blank=True, editable=False, null=True)),
                ("invoice_sequence", models.PositiveIntegerField(blank=True, editable=False, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("salary_record", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="Ivory.salaryrecord")),
            ],
            options={
                "verbose_name": "Salary payment",
                "verbose_name_plural": "Salary payments",
                "ordering": ["-paid_on", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="salaryrecord",
            constraint=models.UniqueConstraint(fields=("member", "salary_month"), name="unique_member_salary_month"),
        ),
        migrations.AddConstraint(
            model_name="salarypayment",
            constraint=models.UniqueConstraint(fields=("invoice_year", "invoice_sequence"), name="unique_salary_payment_invoice_number"),
        ),
    ]
