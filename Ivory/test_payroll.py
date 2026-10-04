from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .admin import SalaryRecordAdminForm
from .models import SalaryAdvance, SalaryPayment, SalaryRecord, TeamMember


class SalaryRecordTests(TestCase):
    def setUp(self):
        self.member = TeamMember.objects.create(
            name="Asha Rai",
            designation="Interior Designer",
            photo="team/asha.jpg",
        )

    def test_salary_summary_tracks_advance_payment_and_pending_balance(self):
        record = SalaryRecord.objects.create(
            member=self.member,
            salary_month=date(2026, 9, 18),
            salary_amount=Decimal("50000.00"),
        )
        SalaryAdvance.objects.create(
            salary_record=record,
            amount=Decimal("5000.00"),
            given_on=date(2026, 9, 10),
        )
        SalaryPayment.objects.create(
            salary_record=record,
            amount=Decimal("30000.00"),
            paid_on=date(2026, 9, 28),
        )
        record.refresh_from_db()

        self.assertEqual(record.salary_month, date(2026, 9, 1))
        self.assertEqual(record.advance_total, Decimal("5000.00"))
        self.assertEqual(record.payment_total, Decimal("30000.00"))
        self.assertEqual(record.pending_amount, Decimal("15000.00"))
        self.assertEqual(record.payment_status, "Partly paid")

    def test_monthly_salary_form_uses_team_member_saved_salary(self):
        self.member.monthly_salary = Decimal("50000.00")
        self.member.save(update_fields=("monthly_salary",))
        form = SalaryRecordAdminForm(data={
            "member": self.member.pk,
            "salary_month": "2026-10",
            "salary_amount": "",
            "notes": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        record = form.save()
        self.assertEqual(record.salary_amount, Decimal("50000.00"))


class SalaryAdminFlowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="owner",
            email="owner@example.com",
            password="test-password",
        )
        self.client.force_login(self.admin)
        member = TeamMember.objects.create(
            name="Nima Sherpa",
            designation="Architect",
            photo="team/nima.jpg",
        )
        self.record = SalaryRecord.objects.create(
            member=member,
            salary_month=date(2026, 8, 1),
            salary_amount=Decimal("60000.00"),
        )
        SalaryAdvance.objects.create(
            salary_record=self.record,
            amount=Decimal("10000.00"),
            given_on=date(2026, 8, 12),
        )

    def test_pay_salary_creates_numbered_invoice_and_pdf(self):
        response = self.client.post(
            reverse("admin:salary_record_pay", args=(self.record.pk,)),
            {"amount": "50000.00", "paid_on": "2026-08-30", "note": "August salary"},
        )
        payment = SalaryPayment.objects.get()

        self.assertRedirects(response, reverse("admin:salary_payment_invoice", args=(payment.public_id,)), fetch_redirect_response=False)
        self.assertEqual(payment.invoice_number, "IVY-SAL-2026-00001")
        self.assertEqual(self.record.pending_amount, Decimal("0.00"))
        pdf = self.client.get(reverse("admin:salary_payment_invoice", args=(payment.public_id,)))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertIn("Nima-Sherpa-Salary-August-2026.pdf", pdf["Content-Disposition"])
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_pay_salary_rejects_more_than_pending_balance(self):
        response = self.client.post(
            reverse("admin:salary_record_pay", args=(self.record.pk,)),
            {"amount": "50000.01", "paid_on": "2026-08-30", "note": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment cannot be greater")
        self.assertEqual(SalaryPayment.objects.count(), 0)

    def test_salary_list_shows_clear_financial_summary(self):
        response = self.client.get(reverse("admin:Ivory_salaryrecord_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nima Sherpa")
        self.assertContains(response, "August 2026")
        self.assertContains(response, "NPR 60,000.00")
        self.assertContains(response, "NPR 10,000.00")
        self.assertContains(response, "NPR 50,000.00")
        self.assertContains(response, "Partly paid")
        self.assertContains(response, "Pay &amp; create invoice")
        self.assertContains(response, "A monthly salary starts as money owed")

    def test_advance_has_its_own_clear_admin_list(self):
        response = self.client.get(reverse("admin:Ivory_salaryadvance_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nima Sherpa")
        self.assertContains(response, "Deducted from August 2026")
        self.assertContains(response, "NPR 10,000.00")

    def test_advance_form_creates_an_independent_record(self):
        response = self.client.get(reverse("admin:Ivory_salaryadvance_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team member")
        self.assertContains(response, "remains unused")
        self.assertNotContains(response, "Salary month")
        self.assertNotContains(response, "No results found")

    def test_superuser_decides_when_an_advance_is_deducted(self):
        member = TeamMember.objects.create(
            name="Pema Lama",
            designation="Site Supervisor",
            photo="team/pema.jpg",
            monthly_salary=Decimal("50000.00"),
        )

        response = self.client.post(
            reverse("admin:Ivory_salaryadvance_add"),
            {
                "member": member.pk,
                "amount": "10000.00",
                "given_on": "2026-10-05",
                "note": "October advance",
                "_save": "Save",
            },
        )

        self.assertRedirects(response, reverse("admin:Ivory_salaryadvance_changelist"))
        advance = SalaryAdvance.objects.get(member=member)
        self.assertIsNone(advance.salary_record)
        self.assertFalse(SalaryRecord.objects.filter(member=member).exists())

        response = self.client.post(
            reverse("admin:Ivory_salaryrecord_add"),
            {
                "member": member.pk,
                "salary_month": "2026-10",
                "salary_amount": "",
                "notes": "",
                "advances_to_deduct": [advance.pk],
                "payments-TOTAL_FORMS": "0",
                "payments-INITIAL_FORMS": "0",
                "payments-MIN_NUM_FORMS": "0",
                "payments-MAX_NUM_FORMS": "0",
                "_save": "Save",
            },
        )

        self.assertRedirects(response, reverse("admin:Ivory_salaryrecord_changelist"))
        record = SalaryRecord.objects.get(member=member, salary_month=date(2026, 10, 1))
        advance.refresh_from_db()
        self.assertEqual(advance.salary_record, record)
        self.assertEqual(record.salary_amount, Decimal("50000.00"))
        self.assertEqual(record.advance_total, Decimal("10000.00"))
        self.assertEqual(record.pending_amount, Decimal("40000.00"))

    def test_member_advance_lookup_only_lists_unused_or_current_advances(self):
        unused = SalaryAdvance.objects.create(
            member=self.record.member,
            amount=Decimal("5000.00"),
            given_on=date(2026, 9, 1),
        )

        response = self.client.get(
            reverse("admin:salary_record_member_advances", args=(self.record.member_id,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["advances"], [{
            "id": unused.pk,
            "amount": "5000.00",
            "given_on": "2026-09-01",
            "note": "",
            "selected": False,
        }])

    def test_monthly_salary_form_explains_unpaid_and_pay_now_options(self):
        response = self.client.get(reverse("admin:Ivory_salaryrecord_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This starts as an unpaid balance")
        self.assertContains(response, 'value="Save & pay balance"')
        self.assertContains(response, "admin/payroll.js")

    def test_member_salary_lookup_returns_saved_default(self):
        self.record.member.monthly_salary = Decimal("50000.00")
        self.record.member.save(update_fields=("monthly_salary",))

        response = self.client.get(
            reverse("admin:salary_record_member_salary", args=(self.record.member_id,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["monthly_salary"], "50000.00")

    def test_partial_payment_leaves_ten_thousand_pending_and_creates_invoice(self):
        member = TeamMember.objects.create(
            name="Maya Gurung",
            designation="Designer",
            photo="team/maya.jpg",
            monthly_salary=Decimal("50000.00"),
        )
        record = SalaryRecord.objects.create(
            member=member,
            salary_month=date(2026, 9, 1),
            salary_amount=member.monthly_salary,
        )

        response = self.client.post(
            reverse("admin:salary_record_pay", args=(record.pk,)),
            {"amount": "40000.00", "paid_on": "2026-09-28", "note": "Partial salary"},
        )
        payment = SalaryPayment.objects.get(salary_record=record)

        self.assertRedirects(
            response,
            reverse("admin:salary_payment_invoice", args=(payment.public_id,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(record.pending_amount, Decimal("10000.00"))
        self.assertEqual(record.payment_status, "Partly paid")
        invoice = self.client.get(reverse("admin:salary_payment_invoice", args=(payment.public_id,)))
        self.assertEqual(invoice.status_code, 200)
        self.assertTrue(invoice.content.startswith(b"%PDF"))

    def test_superuser_can_delete_monthly_salary_with_its_invoice(self):
        payment = SalaryPayment.objects.create(
            salary_record=self.record,
            amount=Decimal("50000.00"),
            paid_on=date(2026, 8, 30),
        )
        changelist = reverse("admin:Ivory_salaryrecord_changelist")
        selection = {
            "action": "delete_selected",
            "_selected_action": [str(self.record.pk)],
        }

        confirmation = self.client.post(changelist, selection)
        self.assertEqual(confirmation.status_code, 200)
        self.assertNotContains(confirmation, "doesn’t have permission")
        self.assertContains(confirmation, payment.invoice_number)

        response = self.client.post(changelist, {**selection, "post": "yes"})
        self.assertRedirects(response, changelist)
        self.assertEqual(SalaryRecord.objects.count(), 0)
        self.assertEqual(SalaryPayment.objects.count(), 0)


class TeamMemberPayrollPrivacyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="asha-staff",
            password="staff-password",
            is_staff=True,
        )
        payroll_permissions = Permission.objects.filter(codename__in=(
            "view_salaryrecord", "add_salaryrecord", "change_salaryrecord",
            "view_salaryadvance", "add_salaryadvance", "change_salaryadvance",
            "view_salarypayment",
        ))
        self.user.user_permissions.add(*payroll_permissions)
        self.member = TeamMember.objects.create(
            user=self.user,
            name="Asha Staff",
            designation="Architect",
            photo="team/asha-staff.jpg",
            monthly_salary=Decimal("50000.00"),
        )
        self.other_member = TeamMember.objects.create(
            name="Other Person",
            designation="Engineer",
            photo="team/other-person.jpg",
            monthly_salary=Decimal("70000.00"),
        )
        self.own_record = SalaryRecord.objects.create(
            member=self.member,
            salary_month=date(2026, 9, 1),
            salary_amount=Decimal("50000.00"),
        )
        self.other_record = SalaryRecord.objects.create(
            member=self.other_member,
            salary_month=date(2026, 9, 1),
            salary_amount=Decimal("70000.00"),
        )
        self.own_advance = SalaryAdvance.objects.create(
            member=self.member,
            amount=Decimal("5000.00"),
            given_on=date(2026, 9, 5),
        )
        self.other_advance = SalaryAdvance.objects.create(
            member=self.other_member,
            amount=Decimal("9000.00"),
            given_on=date(2026, 9, 5),
        )
        self.client.force_login(self.user)

    def test_team_member_sees_only_their_salary_records(self):
        response = self.client.get(reverse("admin:Ivory_salaryrecord_changelist"))
        add_page = self.client.get(reverse("admin:Ivory_salaryrecord_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Staff")
        self.assertNotContains(response, "Other Person")
        self.assertContains(add_page, "Asha Staff")
        self.assertNotContains(add_page, "Other Person")
        self.assertEqual(
            self.client.get(reverse("admin:Ivory_salaryrecord_change", args=(self.own_record.pk,))).status_code,
            200,
        )
        self.assertNotEqual(
            self.client.get(reverse("admin:Ivory_salaryrecord_change", args=(self.other_record.pk,))).status_code,
            200,
        )

    def test_team_member_sees_only_their_salary_advances(self):
        response = self.client.get(reverse("admin:Ivory_salaryadvance_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Staff")
        self.assertNotContains(response, "Other Person")
        self.assertEqual(
            self.client.get(reverse("admin:Ivory_salaryadvance_change", args=(self.own_advance.pk,))).status_code,
            200,
        )
        self.assertNotEqual(
            self.client.get(reverse("admin:Ivory_salaryadvance_change", args=(self.other_advance.pk,))).status_code,
            200,
        )

    def test_member_lookup_endpoints_do_not_expose_another_member(self):
        own_salary = self.client.get(
            reverse("admin:salary_record_member_salary", args=(self.member.pk,))
        )
        other_salary = self.client.get(
            reverse("admin:salary_record_member_salary", args=(self.other_member.pk,))
        )
        own_advances = self.client.get(
            reverse("admin:salary_record_member_advances", args=(self.member.pk,))
        )
        other_advances = self.client.get(
            reverse("admin:salary_record_member_advances", args=(self.other_member.pk,))
        )

        self.assertEqual(own_salary.status_code, 200)
        self.assertEqual(own_advances.status_code, 200)
        self.assertEqual(other_salary.status_code, 404)
        self.assertEqual(other_advances.status_code, 404)

    def test_team_member_cannot_open_another_members_invoice(self):
        own_payment = SalaryPayment.objects.create(
            salary_record=self.own_record,
            amount=Decimal("1000.00"),
            paid_on=date(2026, 9, 20),
        )
        other_payment = SalaryPayment.objects.create(
            salary_record=self.other_record,
            amount=Decimal("1000.00"),
            paid_on=date(2026, 9, 20),
        )

        own_invoice = self.client.get(
            reverse("admin:salary_payment_invoice", args=(own_payment.public_id,))
        )
        other_invoice = self.client.get(
            reverse("admin:salary_payment_invoice", args=(other_payment.public_id,))
        )

        self.assertEqual(own_invoice.status_code, 200)
        self.assertEqual(other_invoice.status_code, 404)
