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

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. Aggregates that are not finite numbers (NaN < min is False: a naive gate lets it pass).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}: not a finite number")

    # 2. Row count and (item, seed) coverage: nothing dropped, duplicated or cherry-picked.
    n_seeds = len(man.get("seeds") or [])
    want_n = int(man.get("items") or 0) * n_seeds
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {n_seeds} seeds = {want_n}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = len(keys) - len(set(keys))
    if dup:
        problems.append(f"{dup} duplicated (item, seed) row(s)")
    if man.get("items") != base_man.get("items") or list(man.get("seeds") or []) != list(base_man.get("seeds") or []):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from the baseline's "
                        f"{base_man.get('items')}/{base_man.get('seeds')}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        miss, extra = len(base_keys - set(keys)), len(set(keys) - base_keys)
        problems.append(f"(item, seed) set differs from the baseline's: {miss} missing, {extra} extra")

    # 3. Crashed graders: listed failures, or a graded value that is None / not a pass-fail bool.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    for m in graded:
        if not any(m in r for r in base_rows) and not any(m in r for r in rows):
            continue                                    # metric not graded on either side
        bad = [r for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            problems.append(f"{len(bad)} row(s) with no pass/fail value for graded metric {m} "
                            f"(first {bad[0].get('item_id')}@{bad[0].get('seed')}: {bad[0].get(m)!r})")

    # 4. Reported aggregates must equal what the rows give (a polished number is not a result).
    if rows and not problems:
        try:
            recomputed = aggregate(rows, [m for m in graded if m in rows[0]], k_values=spec.get("pass_k", []))
        except (KeyError, TypeError, ValueError):
            recomputed = {}
        reported = pr.get("metrics") or {}
        for k, v in recomputed.items():
            if k not in reported:
                continue
            got = reported[k]
            if isinstance(v, (int, float)) and (not isinstance(got, (int, float)) or abs(got - v) > 1e-3):
                problems.append(f"metric {k} reported {got!r}, rows give {v}")
            elif v is None and got is not None:
                problems.append(f"metric {k} reported {got!r}, rows give None")

    # 5. Slice tags must match the baseline's for every item (relabelling hides a slice regression).
    def tags(rs: list[dict]) -> dict:              # every row of an item, not just the last one
        out: dict = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return {k: sorted(v) for k, v in out.items()}
    pt, bt = tags(rows), tags(base_rows)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags differ from the baseline's on {len(moved)} item(s), first {moved[0]}: "
                        f"{pt[moved[0]]} vs {bt[moved[0]]}")

    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None:
        problems += ratchet_check(spec, base_spec)
    return problems


def _looser(new: dict, old: dict) -> list[str]:
    """What in threshold-like dict `new` is looser than in `old` (empty = same or stricter)."""
    out = []
    for key in ("max", "max_increase"):
        if key in old and (key not in new or new[key] > old[key]):
            out.append(f"{key} {old[key]} -> {new.get(key, 'removed')}")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"min {old['min']} -> {new.get('min', 'removed')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def ratchet_check(spec: dict, base_spec: dict) -> list[str]:
    """Spec vs the spec on main. A different eval-set version means a new baseline: thresholds restart."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for old in base_spec.get("metrics", []):
        mid, new = old["id"], new_m.get(old["id"])
        if new is None:
            problems.append(f"RATCHET metric {mid} removed")
            continue
        if old.get("blocking") and not new.get("blocking"):
            problems.append(f"RATCHET metric {mid} no longer blocking")
        problems += [f"RATCHET metric {mid}: {x}"
                     for x in _looser(new.get("threshold") or {}, old.get("threshold") or {})]
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        name = f"{old['name']}/{old['metric']}"
        new = new_s.get((old["name"], old["metric"]))
        if new is None:
            problems.append(f"RATCHET slice {name} removed")
            continue
        if old.get("blocking") and not new.get("blocking"):
            problems.append(f"RATCHET slice {name} no longer blocking")
        problems += [f"RATCHET slice {name}: {x}" for x in _looser(new, old)]
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                         # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
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
