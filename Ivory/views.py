import hashlib
import logging
import re
from urllib.parse import urlencode
from decimal import Decimal, InvalidOperation
from io import BytesIO
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .models import Client, ContactMessage, Project, ProjectCategory, AboutCompany, TeamMember, RoomEstimate
from .models import PopupAd, Service
from .models import ActiveVisitor, SiteStatistics
from .emails import send_contact_confirmation
from .whatsapp import send_whatsapp_confirmation
from .security import rate_limited

logger = logging.getLogger(__name__)

GOOGLE_SITE_VERIFICATION_FILE = "google5995f313dfce11d4.html"


def google_site_verification(request):
    return HttpResponse(
        f"google-site-verification: {GOOGLE_SITE_VERIFICATION_FILE}",
        content_type="text/html; charset=utf-8",
    )


def website_metrics(request):
    """Record one visit per browser session and return near-real-time totals."""
    now = timezone.now()
    limited = rate_limited(request, "website-metrics", limit=60, window=60)
    if not request.user.is_staff and not limited:
        if not request.session.session_key:
            request.session.create()
        visitor_hash = hashlib.sha256(
            f"{settings.SECRET_KEY}:{request.session.session_key}".encode()
        ).hexdigest()
        with transaction.atomic():
            visitor, created = ActiveVisitor.objects.get_or_create(
                visitor_hash=visitor_hash,
                defaults={"last_seen": now},
            )
            if not created:
                ActiveVisitor.objects.filter(pk=visitor.pk).update(last_seen=now)
            statistics, _ = SiteStatistics.objects.select_for_update().get_or_create(pk=1)
            if created:
                statistics.total_visits += 1
                statistics.save(update_fields=["total_visits", "updated_at"])
    else:
        statistics, _ = SiteStatistics.objects.get_or_create(pk=1)

    online_since = now - timedelta(minutes=2)
    return JsonResponse({
        "total_visits": statistics.total_visits,
        "online_now": ActiveVisitor.objects.filter(last_seen__gte=online_since).count(),
    })


@never_cache
@require_GET
def staff_blob_upload_authorize(request):
    """Confirm a current staff session before a direct Blob upload."""
    allowed = request.user.is_authenticated and request.user.is_staff and (
        request.user.is_superuser or any((
        request.user.has_perm("Ivory.change_project"),
        request.user.has_perm("Ivory.change_projectimage"),
        request.user.has_perm("Ivory.change_teamportfolio"),
        ))
    )
    if not allowed:
        return JsonResponse({"authorized": False}, status=403)
    return JsonResponse({"authorized": True})


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    return HttpResponse(
        f"User-agent: *\nAllow: /\nDisallow: /my-lo/\nDisallow: /chatbox/\nSitemap: {sitemap_url}\n",
        content_type="text/plain",
    )


