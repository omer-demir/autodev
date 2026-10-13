import re

import pytest

from app.evaluation_terms import missing_output_terms, output_term_pattern
from app.registry import RegistryError, _validate


def test_terms_ignore_case_and_separator_variants():
    output = "We keep Backward-Compatible fields and a circuit-breaker per dependency."

    assert missing_output_terms(
        ["backward compatible", "Circuit Breaker"], output) == []


def test_term_alternatives_accept_any_equivalent_phrase():
    terms = [["secret manager", "secret store"], "rotation", ["key vault"]]

    assert missing_output_terms(
        terms, "Use a managed secret store with rotation."
    ) == ["key vault"]


@pytest.mark.parametrize(("term", "output", "expected"), [
    (["distributed tracing", "trace propagation"], "W3C trace-propagation", True),
    ("expand-and-contract", "an expand and contract rollout", True),
    ("POST /orders", "keep post /orders stable", True),
    ("operational complexity", "operational burden", False),
])
def test_vally_pattern_matches_native_semantics(term, output, expected):
    pattern = output_term_pattern(term)
    flags = re.IGNORECASE if pattern.startswith("(?i)") else 0
    regex = re.compile(pattern.removeprefix("(?i)"), flags)

    assert bool(regex.search(output)) is expected
    assert (not missing_output_terms([term], output)) is expected


def test_suite_rejects_invalid_output_terms():
    suite = {
        "name": "Suite", "version": "1.0.0",
        "scenarios": [{"id": "one", "checks": {"required_output_terms": [[]]}}],
    }

    with pytest.raises(RegistryError, match="alternative phrases"):
        _validate("evaluation-suites", "suite", suite)
