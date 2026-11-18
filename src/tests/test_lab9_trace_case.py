"""Regression tests for M3 trace case (C-002@11), FM-08, FM-05, and M7 integrity traps."""
from __future__ import annotations

import copy

import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(
        name="t",
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_trace_case_c002_seed11_regression_and_fixed():
    """C-002@11: seeded_regression emits model_override and over-refunds; fixed stays clean."""
    from lab9 import graders, trace_case

    bad = trace_case.investigate("seeded_regression", "C-002", 11)
    good = trace_case.investigate("fixed", "C-002", 11)

    assert bad["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert graders.RefundAmountCorrect().evaluate(_ctx(bad["trial"], bad["label"])).value is False

    assert good["trial"]["lab8_pass"] is True
    assert graders.DbFactKept().evaluate(_ctx(good["trial"], good["label"])).value is True
    assert graders.RefundAmountCorrect().evaluate(_ctx(good["trial"], good["label"])).value is True


def test_fm08_reply_amount_matches_ledger():
    from lab9 import graders

    label = {"refund_vnd": 20000, "approval_ok": True, "forbid_substrings": []}
    bad_trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}}],
        "result": {},
        "lab8_pass": True,
        "lab8_reason": "ok",
    }
    good_trial = copy.deepcopy(bad_trial)
    good_trial["events"][0]["payload"]["text"] = "LogiX đã hoàn phí 20.000đ cho đơn O-808 của anh/chị ạ."

    assert graders.ReplyAmountMatchesLedger().evaluate(_ctx(bad_trial, label)).value is False
    assert graders.ReplyAmountMatchesLedger().evaluate(_ctx(good_trial, label)).value is True


def test_fm05_proposal_matches_quote():
    from lab9 import graders

    label = {"refund_vnd": 0, "approval_ok": True, "forbid_substrings": []}
    bad_trial = {
        "snapshot": {"refund_vnd": 0, "refund_count": 0},
        "unexpected_rows": 0,
        "blob": "",
        "events": [
            {"kind": "quote", "payload": {"amount_vnd": 35000}},
            {"kind": "proposal", "payload": {"amount_vnd": 0}},
        ],
        "result": {"proposal_amount": 0},
        "lab8_pass": False,
        "lab8_reason": "proposal_mismatch",
    }
    good_trial = {
        "snapshot": {"refund_vnd": 0, "refund_count": 0},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "quote", "payload": {"amount_vnd": 35000}}],
        "result": {"proposal_amount": 35000},
        "lab8_pass": True,
        "lab8_reason": "ok",
    }
    assert graders.ProposalMatchesQuote().evaluate(_ctx(bad_trial, label)).value is False
    assert graders.ProposalMatchesQuote().evaluate(_ctx(good_trial, label)).value is True


def test_integrity_catches_duplicate_rows_evaluator_failures_and_slice_relabel():
    from lab9 import gate

    rows = [
        {"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["money_movement"] if i == 0 else []}
        for i in range(4)
        for s in (1, 2)
    ]
    spec = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8}}]}
    base = {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": rows, "metrics": {"pass_rate": 1.0}, "evaluator_failures": []}

    assert gate.integrity_check(base, base, spec) == []

    dup = copy.deepcopy(base)
    dup["rows"][-1] = copy.deepcopy(dup["rows"][0])
    assert gate.integrity_check(dup, base, spec)

    ev_fail = copy.deepcopy(base)
    ev_fail["evaluator_failures"] = ["E-000@1:TrialPass:boom"]
    assert gate.integrity_check(ev_fail, base, spec)

    relabelled = copy.deepcopy(base)
    relabelled["rows"][0]["slices"] = []
    assert gate.integrity_check(relabelled, base, spec)
