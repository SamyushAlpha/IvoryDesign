from django.db import migrations, models
import django.db.models.deletion


def copy_advance_members(apps, schema_editor):
    SalaryAdvance = apps.get_model("Ivory", "SalaryAdvance")
    for advance in SalaryAdvance.objects.select_related("salary_record").all():
        advance.member_id = advance.salary_record.member_id
        advance.save(update_fields=("member",))


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0026_teammember_monthly_salary"),
    ]

    operations = [
        migrations.AddField(
            model_name="salaryadvance",
            name="member",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="salary_advances",
                to="Ivory.teammember",
            ),
        ),
        migrations.RunPython(copy_advance_members, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="salaryadvance",
            name="member",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="salary_advances",
                to="Ivory.teammember",
            ),
        ),
        migrations.AlterField(
            model_name="salaryadvance",
            name="salary_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="advances",
                to="Ivory.salaryrecord",
            ),
        ),
    ]
