import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from .models import Client, ContactMessage, Project, ProjectCategory, AboutCompany, TeamMember
from .models import PopupAd, Service
from .emails import send_contact_confirmation

logger = logging.getLogger(__name__)


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
