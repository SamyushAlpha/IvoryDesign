from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import SalaryRecordAdminForm
from .models import AttendanceRecord, SalaryRecord, TeamMember, monthly_attendance_salary


class AttendanceSalaryTests(TestCase):
    def setUp(self):
        self.member = TeamMember.objects.create(
            name="Asha Rai",
            designation="Interior Designer",
            photo="team/asha.jpg",
            monthly_salary=Decimal("50000.00"),
        )

    def test_approved_full_and_half_day_leave_reduce_monthly_salary(self):
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 7),
            attendance_type=AttendanceRecord.AttendanceType.FULL_DAY_LEAVE,
            approval_status=AttendanceRecord.ApprovalStatus.APPROVED,
        )
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 8),
            attendance_type=AttendanceRecord.AttendanceType.HALF_DAY_LEAVE,
            approval_status=AttendanceRecord.ApprovalStatus.APPROVED,
        )

        summary = monthly_attendance_salary(self.member, date(2026, 9, 1), self.member.monthly_salary)

        self.assertEqual(summary["working_days"], 26)
        self.assertEqual(summary["leave_units"], Decimal("1.5"))
        self.assertEqual(summary["deduction"], Decimal("2884.62"))
        self.assertEqual(summary["payable_salary"], Decimal("47115.38"))

    def test_pending_or_saturday_leave_is_not_deducted(self):
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 9),
            attendance_type=AttendanceRecord.AttendanceType.FULL_DAY_LEAVE,
            approval_status=AttendanceRecord.ApprovalStatus.PENDING,
        )
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 12),
            attendance_type=AttendanceRecord.AttendanceType.FULL_DAY_LEAVE,
            approval_status=AttendanceRecord.ApprovalStatus.APPROVED,
        )

        summary = monthly_attendance_salary(self.member, date(2026, 9, 1), self.member.monthly_salary)

        self.assertEqual(summary["leave_units"], Decimal("0.0"))
        self.assertEqual(summary["deduction"], Decimal("0.00"))
        self.assertEqual(summary["payable_salary"], Decimal("50000.00"))

    def test_salary_form_saves_attendance_snapshot(self):
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 7),
            attendance_type=AttendanceRecord.AttendanceType.FULL_DAY_LEAVE,
            approval_status=AttendanceRecord.ApprovalStatus.APPROVED,
        )
        form = SalaryRecordAdminForm(data={
            "member": self.member.pk,
            "salary_month": "2026-09",
            "salary_amount": "50000.00",
            "notes": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        record = form.save()
        self.assertEqual(record.gross_salary, Decimal("50000.00"))
        self.assertEqual(record.attendance_leave_units, Decimal("1"))
        self.assertEqual(record.attendance_deduction, Decimal("1923.08"))
        self.assertEqual(record.salary_amount, Decimal("48076.92"))

    def test_worked_hours_are_totalled_in_monthly_summary(self):
        entry = timezone.make_aware(datetime(2026, 9, 10, 9, 0))
        exit_time = timezone.make_aware(datetime(2026, 9, 10, 17, 30))
        AttendanceRecord.objects.create(
            member=self.member,
            attendance_date=date(2026, 9, 10),
            attendance_type=AttendanceRecord.AttendanceType.PRESENT,
            check_in_at=entry,
            check_out_at=exit_time,
        )

        summary = monthly_attendance_salary(self.member, date(2026, 9, 1), self.member.monthly_salary)

        self.assertEqual(summary["worked_hours"], Decimal("8.50"))


class AttendanceAdminPrivacyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="attendance-member",
            password="staff-password",
            is_staff=True,
        )
        self.member = TeamMember.objects.create(
            user=self.user,
            name="Attendance Member",
            designation="Designer",
            photo="team/member.jpg",
        )
        self.other = TeamMember.objects.create(
            name="Other Member",
            designation="Architect",
            photo="team/other.jpg",
        )
        self.client.force_login(self.user)

    def test_linked_member_can_record_present_without_manual_permission(self):
        response = self.client.post(
            reverse("admin:Ivory_attendancerecord_add"),
            {
                "member": self.member.pk,
                "attendance_date": "2026-09-30",
                "attendance_type": AttendanceRecord.AttendanceType.PRESENT,
                "note": "On site",
                "_save": "Save",
            },
        )

        self.assertRedirects(response, reverse("admin:Ivory_attendancerecord_changelist"))
        attendance = AttendanceRecord.objects.get()
        self.assertEqual(attendance.member, self.member)
        self.assertEqual(attendance.approval_status, AttendanceRecord.ApprovalStatus.APPROVED)

    def test_linked_member_can_check_in_and_check_out(self):
        entry = timezone.make_aware(datetime(2026, 9, 30, 9, 15))
        exit_time = timezone.make_aware(datetime(2026, 9, 30, 17, 45))
        with patch("Ivory.admin.timezone.now", return_value=entry):
            response = self.client.post(reverse("admin:attendance_check_in"))
        self.assertRedirects(response, reverse("admin:Ivory_attendancerecord_changelist"))
        attendance = AttendanceRecord.objects.get()
        self.assertEqual(attendance.check_in_at, entry)
        self.assertIsNone(attendance.check_out_at)

        with patch("Ivory.admin.timezone.now", return_value=exit_time):
            response = self.client.post(reverse("admin:attendance_check_out"))
        self.assertRedirects(response, reverse("admin:Ivory_attendancerecord_changelist"))
        attendance.refresh_from_db()
        self.assertEqual(attendance.check_out_at, exit_time)
        self.assertEqual(attendance.worked_hours, Decimal("8.50"))

    def test_leave_request_is_pending_and_other_members_are_hidden(self):
        response = self.client.post(
            reverse("admin:Ivory_attendancerecord_add"),
            {
                "member": self.member.pk,
                "attendance_date": "2026-09-29",
                "attendance_type": AttendanceRecord.AttendanceType.HALF_DAY_LEAVE,
                "note": "Appointment",
                "_save": "Save",
            },
        )

        self.assertRedirects(response, reverse("admin:Ivory_attendancerecord_changelist"))
        attendance = AttendanceRecord.objects.get()
        self.assertEqual(attendance.approval_status, AttendanceRecord.ApprovalStatus.PENDING)
        list_response = self.client.get(reverse("admin:Ivory_attendancerecord_changelist"))
        self.assertContains(list_response, self.member.name)
        self.assertNotContains(list_response, self.other.name)

    def test_linked_member_cannot_submit_attendance_for_someone_else(self):
        response = self.client.post(
            reverse("admin:Ivory_attendancerecord_add"),
            {
                "member": self.other.pk,
                "attendance_date": "2026-09-30",
                "attendance_type": AttendanceRecord.AttendanceType.PRESENT,
                "note": "",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.count(), 0)
