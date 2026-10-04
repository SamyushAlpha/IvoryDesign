from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def categorize_existing_members(apps, schema_editor):
    TeamMember = apps.get_model("Ivory", "TeamMember")
    for member in TeamMember.objects.all():
        designation = (member.designation or "").lower()
        if "founder" in designation:
            category = "founder"
        elif "board" in designation or "director" in designation:
            category = "board"
        elif "architect" in designation:
            category = "architects"
        elif "engineer" in designation:
            category = "engineers"
        else:
            category = "staff"
        member.category = category
        member.save(update_fields=("category",))


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0027_independent_salary_advances"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="teammember",
            name="category",
            field=models.CharField(
                choices=[
                    ("founder", "Founder"),
                    ("board", "Board of Director"),
                    ("architects", "Architects"),
                    ("engineers", "Engineers"),
                    ("staff", "Staff"),
                ],
                default="staff",
                help_text="Choose where this member appears on the Our Team page.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="teammember",
            name="user",
            field=models.OneToOneField(
                blank=True,
                help_text="Link the staff login that may view only this member's salary records and advances.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="team_member_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(categorize_existing_members, migrations.RunPython.noop),
    ]
