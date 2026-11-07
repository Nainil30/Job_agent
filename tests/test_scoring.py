"""Heuristic scorer + evaluator (LLM path uses a fake client — no network)."""

import pytest

from src.engine.evaluator import Evaluator
from src.engine.llm import parse_json
from src.engine.scorer import HeuristicScorer
from tests.conftest import make_job


class FakeLLM:
    label = "fake:model"

    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, 0

    async def complete_json(self, system, prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.payload


def test_heuristic_ranks_target_role_above_adjacent(persona):
    scorer = HeuristicScorer(persona["scoring"])
    npi, _ = scorer.score(
        make_job(title="NPI Program Manager", description="Own EVT/DVT/PVT builds and clear-to-build with CM partners.")
    )
    tpm, _ = scorer.score(make_job(title="Technical Program Manager - LLM Safety", location="Seattle, WA"))
    assert npi > tpm
    assert 0 <= tpm <= npi <= 100


def test_heuristic_penalises_seniority(persona):
    scorer = HeuristicScorer(persona["scoring"])
    junior, _ = scorer.score(make_job(description="5 years experience"))
    senior, reasons = scorer.score(make_job(description="Requires 12+ years of experience"))
    assert senior < junior
    assert any(r.startswith("penalty") for r in reasons)


def test_tiers(persona):
    ev = Evaluator(persona)
    assert ev.tier_for(95)[0] == "Tier 1: Apply Now"
    assert ev.tier_for(75)[0] == "Tier 2: Review"
    assert ev.tier_for(10) == ("Skip", "SKIP")


async def test_llm_verdict_used_and_tier_derived_in_code(persona):
    llm = FakeLLM(
        {
            "fit_score": 91,
            "summary": "Great fit",
            "strengths": ["a"],
            "gaps": ["b"],
            "resume_bullets": ["c"],
            "years_required": 5,
        }
    )
    ev = await Evaluator(persona, llm=llm).evaluate(make_job(description="NPI EVT DVT supply chain"))
    assert ev.fit_score == 91 and ev.tier == "Tier 1: Apply Now" and ev.evaluator == "fake:model"
    assert ev.heuristic_score > 0 and ev.tailored_resume_bullets == ["c"]


async def test_years_guard_caps_score(persona):
    llm = FakeLLM(
        {"fit_score": 95, "summary": "", "strengths": [], "gaps": [], "resume_bullets": [], "years_required": 15}
    )
    ev = await Evaluator(persona, llm=llm).evaluate(make_job(description="NPI supply chain"))
    assert ev.fit_score < 70


async def test_llm_failure_falls_back_to_heuristic(persona):
    llm = FakeLLM(error=RuntimeError("429 quota"))
    evaluator = Evaluator(persona, llm=llm)
    ev = await evaluator.evaluate(make_job(description="NPI supply chain"))
    assert ev.evaluator == "heuristic" and evaluator.llm_failures == 1


async def test_llm_budget_and_threshold(persona):
    llm = FakeLLM({"fit_score": 80, "summary": "", "strengths": [], "gaps": [], "resume_bullets": []})
    evaluator = Evaluator(persona, llm=llm, max_llm_calls=1)
    await evaluator.evaluate(make_job(description="NPI"))
    await evaluator.evaluate(make_job(job_id="2", description="NPI"))
    await evaluator.evaluate(make_job(job_id="3", title="Space Suit Sewer"))  # below min heuristic
    assert llm.calls == 1


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Here you go: {"a": 1} thanks'])
def test_parse_json_tolerates_wrappers(text):
    assert parse_json(text) == {"a": 1}
