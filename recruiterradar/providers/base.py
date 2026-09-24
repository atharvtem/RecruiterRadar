from typing import Protocol
from ..models import CandidateProfile, Evidence, Match, Opportunity


class ProviderUnavailable(RuntimeError):
    pass


class SearchProvider(Protocol):
    def investigate(self, opportunity: Opportunity, attempt: int) -> Evidence: ...


class MatchProvider(Protocol):
    def match(self, profile: CandidateProfile, opportunity: Opportunity, evidence: Evidence) -> Match: ...
