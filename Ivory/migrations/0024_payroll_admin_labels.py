from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0023_salary_payroll_records"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="salaryrecord",
            options={
                "ordering": ["-salary_month", "member__name"],
                "verbose_name": "Monthly salary",
                "verbose_name_plural": "Monthly salaries",
            },
        ),
        migrations.AlterModelOptions(
            name="salarypayment",
            options={
                "ordering": ["-paid_on", "-pk"],
                "verbose_name": "Salary invoice",
                "verbose_name_plural": "Salary invoices",
            },
        ),
    ]
