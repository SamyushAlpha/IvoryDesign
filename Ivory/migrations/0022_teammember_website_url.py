from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Ivory", "0021_securitythrottle"),
    ]

    operations = [
        migrations.AddField(
            model_name="teammember",
            name="website_url",
            field=models.URLField(
                blank=True,
                help_text="Optional. Add the full website address, for example https://example.com.",
                max_length=500,
                verbose_name="Website link",
            ),
        ),
    ]