def sitemap_xml(request):
    paths = [
        reverse("home"), reverse("about"), reverse("projects"),
        reverse("services"), reverse("contact"), reverse("calculator"),
    ]
    paths.extend(
        reverse("team_portfolio", args=[pk])
        for pk in TeamMember.objects.filter(is_active=True).values_list("pk", flat=True)
    )
    paths.extend(
        reverse("project_detail", args=[pk])
        for pk in Project.objects.values_list("pk", flat=True)
    )
    urls = "".join(
        f"<url><loc>{request.build_absolute_uri(path)}</loc></url>" for path in paths
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(xml, content_type="application/xml")



def home(request):

    featured_projects = Project.objects.filter(
        featured=True
    ).order_by("-year")[:6]

    popups = PopupAd.objects.filter(
        is_active=True
    )

    clients = Client.objects.filter(is_active=True).order_by("order", "pk")

    return render(
        request,
        "homepage/home.html",
        {
            "featured_projects": featured_projects,
            "popups": popups,
            "clients": clients,
        }
    )

#contact page
def contact(request):

    if request.method == "POST":

        if rate_limited(request, "contact", limit=5, window=900):
            return HttpResponse("Too many submissions. Please wait 15 minutes and try again.", status=429)

        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        contact_number = request.POST.get("contact", "").strip()
        message = request.POST.get("message", "").strip()

        # Save contact message to database
        enquiry = ContactMessage(
            name=name,
            email=email,
            contact=contact_number,
            message=message
        )
        try:
            if not message or len(message) > 5000:
                raise ValidationError("Please enter a message no longer than 5,000 characters.")
            enquiry.full_clean()
        except ValidationError:
            messages.error(request, "Please check your contact details and keep the message under 5,000 characters.")
            return render(request, "homepage/contact.html", {"values": request.POST}, status=400)
        enquiry.save()

        # Email is an additional side effect: an outage must not undo a saved
        # enquiry or encourage the visitor to submit the same form again.
        try:
            if send_contact_confirmation(enquiry) != 1:
                logger.error("Contact confirmation was not sent for enquiry %s.", enquiry.pk)
        except Exception as exc:
            # Keep visitor details, SMTP responses and credentials out of logs.
            logger.error(
                "Contact confirmation failed for enquiry %s (%s).",
                enquiry.pk, type(exc).__name__,
            )

        # WhatsApp uses the same failure-safe behavior as email: the enquiry
        # remains saved even if Meta's API is temporarily unavailable.
        try:
            whatsapp_sent = send_whatsapp_confirmation(enquiry)
            if whatsapp_sent is False:
                logger.error("WhatsApp confirmation was not sent for enquiry %s.", enquiry.pk)
        except Exception as exc:
            logger.error(
                "WhatsApp confirmation failed for enquiry %s (%s).",
                enquiry.pk, type(exc).__name__,
            )

        # Success message
        messages.success(
            request,
            "Thank you for contacting Ivory Arvena Interior & Design. "
            "Your message has been successfully submitted. "
            "We will get back to you soon."
        )

        # Redirect to homepage
        return redirect("home")

    return render(request, "homepage/contact.html")


def calculator(request):
    errors = []
    values = request.POST if request.method == "POST" else {}
    if request.method == "POST":
        if rate_limited(request, "calculator", limit=10, window=900):
            return HttpResponse("Too many estimates. Please wait 15 minutes and try again.", status=429)
        name = request.POST.get("name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        try:
            room_count = int(request.POST.get("room_count", "0"))
        except ValueError:
            room_count = 0
        try:
            rate = Decimal(request.POST.get("rate", ""))
        except (InvalidOperation, TypeError):
            rate = Decimal("0")
        if not name or len(name) > 120:
            errors.append("Please enter your name.")
        if not phone_number:
            errors.append("Please enter your phone number.")
        elif not re.fullmatch(r"[+()\d][+()\d\s-]{6,19}", phone_number):
            errors.append("Please enter a valid phone number.")
        if room_count not in range(1, 8):
            errors.append("Choose between 1 and 7 rooms.")
        if not Decimal("90") <= rate <= Decimal("180"):
            errors.append("Expected rate must be between NPR 90 and NPR 180 per square foot.")
        rooms = []
        for index in range(1, room_count + 1):
            room_name = request.POST.get(f"room_{index}_name", "").strip()
            if not room_name:
                errors.append(f"Please enter a name for room {index}.")
            elif len(room_name) > 80:
                errors.append(f"Room {index} name must be 80 characters or fewer.")
            try:
                length = Decimal(request.POST.get(f"room_{index}_length", ""))
                width = Decimal(request.POST.get(f"room_{index}_width", ""))
                if length <= 0 or width <= 0 or length > 500 or width > 500:
                    raise InvalidOperation
                area = (length * width).quantize(Decimal("0.01"))
                rooms.append({"room": index, "name": room_name, "length": str(length), "width": str(width), "area": str(area)})
            except (InvalidOperation, TypeError):
                errors.append(f"Enter valid positive dimensions for room {index}.")
        if not errors:
            total_area = sum((Decimal(room["area"]) for room in rooms), Decimal("0"))
            estimate = RoomEstimate.objects.create(
                customer_name=name,
                phone_number=phone_number,
                room_count=room_count,
                rooms=rooms,
                rate_per_sq_ft=rate.quantize(Decimal("0.01")),
                total_area_sq_ft=total_area,
                total_amount=(total_area * rate).quantize(Decimal("0.01")),
            )
            return redirect(_signed_estimate_path("estimate_pdf", estimate))
    return render(request, "homepage/calculator.html", {"errors": errors, "values": values})


def _estimate_token(estimate):
    return signing.dumps(str(estimate.public_id), salt="ivory.invoice.access")


def _signed_estimate_path(view_name, estimate):
    path = reverse(view_name, args=[estimate.public_id])
    return f"{path}?{urlencode({'access': _estimate_token(estimate)})}"


def _can_access_estimate(request, estimate):
    if request.user.is_authenticated and request.user.is_staff:
        return True
    token = request.GET.get("access", "")
    try:
        value = signing.loads(
            token,
            salt="ivory.invoice.access",
            max_age=settings.IVORY_INVOICE_LINK_MAX_AGE,
        )
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    return value == str(estimate.public_id)


def _private_invoice_response(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Referrer-Policy"] = "no-referrer"
    return response


def estimate_result(request, public_id):
    estimate = get_object_or_404(RoomEstimate, public_id=public_id)
    if not _can_access_estimate(request, estimate):
        return HttpResponse("This private invoice link is invalid or has expired.", status=403)
    response = render(request, "homepage/estimate_result.html", {
        "estimate": estimate,
        "pdf_url": _signed_estimate_path("estimate_pdf", estimate),
    })
    return _private_invoice_response(response)


def estimate_pdf(request, public_id):
    estimate = get_object_or_404(RoomEstimate, public_id=public_id)
    if not _can_access_estimate(request, estimate):
        return HttpResponse("This private invoice link is invalid or has expired.", status=403)
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from svglib.svglib import svg2rlg
    from PIL import Image as PILImage

    buffer = BytesIO()
    # A compact portrait sheet keeps the invoice content proportioned like the
    # supplied reference instead of leaving most of an A4 page empty.
    page_width = 500
    page_height = 520 + (20 * estimate.room_count)
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    ink = HexColor("#101010")
    blue = HexColor("#D5E5F5")
    blue_dark = HexColor("#B8D1EA")
    rule = HexColor("#30363A")
    paper_left, paper_right = 28, page_width - 28
    paper_bottom, paper_top = 24, page_height - 24
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor("#777777"))
    pdf.setLineWidth(.7)
    pdf.rect(paper_left, paper_bottom, paper_right - paper_left, paper_top - paper_bottom, fill=0, stroke=1)

    center = page_width / 2
    pdf.setFillColor(ink)
    # These invoice-only assets live inside the Django application package so
    # Vercel includes them in the serverless function bundle. Public files in
    # static/ are served by the CDN and are intentionally excluded from that
    # bundle, so ReportLab cannot read them from disk in production.
    invoice_assets = settings.BASE_DIR / "Ivory" / "invoice_assets"
    logo_path = invoice_assets / "Ivoryarvena.svg"
    logo_drawing = svg2rlg(str(logo_path)) if logo_path.exists() else None

    def draw_logo(x, y, width, height, drawing=None):
        drawing = drawing or logo_drawing
        if not drawing:
            return
        # The supplied square SVG has broad margins; fit its actual artwork.
        artwork_left, artwork_bottom, artwork_right, artwork_top = drawing.getBounds()
        artwork_width = artwork_right - artwork_left
        artwork_height = artwork_top - artwork_bottom
        scale = min(width / artwork_width, height / artwork_height)
        pdf.saveState()
        clip = pdf.beginPath()
        clip.rect(x, y, width, height)
        pdf.clipPath(clip, stroke=0, fill=0)
        pdf.translate(
            x + (width - artwork_width * scale) / 2 - artwork_left * scale,
            y + (height - artwork_height * scale) / 2 - artwork_bottom * scale,
        )
        pdf.scale(scale, scale)
        renderPDF.draw(drawing, pdf, 0, 0)
        pdf.restoreState()

    # Compact centered masthead matching the supplied invoice reference.
    draw_logo(center - 40, paper_top - 34, 80, 30)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(center, paper_top - 49, "IVORY DESIGN STUDIO")
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(center, paper_top - 68, "Kathmandu, Nepal")
    pdf.drawCentredString(center, paper_top - 79, "+977 9825776806")
    pdf.drawCentredString(center, paper_top - 90, "ivorydesign2083@gmail.com")
    pdf.drawCentredString(center, paper_top - 101, "ivoryarvena.vercel.app")

    local_time = timezone.localtime(estimate.created_at)
    details_top = paper_top - 137
    left_x, right_x = paper_left + 34, center + 43
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left_x, details_top, "CUSTOMER")
    pdf.drawString(right_x, details_top, "INVOICE DETAILS")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(left_x, details_top - 15, estimate.customer_name)
    pdf.drawString(left_x, details_top - 28, "Kathmandu, Nepal")
    pdf.drawString(left_x, details_top - 41, estimate.phone_number)
    pdf.drawString(left_x, details_top - 54, f"{estimate.room_count} room{'s' if estimate.room_count != 1 else ''}")
    pdf.drawString(right_x, details_top - 15, f"Invoice: {estimate.invoice_number}")
    pdf.drawString(right_x, details_top - 28, f"Date: {local_time:%d %b %Y}")
    pdf.drawString(right_x, details_top - 41, f"Time: {local_time:%I:%M %p}")
    pdf.drawString(right_x, details_top - 54, "Due: Preliminary estimate")

    table_left, table_right = paper_left + 34, paper_right - 34
    y = details_top - 82
    columns = [table_left, table_left + 86, table_left + 140, table_left + 194, table_left + 261, table_left + 313]
    headers = ["Room name", "Length", "Width", "Area", "Rate", "Total"]
    row_height = 20
    pdf.setFillColor(blue)
    pdf.setStrokeColor(rule)
    pdf.setLineWidth(.65)
    pdf.rect(table_left, y, table_right - table_left, row_height, fill=1, stroke=1)
    for x in columns[1:]:
        pdf.line(x, y, x, y + row_height)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 7)
    column_ends = columns[1:] + [table_right]
    for x, x_end, header in zip(columns, column_ends, headers):
        pdf.drawCentredString((x + x_end) / 2, y + 6.5, header)
    y -= row_height
    pdf.setFont("Helvetica", 7)
    for room in estimate.rooms:
        amount = Decimal(room["area"]) * estimate.rate_per_sq_ft
        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.setStrokeColor(rule)
        pdf.rect(table_left, y, table_right - table_left, row_height, fill=1, stroke=1)
        for x in columns[1:]:
            pdf.line(x, y, x, y + row_height)
        pdf.setFillColor(ink)
        values = [room.get("name") or f"Room {room['room']}", room["length"], room["width"], room["area"], f"NPR {estimate.rate_per_sq_ft:,.2f}", f"NPR {amount:,.2f}"]
        for x, x_end, value in zip(columns, column_ends, values):
            pdf.drawCentredString((x + x_end) / 2, y + 6.5, value)
        y -= row_height

    totals_left = columns[4]
    subtotal = estimate.total_amount
    vat = (subtotal * Decimal("0.13")).quantize(Decimal("0.01"))
    discount = Decimal("0.00")
    final_price = subtotal + vat - discount
    for label, value, filled in (
        ("Area", f"{estimate.total_area_sq_ft:,.2f} sq ft", False),
        ("Sub Total", f"NPR {subtotal:,.2f}", False),
        ("VAT (13%)", f"NPR {vat:,.2f}", False),
        ("Discount", f"NPR {discount:,.2f}", False),
        ("FINAL PRICE", f"NPR {final_price:,.2f}", True),
    ):
        pdf.setFillColor(blue_dark if filled else HexColor("#FFFFFF"))
        # Keep every summary row connected to the table, matching the reference.
        pdf.rect(table_left, y, table_right - table_left, row_height, fill=1, stroke=1)
        pdf.line(totals_left, y, totals_left, y + row_height)
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica-Bold", 7.2)
        summary_divider = columns[5]
        pdf.line(summary_divider, y, summary_divider, y + row_height)
        pdf.drawCentredString((totals_left + summary_divider) / 2, y + 6.5, label)
        pdf.drawCentredString((summary_divider + table_right) / 2, y + 6.5, value)
        y -= row_height

    # Full-width blue terms strip and compact closing block mirror the reference.
    pdf.setFillColor(blue)
    pdf.setStrokeColor(rule)
    pdf.rect(table_left, y, table_right - table_left, 22, fill=1, stroke=1)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(center, y + 7, "Terms: Preliminary estimate only - final pricing follows approved plans.")
    y -= 22
    pdf.rect(table_left, y - 52, table_right - table_left, 52, fill=0, stroke=1)
    invoice_url = request.build_absolute_uri(_signed_estimate_path("estimate_pdf", estimate))
    qr_size = 44
    qr_inset = 3
    qr_x = table_left + 5
    qr_y = y - 48
    qr_code = QrCodeWidget(invoice_url)
    qr_bounds = qr_code.getBounds()
    qr_width = qr_bounds[2] - qr_bounds[0]
    qr_height = qr_bounds[3] - qr_bounds[1]
    qr_drawing_size = qr_size - (qr_inset * 2)
    qr_scale = min(qr_drawing_size / qr_width, qr_drawing_size / qr_height)
    qr_drawing = Drawing(
        qr_size,
        qr_size,
        transform=[qr_scale, 0, 0, qr_scale, qr_inset, qr_inset],
    )
    qr_drawing.add(qr_code)
    renderPDF.draw(qr_drawing, pdf, qr_x, qr_y)
    pdf.setFont("Helvetica", 7.5)
    note_x = qr_x + qr_size + 7
    pdf.drawString(note_x, y - 13, "Scan the QR code to open this invoice on any device.")
    pdf.drawString(note_x, y - 25, "This invoice is created according to your calculation.")
    pdf.drawString(note_x, y - 37, "Rates may differ according to the final approved plan.")

    signature_path = invoice_assets / "ivory-signature.png"
    stamp_path = invoice_assets / "stamp.png"
    signature_left = table_right - 128
    signature_right = table_right - 18
    if signature_path.exists():
        pdf.drawImage(ImageReader(str(signature_path)), signature_left + 10, y - 28, width=90, height=20, mask="auto", preserveAspectRatio=True)
    if stamp_path.exists():
        # Crop the transparent canvas so the supplied stamp remains clear at
        # invoice size instead of being reduced by its broad outer margins.
        with PILImage.open(stamp_path) as stamp_image:
            stamp_image = stamp_image.convert("RGBA")
            alpha_bounds = stamp_image.getchannel("A").getbbox()
            if alpha_bounds:
                stamp_image = stamp_image.crop(alpha_bounds)
            stamp_buffer = BytesIO()
            stamp_image.save(stamp_buffer, format="PNG")
            stamp_buffer.seek(0)
            pdf.drawImage(
                ImageReader(stamp_buffer),
                signature_left + 31,
                y - 29,
                width=48,
                height=28,
                mask="auto",
                preserveAspectRatio=True,
                anchor="c",
            )
    pdf.setStrokeColor(ink)
    pdf.setLineWidth(.55)
    pdf.line(signature_left, y - 31, signature_right, y - 31)
    signature_center = (signature_left + signature_right) / 2
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 5.5)
    pdf.drawCentredString(signature_center, y - 40, "Samyush Gautam")
    pdf.setFont("Helvetica", 5.2)
    pdf.drawCentredString(signature_center, y - 48, "CEO (Ivory Design)")
    pdf.setFont("Helvetica", 6)
    pdf.drawCentredString(center, paper_bottom + 10, "Thank you for choosing Ivory Arvena Interior & Design")
    pdf.showPage()
    pdf.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{estimate.invoice_number}.pdf"'
    return _private_invoice_response(response)

#projects page

def projects(request):
    all_projects = Project.objects.select_related("category").prefetch_related("gallery").order_by('-created_at')

    return render(request, 'homepage/projects.html', {
        'projects': all_projects,
        'project_categories': ProjectCategory.objects.filter(projects__isnull=False).distinct().order_by("name"),
    })


def project_detail(request, pk):
    project = get_object_or_404(
        Project.objects.select_related("category").prefetch_related("gallery"),
        pk=pk,
    )
    next_project = Project.objects.exclude(pk=project.pk).order_by("-created_at").first()
    return render(request, "homepage/project_detail.html", {
        "project": project,
        "next_project": next_project,
    })
#About us page
def about(request):

    company = AboutCompany.objects.first()

    team_members = TeamMember.objects.filter(
        is_active=True
    )

    context = {
        "company": company,
        "team_members": team_members,
    }

    return render(
        request,"homepage/about.html",context)


def services(request):
    return render(request, "homepage/services.html", {
        "services": Service.objects.filter(is_active=True),
    })


def team_portfolio(request, pk):
    member = get_object_or_404(TeamMember, pk=pk, is_active=True)
    return render(request, "homepage/team_portfolio.html", {
        "member": member,
        "portfolio": member.portfolio.filter(is_active=True),
    })
