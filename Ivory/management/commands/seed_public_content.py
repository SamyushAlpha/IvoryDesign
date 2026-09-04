from django.core.management import call_command
from django.core.management.base import BaseCommand

from Ivory.models import AboutCompany, Client, Project, Service, TeamMember


class Command(BaseCommand):
    help = "Load the bundled public site content when a new database is empty."

    def handle(self, *args, **options):
        public_models = (AboutCompany, Client, Project, Service, TeamMember)
        if any(model.objects.exists() for model in public_models):
            self.stdout.write("Public content already exists; skipping starter import.")
            return

        call_command("loaddata", "data/public_content.json")
        self.stdout.write(self.style.SUCCESS("Starter public content imported."))
