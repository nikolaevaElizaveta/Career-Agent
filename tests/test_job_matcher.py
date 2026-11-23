"""Matcher logic lands in stage 4. Stage 1 only locks the default weights."""

from career_agent.domain.candidate import MatchWeights
from career_agent.domain.job import WorkAuthorizationVerdict


def test_default_match_weights_sum_to_one_hundred() -> None:
    assert MatchWeights().total() == 100


def test_unknown_authorization_stays_unknown() -> None:
    assert WorkAuthorizationVerdict.UNKNOWN.value == "unknown"
