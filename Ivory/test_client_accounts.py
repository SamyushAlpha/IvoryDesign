from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .admin import ClientProjectAccountAdminForm
from .models import ClientProjectAccount, ClientProjectPayment


class ClientProjectAccountTests(TestCase):
    def test_account_balance_tracks_partial_payments(self):
        account = ClientProjectAccount.objects.create(
            client_name="Sita Shrestha",
            client_location="Lalitpur",
            project_started_on=date(2026, 9, 1),
            agreed_amount=Decimal("500000.00"),
        )
        ClientProjectPayment.objects.create(
            account=account,
            amount=Decimal("100000.00"),
            paid_on=date(2026, 9, 1),
        )
        ClientProjectPayment.objects.create(
            account=account,
            amount=Decimal("150000.00"),
            paid_on=date(2026, 9, 20),
        )

        self.assertEqual(account.payment_total, Decimal("250000.00"))
        self.assertEqual(account.remaining_amount, Decimal("250000.00"))
        self.assertEqual(account.payment_status, "Partly paid")

    def test_initial_advance_cannot_exceed_agreed_amount(self):
        form = ClientProjectAccountAdminForm(data={
            "client_name": "Sita Shrestha",
            "client_location": "Lalitpur",
            "project_started_on": "2026-09-01",
            "agreed_amount": "500000.00",
            "initial_advance": "500000.01",
            "advance_received_on": "2026-09-01",
            "notes": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("Advance cannot be greater", form.errors["initial_advance"][0])


class ClientProjectAdminFlowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="owner-client-ledger",
            email="owner@example.com",
            password="test-password",
        )
        self.client.force_login(self.admin)

    def _create_account(self):
        response = self.client.post(
            reverse("admin:Ivory_clientprojectaccount_add"),
            {
                "client_name": "Ram Bahadur",
                "client_location": "Bhaktapur",
                "project_started_on": "2026-09-10",
                "agreed_amount": "500000.00",
                "notes": "Residence interior",
                "initial_advance": "100000.00",
                "advance_received_on": "2026-09-10",
                "payments-TOTAL_FORMS": "0",
                "payments-INITIAL_FORMS": "0",
                "payments-MIN_NUM_FORMS": "0",
                "payments-MAX_NUM_FORMS": "0",
                "_save": "Save",
            },
        )
        return response, ClientProjectAccount.objects.get()

    def test_create_account_saves_advance_and_opens_invoice(self):
        response, account = self._create_account()
        payment = account.payments.get()

        self.assertRedirects(
            response,
            reverse("admin:client_project_payment_invoice", args=(payment.public_id,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.amount, Decimal("100000.00"))
        self.assertEqual(payment.invoice_number, "IVY-CLI-2026-00001")
        self.assertEqual(account.remaining_amount, Decimal("400000.00"))

        invoice = self.client.get(reverse("admin:client_project_payment_invoice", args=(payment.public_id,)))
        self.assertEqual(invoice.status_code, 200)
        self.assertEqual(invoice["Content-Type"], "application/pdf")
        self.assertIn("Ram-Bahadur-IVY-CLI-2026-00001.pdf", invoice["Content-Disposition"])
        self.assertTrue(invoice.content.startswith(b"%PDF"))

    def test_add_partial_payment_reduces_remaining_balance_and_creates_invoice(self):
        _, account = self._create_account()
        response = self.client.post(
            reverse("admin:client_project_account_pay", args=(account.pk,)),
            {"amount": "150000.00", "paid_on": "2026-09-25", "note": "Second installment"},
        )
        payment = account.payments.order_by("-pk").first()

        self.assertRedirects(
            response,
            reverse("admin:client_project_payment_invoice", args=(payment.public_id,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.invoice_number, "IVY-CLI-2026-00002")
        self.assertEqual(account.remaining_amount, Decimal("250000.00"))

    def test_payment_cannot_exceed_remaining_balance(self):
        _, account = self._create_account()
        response = self.client.post(
            reverse("admin:client_project_account_pay", args=(account.pk,)),
            {"amount": "400000.01", "paid_on": "2026-09-25", "note": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment cannot be greater")
        self.assertEqual(account.payments.count(), 1)

    def test_dashboard_shows_total_client_payments_collected(self):
        _, account = self._create_account()
        ClientProjectPayment.objects.create(
            account=account,
            amount=Decimal("150000.00"),
            paid_on=date(2026, 9, 25),
        )

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total client payments collected")
        self.assertContains(response, "NPR 250,000.00")

    def test_account_list_shows_financial_summary_and_payment_action(self):
        _, account = self._create_account()
        response = self.client.get(reverse("admin:Ivory_clientprojectaccount_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, account.client_name)
        self.assertContains(response, "NPR 500,000.00")
        self.assertContains(response, "NPR 100,000.00")
        self.assertContains(response, "NPR 400,000.00")
        self.assertContains(response, "Add payment &amp; invoice")
