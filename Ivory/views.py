import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from .models import Client, ContactMessage, Project, ProjectCategory, AboutCompany, TeamMember
from .models import PopupAd, Service
from .models import ActiveVisitor, SiteStatistics
from .emails import send_contact_confirmation

logger = logging.getLogger(__name__)


def website_metrics(request):
    """Record one visit per browser session and return near-real-time totals."""
    now = timezone.now()
    if not request.user.is_staff:
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


def staff_blob_upload_authorize(request):
    """Confirm a current staff session before a direct Blob upload."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"authorized": False}, status=403)
    return JsonResponse({"authorized": True})


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    return HttpResponse(
        f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /chatbox/\nSitemap: {sitemap_url}\n",
        content_type="text/plain",
    )


def sitemap_xml(request):
    paths = [
        reverse("home"), reverse("about"), reverse("projects"),
        reverse("services"), reverse("contact"),
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

        name = request.POST.get("name")
        email = request.POST.get("email")
        contact_number = request.POST.get("contact")
        message = request.POST.get("message")

        # Save contact message to database
        enquiry = ContactMessage.objects.create(
            name=name,
            email=email,
            contact=contact_number,
            message=message
        )

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

        # Success message
        messages.success(
            request,
            "Thank you for contacting Ivory Design Studio. "
            "Your message has been successfully submitted. "
            "We will get back to you soon."
        )

        # Redirect to homepage
        return redirect("home")

    return render(request, "homepage/contact.html")

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
