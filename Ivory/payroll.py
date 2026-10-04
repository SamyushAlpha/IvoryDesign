from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from reportlab.graphics import renderPDF
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg


def _money(value):
    return f"NPR {Decimal(value):,.2f}"


def salary_invoice_response(payment):
    record = payment.salary_record
    member = record.member
    advances = record.advance_total
    paid_before = sum(
        (entry.amount for entry in record.payments.exclude(pk=payment.pk)),
        Decimal("0.00"),
    )
    remaining = max(
        record.salary_amount - advances - paid_before - payment.amount,
        Decimal("0.00"),
    )

    page_width, page_height = 500, 610
    paper_left, paper_right = 28, page_width - 28
    paper_bottom, paper_top = 24, page_height - 24
    ink = HexColor("#132321")
    muted = HexColor("#66716E")
    blue = HexColor("#D5E5F5")
    pale = HexColor("#F4F7F6")
    rule = HexColor("#394743")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    pdf.setTitle(f"{member.name} Salary {record.salary_month:%B %Y}")
    pdf.setAuthor("Ivory Arvena Interior & Design")
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor("#89918F"))
    pdf.setLineWidth(.7)
    pdf.rect(paper_left, paper_bottom, paper_right - paper_left, paper_top - paper_bottom, fill=0, stroke=1)

    center = page_width / 2
    logo_path = settings.BASE_DIR / "Ivory" / "invoice_assets" / "Ivoryarvena.svg"
    logo = svg2rlg(str(logo_path)) if logo_path.exists() else None
    if logo:
        left, bottom, right, top = logo.getBounds()
        width, height = right - left, top - bottom
        scale = min(80 / width, 30 / height)
        pdf.saveState()
        pdf.translate(center - width * scale / 2 - left * scale, paper_top - 35 - bottom * scale)
        pdf.scale(scale, scale)
        renderPDF.draw(logo, pdf, 0, 0)
        pdf.restoreState()

    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(center, paper_top - 50, "IVORY DESIGN STUDIO")
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(center, paper_top - 67, "Kathmandu, Nepal  |  +977 9825776806")
    pdf.drawCentredString(center, paper_top - 79, "ivorydesign2083@gmail.com  |  ivoryarvena.vercel.app")

    pdf.setFillColor(blue)
    pdf.rect(paper_left + 1, paper_top - 122, paper_right - paper_left - 2, 28, fill=1, stroke=0)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(paper_left + 18, paper_top - 112, "SALARY PAYMENT RECEIPT")
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(paper_right - 18, paper_top - 111, payment.invoice_number)

    details_top = paper_top - 154
    left_x, right_x = paper_left + 24, center + 24
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left_x, details_top, "TEAM MEMBER")
    pdf.drawString(right_x, details_top, "PAYMENT DETAILS")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(left_x, details_top - 17, member.name)
    pdf.drawString(left_x, details_top - 32, member.designation)
    pdf.drawString(left_x, details_top - 47, f"Salary month: {record.salary_month:%B %Y}")
    pdf.drawString(right_x, details_top - 17, f"Paid on: {payment.paid_on:%d %B %Y}")
    pdf.drawString(right_x, details_top - 32, f"Receipt: {payment.invoice_number}")
    pdf.drawString(right_x, details_top - 47, "Currency: Nepalese Rupee")

    table_left, table_right = paper_left + 24, paper_right - 24
    y = details_top - 86
    row_height = 30
    label_width = 245
    rows = (
        ("Monthly salary before attendance", record.salary_before_attendance, False),
        ("Approved leave deduction", record.attendance_deduction, False),
        ("Salary after attendance", record.salary_amount, False),
        ("Advance deducted", advances, False),
        ("Previous salary payments", paid_before, False),
        ("Paid with this receipt", payment.amount, True),
        ("Pending after this payment", remaining, False),
    )
    for label, amount, highlighted in rows:
        pdf.setFillColor(blue if highlighted else pale if label.startswith("Pending") else HexColor("#FFFFFF"))
        pdf.setStrokeColor(rule)
        pdf.rect(table_left, y, table_right - table_left, row_height, fill=1, stroke=1)
        pdf.line(table_left + label_width, y, table_left + label_width, y + row_height)
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold" if highlighted else "Helvetica", 8.5)
        pdf.drawString(table_left + 12, y + 10, label)
        pdf.drawRightString(table_right - 12, y + 10, _money(amount))
        y -= row_height

    if payment.note:
        note = payment.note.strip()
        max_width = table_right - table_left - 22
        while note and stringWidth(note, "Helvetica", 7.5) > max_width:
            note = note[:-1]
        if note != payment.note.strip():
            note = note.rstrip() + "…"
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(table_left, y - 18, f"Note: {note}")

    signature_width = 154
    signature_height = 72
    signature_left = table_right - signature_width
    signature_bottom = paper_bottom + 56
    pdf.setFillColor(pale)
    pdf.setStrokeColor(HexColor("#9AA29F"))
    pdf.roundRect(signature_left, signature_bottom, signature_width, signature_height, 3, fill=1, stroke=1)
    pdf.setStrokeColor(ink)
    pdf.line(signature_left + 18, signature_bottom + 37, table_right - 18, signature_bottom + 37)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(signature_left + signature_width / 2, signature_bottom + 23, member.name)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawCentredString(signature_left + signature_width / 2, signature_bottom + 11, "Team member signature")

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(table_left, signature_bottom + 46, "Received and acknowledged by")
    pdf.drawString(table_left, signature_bottom + 31, member.name)
    pdf.drawString(table_left, signature_bottom + 16, f"For salary month {record.salary_month:%B %Y}")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(center, paper_bottom + 15, "Salary payment record generated by Ivory Arvena Interior & Design")

    pdf.showPage()
    pdf.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{payment.invoice_filename}"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def client_payment_invoice_response(payment):
    account = payment.account
    paid_before = sum(
        (entry.amount for entry in account.payments.filter(pk__lt=payment.pk)),
        Decimal("0.00"),
    )
    remaining = max(account.agreed_amount - paid_before - payment.amount, Decimal("0.00"))

    page_width, page_height = 500, 610
    paper_left, paper_right = 28, page_width - 28
    paper_bottom, paper_top = 24, page_height - 24
    ink = HexColor("#132321")
    muted = HexColor("#66716E")
    blue = HexColor("#D5E5F5")
    pale = HexColor("#F4F7F6")
    rule = HexColor("#394743")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    pdf.setTitle(f"{account.client_name} Payment {payment.paid_on:%d %B %Y}")
    pdf.setAuthor("Ivory Arvena Interior & Design")
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor("#89918F"))
    pdf.setLineWidth(.7)
    pdf.rect(paper_left, paper_bottom, paper_right - paper_left, paper_top - paper_bottom, fill=0, stroke=1)

    center = page_width / 2
    logo_path = settings.BASE_DIR / "Ivory" / "invoice_assets" / "Ivoryarvena.svg"
    logo = svg2rlg(str(logo_path)) if logo_path.exists() else None
    if logo:
        left, bottom, right, top = logo.getBounds()
        width, height = right - left, top - bottom
        scale = min(80 / width, 30 / height)
        pdf.saveState()
        pdf.translate(center - width * scale / 2 - left * scale, paper_top - 35 - bottom * scale)
        pdf.scale(scale, scale)
        renderPDF.draw(logo, pdf, 0, 0)
        pdf.restoreState()

    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(center, paper_top - 50, "IVORY DESIGN STUDIO")
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(center, paper_top - 67, "Kathmandu, Nepal  |  +977 9825776806")
    pdf.drawCentredString(center, paper_top - 79, "ivorydesign2083@gmail.com  |  ivoryarvena.vercel.app")

    pdf.setFillColor(blue)
    pdf.rect(paper_left + 1, paper_top - 122, paper_right - paper_left - 2, 28, fill=1, stroke=0)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(paper_left + 18, paper_top - 112, "CLIENT PAYMENT RECEIPT")
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(paper_right - 18, paper_top - 111, payment.invoice_number)

    details_top = paper_top - 154
    left_x, right_x = paper_left + 24, center + 24
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left_x, details_top, "CLIENT")
    pdf.drawString(right_x, details_top, "TRANSACTION DETAILS")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(left_x, details_top - 17, account.client_name)
    pdf.drawString(left_x, details_top - 32, account.client_location)
    pdf.drawString(left_x, details_top - 47, f"Project fixed on: {account.project_started_on:%d %B %Y}")
    pdf.drawString(right_x, details_top - 17, f"Invoice created: {payment.created_at:%d %B %Y}")
    pdf.drawString(right_x, details_top - 32, f"Amount received: {payment.paid_on:%d %B %Y}")
    pdf.drawString(right_x, details_top - 47, f"Invoice: {payment.invoice_number}")

    table_left, table_right = paper_left + 24, paper_right - 24
    y = details_top - 86
    row_height = 32
    label_width = 245
    rows = (
        ("Agreed project amount", account.agreed_amount, False),
        ("Previously received", paid_before, False),
        ("Received in this transaction", payment.amount, True),
        ("Remaining project balance", remaining, False),
    )
    for label, amount, highlighted in rows:
        pdf.setFillColor(blue if highlighted else pale if label.startswith("Remaining") else HexColor("#FFFFFF"))
        pdf.setStrokeColor(rule)
        pdf.rect(table_left, y, table_right - table_left, row_height, fill=1, stroke=1)
        pdf.line(table_left + label_width, y, table_left + label_width, y + row_height)
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold" if highlighted else "Helvetica", 8.5)
        pdf.drawString(table_left + 12, y + 11, label)
        pdf.drawRightString(table_right - 12, y + 11, _money(amount))
        y -= row_height

    if payment.note:
        note = payment.note.strip()
        max_width = table_right - table_left - 22
        while note and stringWidth(note, "Helvetica", 7.5) > max_width:
            note = note[:-1]
        if note != payment.note.strip():
            note = note.rstrip() + "…"
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(table_left, y - 18, f"Note: {note}")

    signature_width = 154
    signature_height = 72
    signature_left = table_right - signature_width
    signature_bottom = paper_bottom + 56
    pdf.setFillColor(pale)
    pdf.setStrokeColor(HexColor("#9AA29F"))
    pdf.roundRect(signature_left, signature_bottom, signature_width, signature_height, 3, fill=1, stroke=1)
    pdf.setStrokeColor(ink)
    pdf.line(signature_left + 18, signature_bottom + 37, table_right - 18, signature_bottom + 37)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(signature_left + signature_width / 2, signature_bottom + 23, account.client_name)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawCentredString(signature_left + signature_width / 2, signature_bottom + 11, "Client signature")

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(table_left, signature_bottom + 46, "Payment received from")
    pdf.drawString(table_left, signature_bottom + 31, account.client_name)
    pdf.drawString(table_left, signature_bottom + 16, f"Transaction date: {payment.paid_on:%d %B %Y}")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawCentredString(center, paper_bottom + 15, "Client payment record generated by Ivory Arvena Interior & Design")

    pdf.showPage()
    pdf.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{payment.invoice_filename}"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
