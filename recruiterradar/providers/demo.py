"""Synthetic fixtures only; these are not company verification or LLM matching."""

import re
from ..models import Evidence, Match


class DemoSearch:
    def investigate(self, opportunity, attempt):
        if opportunity.company.strip().casefold() == "example robotics":
            return Evidence(True, "Synthetic demo company fixture.", ("https://example.com",), opportunity_supported=True, classification="supported")
        return Evidence(False, "No synthetic fixture for this company.")


class DemoMatcher:
    def match(self, profile, opportunity, evidence):
        skills = {skill.strip().casefold() for skill in profile.skills if skill.strip()}
        if not skills:
            return Match(0, "No skills provided in the demo profile.")
        hits = sum(bool(re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", opportunity.message, re.I)) for skill in skills)
        return Match(round(100 * hits / len(skills)), "Demo keyword overlap only; not an objective assessment of job fit.")
