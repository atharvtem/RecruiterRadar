"""Hard stop: live provider execution is deliberately not implemented."""

from .base import ProviderUnavailable


class DisabledSearch:
    def investigate(self, opportunity, attempt):
        raise ProviderUnavailable("Live search is disabled. Company verification needs human review.")


class DisabledMatcher:
    def match(self, profile, opportunity, evidence):
        raise ProviderUnavailable("Live matching is disabled.")
