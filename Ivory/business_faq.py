"""Grounded business FAQs. Public configuration and aggregate counts only."""

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import OperationalError, ProgrammingError

from .models import (
    BusinessInformation, BusinessSocialProfile, Client, TeamMember,
    DEFAULT_APPOINTMENT_INSTRUCTIONS, DEFAULT_PRICING_GUIDANCE,
)

logger = logging.getLogger(__name__)
CONTACT_CHANNELS = "Contact the team at +977 9825776806 or hello@ivorydesign.com, or use the Contact form below."
SQ_FT = r"(?:sq\.?\s*(?:ft|feet|foot)\.?|square[\s-]*(?:feet|foot)|ft[²2]|sft)\b"
AREA = re.compile(r"(?<![\w.,])(?P<number>[+−-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))\s*" + SQ_FT, re.I)
AREA_HELP = "For an estimate, enter one positive floor area in square feet, e.g. 1,000 sq ft. I cannot estimate ranges, dimensions, other units, or areas above 1,000,000 sq ft; please request a quote."
MAX_REPLY_LENGTH = 1800


def business_information():
    try:
        return BusinessInformation.objects.filter(pk=1).first() or BusinessInformation()
    except (OperationalError, ProgrammingError):
        # During migration rollout, do not turn an unavailable FAQ table into
        # an invented price or a public stack trace. No writes on chat requests.
        logger.warning("Chat business information unavailable; check database migrations.")
        return BusinessInformation()


def _safe_url(value):
    try:
        URLValidator(schemes=["https", "http"])(value)
    except ValidationError:
        return ""
    return value


def appointment_reply(info):
    instructions = info.appointment_instructions.strip() or DEFAULT_APPOINTMENT_INSTRUCTIONS
    url = _safe_url(info.appointment_url) if info.appointment_url else ""
    destination = f"Request an appointment: {url}" if url else "Request a consultation through the Contact form below (/contact/)."
    return f"{instructions} {destination} This chat does not book or confirm appointments; please wait for the team's confirmation."


def location_reply(info, nearby=False):
    location = f"Published studio location: {info.location.strip()}." if info.location.strip() else "A studio address has not been published in the chat information yet."
    landmark = f"Nearby landmark: {info.nearby_landmark.strip()}." if info.nearby_landmark.strip() else "A nearby landmark has not been published yet."
    if nearby:
        landmark += " I cannot determine your location or calculate the nearest studio/distance."
    return f"{location} {landmark} {CONTACT_CHANNELS} Please confirm directions and visiting hours with the team."


def parse_area(message):
    """Accept one explicit sq-ft value, never infer units or sum dimensions."""
    matches = list(AREA.finditer(message))
    ambiguous = re.search(r"\d\s*(?:x|×|\*|to|[-–/])\s*\d", message, re.I)
    other_units = re.search(r"\b(?:sq\.?\s*m|square\s*met(?:er|re)s?|m[²2]|sqm|ropani|aana)\b", message, re.I)
    if len(matches) != 1 or ambiguous or other_units:
        return None
    number = matches[0]["number"]
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", number):
        return None
    try:
        area = Decimal(number.replace(",", ""))
        if area.is_finite() and Decimal("0") < area <= Decimal("1000000"):
            return area
    except InvalidOperation:
        pass
    return None


