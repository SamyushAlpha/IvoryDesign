from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Project, ProjectCategory, TeamMember


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
        member = TeamMember.objects.create(
            name="Linked staff member",
            designation="Architect",
            photo="team/linked.jpg",
        )
        response = self.client.post(reverse("admin:auth_user_add"), {
            "username": "new-project-viewer",
            "password1": "Cobalt-Lantern-7391",
            "password2": "Cobalt-Lantern-7391",
            "is_active": "on",
            "is_staff": "on",
            "user_permissions": [view_project.pk],
            "team_member": member.pk,
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="new-project-viewer")
        self.assertTrue(created.is_staff)
        self.assertTrue(created.has_perm("Ivory.view_project"))
        self.assertFalse(created.has_perm("Ivory.change_project"))
        member.refresh_from_db()
        self.assertEqual(member.user, created)

    def test_existing_staff_account_can_be_linked_and_shows_member_photo(self):
        owner = get_user_model().objects.create_superuser(
            username="existing-owner",
            password="strong-owner-password",
            email="owner@example.com",
        )
        member = TeamMember.objects.create(
            name="Existing account member",
            designation="Designer",
            photo="team/existing-member.jpg",
        )
        self.client.force_login(owner)

        change_page = self.client.get(reverse("admin:auth_user_change", args=[owner.pk]))
        self.assertEqual(change_page.status_code, 200)
        self.assertContains(change_page, 'name="team_member"')
        self.assertContains(change_page, "Existing account member")

        response = self.client.post(reverse("admin:auth_user_change", args=[owner.pk]), {
            "username": owner.username,
            "email": owner.email,
            "is_active": "on",
            "is_staff": "on",
            "is_superuser": "on",
            "team_member": member.pk,
            "date_joined_0": owner.date_joined.date().isoformat(),
            "date_joined_1": owner.date_joined.time().strftime("%H:%M:%S"),
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.user, owner)

        dashboard = self.client.get(reverse("admin:index"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "/media/team/existing-member.jpg")

    def test_live_support_checkbox_grants_existing_member_chat_access(self):
        owner = get_user_model().objects.create_superuser(
            username="support-owner",
            password="strong-owner-password",
        )
        member_user = get_user_model().objects.create_user(
            username="support-member",
            password="strong-member-password",
            is_staff=True,
        )
        self.client.force_login(owner)

        change_page = self.client.get(reverse("admin:auth_user_change", args=[member_user.pk]))
        self.assertContains(change_page, "Live Support access")

        response = self.client.post(reverse("admin:auth_user_change", args=[member_user.pk]), {
            "username": member_user.username,
            "is_active": "on",
            "is_staff": "on",
            "can_use_live_support": "on",
            "date_joined_0": member_user.date_joined.date().isoformat(),
            "date_joined_1": member_user.date_joined.time().strftime("%H:%M:%S"),
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        member_user.refresh_from_db()
        self.assertTrue(member_user.has_perm("Ivory.view_supportconversation"))
        self.assertTrue(member_user.has_perm("Ivory.change_supportconversation"))

        self.client.force_login(member_user)
        self.assertEqual(self.client.get(reverse("support_inbox")).status_code, 200)
