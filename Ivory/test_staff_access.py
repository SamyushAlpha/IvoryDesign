from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Project, ProjectCategory


class StaffAccessTests(TestCase):
    def setUp(self):
        category = ProjectCategory.objects.create(name="Homes", slug="homes")
        self.project = Project.objects.create(
            name="Permission test project",
            category=category,
            image="projects/test.jpg",
        )

    def staff_with(self, username, *permissions):
        user = get_user_model().objects.create_user(
            username=username,
            password="strong-test-password",
            is_staff=True,
        )
        user.user_permissions.add(*Permission.objects.filter(codename__in=permissions))
        return user

    def test_project_viewer_cannot_create_edit_or_delete_projects(self):
        self.client.force_login(self.staff_with("viewer", "view_project"))

        self.assertEqual(self.client.get(reverse("admin:Ivory_project_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:Ivory_project_add")).status_code, 403)
        detail = self.client.get(reverse("admin:Ivory_project_change", args=[self.project.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'name="_save"')
        self.assertEqual(
            self.client.get(reverse("admin:Ivory_project_delete", args=[self.project.pk])).status_code,
            403,
        )

    def test_project_editor_can_create_and_edit_without_delete_access(self):
        self.client.force_login(self.staff_with(
            "editor", "view_project", "add_project", "change_project"
        ))

        self.assertEqual(self.client.get(reverse("admin:Ivory_project_add")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:Ivory_project_change", args=[self.project.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("admin:Ivory_project_delete", args=[self.project.pk])).status_code,
            403,
        )

    def test_only_superusers_can_manage_staff_accounts_and_roles(self):
        user = self.staff_with("account-manager", "view_user", "change_user", "view_group", "change_group")
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist")).status_code, 403)

        owner = get_user_model().objects.create_superuser(
            username="owner", password="strong-owner-password"
        )
        self.client.force_login(owner)
        account_page = self.client.get(reverse("admin:auth_user_add"))
        self.assertEqual(account_page.status_code, 200)
        self.assertContains(account_page, "Access control")
        self.assertContains(account_page, 'name="user_permissions"')
        self.assertEqual(self.client.get(reverse("admin:auth_group_add")).status_code, 200)

        view_project = Permission.objects.get(codename="view_project")
        response = self.client.post(reverse("admin:auth_user_add"), {
            "username": "new-project-viewer",
            "password1": "Cobalt-Lantern-7391",
            "password2": "Cobalt-Lantern-7391",
            "is_active": "on",
            "is_staff": "on",
            "user_permissions": [view_project.pk],
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="new-project-viewer")
        self.assertTrue(created.is_staff)
        self.assertTrue(created.has_perm("Ivory.view_project"))
        self.assertFalse(created.has_perm("Ivory.change_project"))
