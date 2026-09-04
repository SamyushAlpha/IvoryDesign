import re
from difflib import SequenceMatcher
from .models import CustomFAQ


def normalize(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def custom_faq_reply(message):
    query = normalize(message)
    best = (0, None)
    for faq in CustomFAQ.objects.filter(is_active=True):
        for alternative in [faq.question, *faq.aliases.splitlines()]:
            candidate = normalize(alternative)
            if not candidate:
                continue
            if candidate == query:
                return faq.answer
            left, right = set(query.split()), set(candidate.split())
            if min(len(left), len(right)) < 3:
                continue
            overlap = len(left & right) / max(len(left), len(right))
            similarity = SequenceMatcher(None, query, candidate).ratio()
            score = max(overlap, similarity if overlap >= .5 else 0)
            if score >= .82 and score > best[0]:
                best = (score, faq.answer)
    return best[1]
