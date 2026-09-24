"""Pure node functions shared by the offline runner and optional LangGraph graph."""

from typing import TypedDict
import time
from .models import CandidateProfile, Evidence, Opportunity, Result, Verdict
from .providers.base import MatchProvider, ProviderUnavailable, SearchProvider
from .providers.disabled import DisabledMatcher, DisabledSearch
from .rules import rejection_reason


class PipelineState(TypedDict, total=False):
    profile: CandidateProfile
    opportunity: Opportunity
    result: Result
    evidence: Evidence
    attempts: int
    investigation: tuple[str, ...]


class Pipeline:
    def __init__(self, search: SearchProvider | None = None, matcher: MatchProvider | None = None, *, simulated=False):
        self.search = search or DisabledSearch()
        self.matcher = matcher or DisabledMatcher()
        self.simulated = simulated
        self.metrics = []

    def measured(self, node):
        def invoke(state):
            start = time.monotonic()
            try:
                update = node(state)
                result = update.get("result")
                self.metrics.append({"node": node.__name__, "seconds": round(time.monotonic() - start, 3),
                                     "outcome": result.verdict.value if result else "continue",
                                     "attempt": update.get("attempts", 0)})
                return update
            except Exception:
                self.metrics.append({"node": node.__name__, "seconds": round(time.monotonic() - start, 3), "outcome": "error"})
                raise
        return invoke

    def triage(self, state: PipelineState) -> dict:
        reason = rejection_reason(state["profile"], state["opportunity"])
        if reason:
            return {"result": Result(Verdict.SPAM, reason, simulated=self.simulated, assessment="suspicious")}
        if not state["opportunity"].company.strip():
            return {"result": Result(Verdict.ABSTAIN, "Company name is missing; request it from the recruiter.", simulated=self.simulated)}
        return {}

    def investigate(self, state: PipelineState) -> dict:
        attempt = state.get("attempts", 0) + 1
        try:
            evidence = self.search.investigate(state["opportunity"], attempt)
        except ProviderUnavailable as exc:
            return {"attempts": attempt, "result": Result(Verdict.ABSTAIN, str(exc), search_attempts=attempt, simulated=self.simulated, investigation=state.get("investigation", ()))}
        history = state.get("investigation", ()) + (f"Search {attempt}: {evidence.reason} Follow-up: {evidence.retry_reason}",)
        common = dict(sources=evidence.sources, search_attempts=attempt, simulated=self.simulated,
                      assessment=evidence.classification, investigation=history)
        if evidence.classification == "suspicious":
            return {"attempts": attempt, "result": Result(Verdict.SPAM, evidence.reason, **common)}
        if evidence.classification == "promotional":
            return {"attempts": attempt, "result": Result(Verdict.PROMOTIONAL, evidence.reason, **common)}
        if evidence.verified and evidence.sources and evidence.opportunity_supported:
            return {"attempts": attempt, "evidence": evidence, "investigation": history}
        if attempt >= 3 or not evidence.retry_worthwhile:
            stop = "Search budget exhausted. " if attempt >= 3 else "Further web search is unlikely to resolve the missing evidence. "
            return {"attempts": attempt, "result": Result(Verdict.ABSTAIN, stop + evidence.reason + " Verify the sender and role through an independently found official company contact before proceeding.", **common)}
        return {"attempts": attempt, "investigation": history}

    def match(self, state: PipelineState) -> dict:
        try:
            match = self.matcher.match(state["profile"], state["opportunity"], state["evidence"])
            result = Result(Verdict.HIGH_FIT if match.score >= 70 else Verdict.LOW_FIT, "Public evidence supports the opportunity; sender ownership is not authenticated. " + match.reason, match.score, state["evidence"].sources, state["attempts"], self.simulated, "supported", state.get("investigation", ()))
        except ProviderUnavailable as exc:
            result = Result(Verdict.ABSTAIN, str(exc), search_attempts=state["attempts"], simulated=self.simulated)
        return {"result": result}

    def run(self, profile: CandidateProfile, opportunity: Opportunity) -> Result:
        state: PipelineState = {"profile": profile, "opportunity": opportunity, "attempts": 0}
        state.update(self.triage(state))
        while "result" not in state and "evidence" not in state:
            state.update(self.investigate(state))
        if "result" not in state:
            state.update(self.match(state))
        return state["result"]

    def compile_graph(self):
        from langgraph.graph import END, START, StateGraph
        graph = StateGraph(PipelineState)
        graph.add_node("triage", self.measured(self.triage))
        graph.add_node("investigate", self.measured(self.investigate))
        graph.add_node("match", self.measured(self.match))
        graph.add_edge(START, "triage")
        graph.add_conditional_edges("triage", lambda s: END if "result" in s else "investigate")
        graph.add_conditional_edges("investigate", lambda s: END if "result" in s else "match" if "evidence" in s else "investigate")
        graph.add_edge("match", END)
        return graph.compile()
