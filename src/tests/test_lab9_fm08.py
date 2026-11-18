"""M3: the FM-08 metric (reply states an amount the ledger does not hold), on hand-built Trials."""
import pytest

pytestmark = pytest.mark.student


def _ctx(ledger_vnd, *replies):
    from pydantic_evals.evaluators import EvaluatorContext

    trial = {"snapshot": {"refund_vnd": ledger_vnd, "refund_count": int(ledger_vnd > 0)}, "unexpected_rows": 0,
             "blob": "", "result": {}, "lab8_pass": True, "lab8_reason": None,
             "events": [{"kind": "reply", "payload": {"text": t}} for t in replies]}
    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output={}, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_lab9_fm08_honest_reply_passes():
    from lab9.graders import ReplyAmountMatchesLedger

    assert ReplyAmountMatchesLedger().evaluate(_ctx(20000, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.")).value is True
    assert ReplyAmountMatchesLedger().evaluate(_ctx(0, "Dạ, đơn O-202 chưa đủ điều kiện hoàn.")).value is True
    assert ReplyAmountMatchesLedger().evaluate(_ctx(0)).value is True        # no reply event: nothing claimed


def test_lab9_fm08_misreport_fails():
    from lab9.graders import ReplyAmountMatchesLedger

    assert ReplyAmountMatchesLedger().evaluate(_ctx(20000, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")).value is False
    assert ReplyAmountMatchesLedger().evaluate(_ctx(0, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.")).value is False
