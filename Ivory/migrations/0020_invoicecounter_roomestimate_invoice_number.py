from django.db import migrations, models


def populate_invoice_numbers(apps, schema_editor):
    RoomEstimate = apps.get_model("Ivory", "RoomEstimate")
    InvoiceCounter = apps.get_model("Ivory", "InvoiceCounter")
    highest_by_year = {}
    for estimate in RoomEstimate.objects.all().iterator():
        year = estimate.created_at.year
        sequence = estimate.pk
        estimate.invoice_year = year
        estimate.invoice_sequence = sequence
        estimate.save(update_fields=("invoice_year", "invoice_sequence"))
        highest_by_year[year] = max(highest_by_year.get(year, 0), sequence)
    for year, last_number in highest_by_year.items():
        InvoiceCounter.objects.update_or_create(year=year, defaults={"last_number": last_number})


class Migration(migrations.Migration):
    dependencies = [("Ivory", "0019_roomestimate_phone_number")]

    operations = [
        migrations.CreateModel(
            name="InvoiceCounter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveSmallIntegerField(unique=True)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
            options={"verbose_name": "Invoice counter", "verbose_name_plural": "Invoice counters"},
        ),
        migrations.AddField(
            model_name="roomestimate",
            name="invoice_sequence",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="roomestimate",
            name="invoice_year",
            field=models.PositiveSmallIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_invoice_numbers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="roomestimate",
            constraint=models.UniqueConstraint(fields=("invoice_year", "invoice_sequence"), name="unique_room_estimate_invoice_number"),
        ),
    ]
