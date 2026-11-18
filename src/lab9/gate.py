"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _check_ratchet_entry(label: str, cur: dict[str, Any], cur_th: dict[str, Any],
                         base: dict[str, Any], base_th: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if base.get("blocking") and not cur.get("blocking"):
        problems.append(f"ratchet: {label} became non-blocking")
    for key in ("max", "max_increase"):
        if key in base_th and (key not in cur_th or cur_th[key] > base_th[key]):
            problems.append(f"ratchet: {label} loosened {key} ({base_th[key]} -> {cur_th.get(key)})")
    if "min" in base_th and ("min" not in cur_th or cur_th["min"] < base_th["min"]):
        problems.append(f"ratchet: {label} lowered min ({base_th['min']} -> {cur_th.get('min')})")
    if base_th.get("no_significant_drop") and not cur_th.get("no_significant_drop"):
        problems.append(f"ratchet: {label} dropped no_significant_drop")
    return problems


def _ratchet_problems(spec: dict[str, Any], base_spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    cur_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in cur_metrics:
            problems.append(f"ratchet: metric {mid} disappeared")
            continue
        cm = cur_metrics[mid]
        problems += _check_ratchet_entry(
            f"metric {mid}", cm, cm.get("threshold") or {}, bm, bm.get("threshold") or {},
        )
    cur_slices = {(s["name"], s["metric"]): s for s in (spec.get("slices") or [])}
    for bs in base_spec.get("slices") or []:
        key = (bs["name"], bs["metric"])
        if key not in cur_slices:
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} disappeared")
            continue
        cs = cur_slices[key]
        problems += _check_ratchet_entry(f"slice {bs['name']}/{bs['metric']}", cs, cs, bs, bs)
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted."""
    problems: list[str] = []
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is {v!r}")
    failures = pr.get("evaluator_failures") or []
    if failures:
        problems.append(f"{len(failures)} evaluator failure(s): {failures[0]}")

    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected_n = int(manifest.get("items") or 0) * len(manifest.get("seeds") or [])
    if len(rows) != expected_n:
        problems.append(f"row count {len(rows)} != manifest {manifest.get('items')} x {len(manifest.get('seeds') or [])}")

    pr_keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(pr_keys) != len(set(pr_keys)):
        problems.append("duplicate (item_id, seed) row(s) in PR report")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_keys) != base_keys:
        problems.append("(item_id, seed) set of PR differs from baseline")

    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    for r in rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            problems.append(f"slice tags changed for {key[0]}@{key[1]}: {r.get('slices')} != {base_slices[key]}")

    try:
        from lab9.graders import GRADERS
    except ImportError:
        GRADERS = {}
    meta_cols = {"item_id", "seed", "slices", "cost"}
    known_row_cols = {k for r in (*base_rows, *rows) for k in r if k not in meta_cols}
    row_metric_ids = [
        m["id"] for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or m.get("grader") in ("code", "lab8.metrics.trial_pass") or m["id"] in known_row_cols
    ]
    for r in rows:
        for mid in row_metric_ids:
            val = r.get(mid)
            if mid not in r or val is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} missing/None for {mid}")
            elif isinstance(val, (int, float)) and not isinstance(val, bool) and (math.isnan(val) or math.isinf(val)):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has {val!r} for {mid}")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += _ratchet_problems(spec, base_spec)
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): evaluate each slice threshold and paired CI."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                b = per_item(base, mid, slice_name=name)
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        sid = f"slice:{name}/{mid}"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