def pricing_reply(info, message):
    guidance = info.pricing_guidance.strip() or DEFAULT_PRICING_GUIDANCE
    valid = info.pricing_mode == BusinessInformation.PricingMode.PER_SQ_FT
    if valid:
        try:
            # Also fails closed if a bulk import bypassed model/admin validation.
            info.full_clean(validate_unique=False, validate_constraints=False)
            valid = info.rate_per_sq_ft is not None and info.rate_per_sq_ft.is_finite() and info.rate_per_sq_ft > 0
        except (ValidationError, InvalidOperation, AttributeError, TypeError):
            valid = False
    if not valid:
        return f"{guidance} No confirmed per-square-foot rate is available for an automatic estimate. {appointment_reply(info)}"
    rate = info.rate_per_sq_ft
    rate_text = f"Published rate: {info.currency} {rate:,.2f} per sq ft of floor area. Scope: {info.pricing_scope.strip()}."
    area = parse_area(message)
    if area is None:
        estimate = AREA_HELP
    else:
        total = (area * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        area_text = f"{area:,.2f}".rstrip("0").rstrip(".")
        estimate = f"Indicative estimate for {area_text} sq ft: {area_text} × {info.currency} {rate:,.2f} = {info.currency} {total:,.2f}."
    return f"{rate_text} {estimate} {guidance} This is not a binding quote. No taxes or extra fees are added automatically; confirm the scope and final price with the team through the Contact form below."


def team_reply():
    roles = list(TeamMember.objects.filter(is_active=True).values_list("designation", flat=True))
    if not roles:
        return "No active team profiles are currently published, so I cannot confirm the number of architects or designers. " + CONTACT_CHANNELS
    architects = sum(bool(re.search(r"\barchitects?\b", role, re.I)) for role in roles)
    designers = sum(bool(re.search(r"\bdesigners?\b", role, re.I)) for role in roles)
    return (f"The website currently lists {len(roles)} active team profile(s): {architects} with an architect designation and {designers} with a designer designation. "
            "Roles can overlap. These are published profile counts, not a verified full staff headcount. Please contact the studio to confirm its current team.")


def clients_reply():
    count = Client.objects.filter(is_active=True).count()
    if not count:
        return "No active client profiles are currently published, so I cannot confirm how many clients the studio has worked with. " + CONTACT_CHANNELS
    return (f"The website currently lists {count} active client profile(s). This is the published client showcase, not a verified lifetime total of clients or completed projects. "
            "Contact the studio for its full experience and project history.")


def social_reply(info, normalized):
    platforms = {value: label for value, label in BusinessSocialProfile.Platform.choices}
    selected = [value for value in platforms if re.search(r"\b" + value + r"\b", normalized)]
    if "twitter" in normalized:
        selected.append("x")
    profiles = info.social_profiles.all() if not info._state.adding else []
    lines = []
    for profile in profiles:
        if selected and profile.platform not in selected:
            continue
        url = _safe_url(profile.url) if profile.url else ""
        details = " — ".join(value for value in (profile.handle.strip(), url) if value)
        if details and profile.platform in platforms:
            lines.append(f"{platforms[profile.platform]}: {details}")
    if not lines:
        return "A verified social profile for that request has not been published in the chat information yet. Please ask the team through the Contact form; I will not guess a handle or URL."
    result = "Published Ivory Design social profiles:\n"
    for line in lines:
        if len(result) + len(line) > MAX_REPLY_LENGTH - 120:
            return result + "\nFor additional profiles, please ask the studio through the Contact form."
        result += line + "\n"
    return result.rstrip()


def business_reply(message):
    normalized = " ".join(re.findall(r"[\w]+", message.lower()))
    pricing = re.search(r"\b(prices?|pricing|costs?|quotes?|quotation|budget|estimates?|rates?|charges?|charge)\b", normalized)
    per_area = re.search(r"\bper (square foot|square feet|sq ft|sqft|sft)\b", normalized) and not re.search(r"\b(light|lighting|daylight)\b", normalized)
    bare_area = re.fullmatch(r"\s*(?:(?:my area is|area|for)\s+)?[\d,.]+\s*" + SQ_FT + r"[?.!]?\s*", message, re.I)
    how_much_area = re.search(r"\bhow much\b.*\b(?:sqft|square feet|sq ft)\b", normalized) and not re.search(r"\b(light|lighting|daylight)\b", normalized)
    how_much_project = re.search(r"\bhow much (for|would|will|does|do|is|are|to|per)\b", normalized) and not re.search(r"\b(light|lighting|daylight)\b", normalized)
    if pricing or per_area or bare_area or how_much_area or how_much_project:
        return pricing_reply(business_information(), message)
    if re.search(r"\b(book|booking|appointments?|consultations?|start a project|schedule a visit|schedule a meeting|meet your team)\b", normalized):
        return appointment_reply(business_information())
    if re.search(r"\b(social|instagram|facebook|linkedin|tiktok|twitter|youtube|pinterest|handles?|follow you)\b", normalized):
        return social_reply(business_information(), normalized)
    if re.search(r"\b(team|staff|architects?|designers?)\b", normalized) and (re.search(r"\b(how many|number|count|size|total|people|your team|your architects|your designers)\b", normalized) or normalized in {"team", "architects", "designers"}):
        return team_reply()
    if re.search(r"\b(clients?|customers?|clientele)\b", normalized):
        return clients_reply()
    if re.search(r"\b(location|address|located|landmark|nearby|near me|nearest)\b", normalized) or re.search(r"\bwhere\b.*\b(you|ivory|studio|office)\b", normalized):
        return location_reply(business_information(), nearby=bool(re.search(r"\b(nearby|near me|nearest)\b", normalized)))
    if re.search(r"\b(contact|phone|email|hours|reach|call)\b", normalized):
        return location_reply(business_information())
    return None
