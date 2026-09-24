"""Conservative local triage; an unknown sender is not automatically spam."""

import re
from .models import CandidateProfile, Opportunity

SPAM_PATTERNS = (
    r"\bpay\s+(?:an?\s+)?upfront\s+fee\b",
    r"\b(?:send|transfer)\s+(?:us\s+)?(?:bitcoin|crypto|money)\b",
    r"\bguaranteed\s+income\b",
)


def rejection_reason(profile: CandidateProfile, opportunity: Opportunity) -> str | None:
    if any(re.search(pattern, opportunity.message, re.I) for pattern in SPAM_PATTERNS):
        return "Message matches a high-risk solicitation rule; review if unexpected."
    sender = opportunity.sender_email.strip().casefold()
    if sender.count("@") == 1:
        domain = sender.rsplit("@", 1)[1].rstrip(".")
        for excluded in profile.excluded_domains:
            excluded = excluded.strip().casefold().rstrip(".")
            if excluded and (domain == excluded or domain.endswith("." + excluded)):
                return "Sender domain matches your explicit exclusion list."
    return None
