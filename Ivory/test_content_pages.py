from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Client, Project, ProjectCategory, ProjectImage, Service, TeamMember, TeamPortfolio


class ContentPagesTests(TestCase):
    def test_project_archive_links_to_long_form_case_study(self):
        category = ProjectCategory.objects.create(name="Apartments", slug="apartments")
        project = Project.objects.create(name="Sky Residence", category=category, description="Calm interior", image="projects/sky.jpg")
        ProjectImage.objects.create(project=project, image="projects/gallery/lounge.jpg", caption="The lounge", description="Layered stone and walnut.")
        detail_url = reverse("project_detail", args=[project.pk])
        self.assertContains(self.client.get(reverse("projects")), f'href="{detail_url}"')
        response = self.client.get(detail_url)
        self.assertContains(response, "Sky Residence")
        self.assertContains(response, "The lounge")
        self.assertContains(response, "Layered stone and walnut.")

    def test_services_show_only_published_content_in_order(self):
        Service.objects.create(title="Later service", description="Later", order=2)
        Service.objects.create(title="First service", description="<script>bad</script>", order=1)
        Service.objects.create(title="Hidden service", description="Private", is_active=False)
        response = self.client.get(reverse("services"))
        self.assertContains(response, "First service")
        self.assertNotContains(response, "Hidden service")
        self.assertContains(response, "&lt;script&gt;bad&lt;/script&gt;")
        self.assertLess(response.content.index(b"First service"), response.content.index(b"Later service"))

    def test_portfolio_is_scoped_to_active_member_and_entries(self):
        member = TeamMember.objects.create(name="Asha", designation="Designer", photo="team/asha.jpg")
        other = TeamMember.objects.create(name="Other", designation="Designer", photo="team/other.jpg")
        TeamPortfolio.objects.create(member=member, title="Asha project", image="team/work.jpg")
        TeamPortfolio.objects.create(member=member, title="Draft project", image="team/draft.jpg", is_active=False)
        TeamPortfolio.objects.create(member=other, title="Other project", image="team/other-work.jpg")
        url = reverse("team_portfolio", args=[member.pk])
        response = self.client.get(url)
        self.assertContains(response, "Asha project")
        self.assertNotContains(response, "Draft project")
        self.assertNotContains(response, "Other project")
        self.assertContains(self.client.get(reverse("about")), f'href="{url}"')
        member.is_active = False
        member.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("team_portfolio", args=[99999])).status_code, 404)

    def test_clients_only_show_active_logos(self):
        Client.objects.create(name="Visible client", logo="clients/visible.png")
        Client.objects.create(name="Hidden client", logo="clients/hidden.png", is_active=False)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'src="/media/clients/visible.png"', count=2)
        self.assertNotContains(response, 'clients/hidden.png')
        self.assertContains(response, 'clients-marquee.js')

    def test_empty_pages_render(self):
        self.assertContains(self.client.get(reverse("services")), "service details will be available soon")
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        member = TeamMember.objects.create(name="New member", designation="Designer", photo="team/new.jpg")
        self.assertContains(self.client.get(reverse("team_portfolio", args=[member.pk])), "Portfolio projects will be shared soon")

    def test_admin_can_publish_and_edit_service_and_portfolio(self):
        user = get_user_model().objects.create_superuser(username="editor", password="test-only-password")
        self.client.force_login(user)
        response = self.client.post(reverse("admin:Ivory_service_add"), {
            "title": "Admin service", "description": "Service details", "order": 0, "is_active": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Service.objects.filter(title="Admin service", is_active=True).exists())
        member = TeamMember.objects.create(name="Editor member", designation="Designer", photo="team/editor.jpg")
        self.assertContains(self.client.get(reverse("admin:Ivory_teammember_change", args=[member.pk])), 'portfolio-TOTAL_FORMS')
        self.assertEqual(self.client.get(reverse("admin:Ivory_teamportfolio_add")).status_code, 200)

    def test_admin_uploads_portfolio_image_under_team_member(self):
        user = get_user_model().objects.create_superuser(username="portfolio-editor", password="test-only-password")
        self.client.force_login(user)
        member = TeamMember.objects.create(name="Member", designation="Architect", photo="team/member.jpg")
        image = BytesIO()
        Image.new("RGB", (8, 8), "white").save(image, format="PNG")
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("admin:Ivory_teammember_change", args=[member.pk]), {
                "name": member.name, "designation": member.designation, "order": 0, "is_active": "on",
                "portfolio-TOTAL_FORMS": 1, "portfolio-INITIAL_FORMS": 0,
                "portfolio-MIN_NUM_FORMS": 0, "portfolio-MAX_NUM_FORMS": 1000,
                "portfolio-0-member": member.pk, "portfolio-0-title": "Uploaded work",
                "portfolio-0-image": SimpleUploadedFile("project.png", image.getvalue(), content_type="image/png"),
                "portfolio-0-description": "Created in the team member editor",
                "portfolio-0-order": 0, "portfolio-0-is_active": "on", "_save": "Save",
            })
            self.assertEqual(response.status_code, 302)
            entry = member.portfolio.get()
            self.assertTrue(entry.image.storage.exists(entry.image.name))
            self.assertContains(self.client.get(reverse("team_portfolio", args=[member.pk])), "Uploaded work")
