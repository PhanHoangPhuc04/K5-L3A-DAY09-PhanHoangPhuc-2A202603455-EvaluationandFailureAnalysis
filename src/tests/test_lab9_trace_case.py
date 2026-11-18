"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step = event 3 `model_override {"delay_days": 5}`: the agent replaces the DB fact
(O-202 delay_days = 2) with the number in the ticket, so a no-entitlement claim gets refunded.
The same claim@seed on `fixed` keeps the DB fact and is denied.
"""
import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return {shape: investigate(shape, "C-002", 11) for shape in ("seeded_regression", "fixed")}


def test_lab9_trace_case_c002_first_wrong_step_is_override(cases):
    events = cases["seeded_regression"]["trial"]["events"]
    first_override = next(i for i, e in enumerate(events, 1) if e["kind"] == "model_override")
    assert first_override == 3 and events[2]["payload"] == {"delay_days": 5}
    assert all(e["kind"] != "model_override" for e in cases["fixed"]["trial"]["events"])


def test_lab9_trace_case_c002_graders_catch_regression_not_fix(cases):
    from lab9.graders import DbFactKept, RefundAmountCorrect

    bad, good = cases["seeded_regression"], cases["fixed"]
    assert DbFactKept().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert RefundAmountCorrect().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert DbFactKept().evaluate(_ctx(good["trial"], good["label"])).value is True
    assert RefundAmountCorrect().evaluate(_ctx(good["trial"], good["label"])).value is True
