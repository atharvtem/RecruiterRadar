"""Transport-independent, immutable session data."""

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    SPAM = "SPAM"
    PROMOTIONAL = "PROMOTIONAL / SPONSORED"
    ABSTAIN = "ABSTAIN NEEDS HUMAN"
    HIGH_FIT = "HIGH FIT"
    LOW_FIT = "LOW FIT"


@dataclass(frozen=True)
class CandidateProfile:
    skills: tuple[str, ...]
    experience: str = ""
    excluded_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class Opportunity:
    message: str
    sender_email: str = ""
    company: str = ""

    def __post_init__(self):
        if not self.message.strip():
            raise ValueError("Enter a recruiter message.")
        if len(self.message) > 20_000:
            raise ValueError("Message must be at most 20,000 characters.")


@dataclass(frozen=True)
class Evidence:
    verified: bool
    reason: str
    sources: tuple[str, ...] = ()
    opportunity_supported: bool = False
    classification: str = "unverified"
    retry_worthwhile: bool = False
    retry_reason: str = "No useful follow-up search identified."


@dataclass(frozen=True)
class Match:
    score: int
    reason: str

    def __post_init__(self):
        if not 0 <= self.score <= 100:
            raise ValueError("Fit score must be between 0 and 100.")


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    reason: str
    score: int | None = None
    sources: tuple[str, ...] = ()
    search_attempts: int = 0
    simulated: bool = False
    assessment: str = "unverified"
    investigation: tuple[str, ...] = ()
