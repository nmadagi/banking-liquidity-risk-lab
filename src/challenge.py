"""Independent challenge of proposed changes to internal stress assumptions.

The first line proposes; the second line tests the proposal against two
pieces of evidence, the worst 30 day outflow the segment has actually
produced and the model's stressed reading of its history, and against the
limits. The verdict rule is written down so the same proposal always gets
the same answer, and the memo is generated from the numbers.
"""
import copy
import math

import pandas as pd

from src import ml
from src.limits import status
from src.metrics import INTERNAL, internal_stress

BUFFER = 0.10   # the floor sits 10% above the strongest piece of evidence

PROPOSALS = [
    dict(id="P1", kind="deposit_runoff", name="corp_nonop", proposed=0.40,
         submitted_by="deposit product team",
         rationale="Align the internal runoff on corporate non-operational deposits to the "
                   "40% regulatory weight. These are relationship balances and the "
                   "internal 50% is punitive."),
    dict(id="P2", kind="deposit_runoff", name="retail_less_stable", proposed=0.12,
         submitted_by="consumer banking team",
         rationale="Less stable retail is insured money that rate-shops; realized outflow "
                   "in the 2025 event was about 11%. Lower the internal 13% to 12%."),
    dict(id="P3", kind="draw", name="corp_liquidity", proposed=0.30,
         submitted_by="corporate lending team",
         rationale="Liquidity facility draws peaked below 30% in 2025. The internal 35% "
                   "draw assumption over-reserves against the facility book."),
]


def floor_from(realized, model_reading) -> float:
    strongest = max(realized, model_reading)
    # round first: 0.10 * 1.1 * 100 is 11.000000000000002 in floating point
    return math.ceil(round(strongest * (1 + BUFFER) * 100, 6)) / 100


def verdict(proposed, current, realized, model_reading) -> tuple:
    """Returns (verdict, counter) with counter set only for a counter-proposal."""
    floor = floor_from(realized, model_reading)
    if proposed < realized:
        return "rejected", None
    if proposed >= floor:
        return "accepted", None
    if floor < current:
        return "counter-proposed", floor
    return "rejected", None


def _with(assumptions, kind, name, value):
    a = copy.deepcopy(assumptions)
    a[kind][name] = value
    return a


def evaluate(df, row, models, panels, assumptions=INTERNAL) -> list:
    """Run every proposal at the as-of balance sheet `row`."""
    out = []
    base = internal_stress(row, assumptions)
    for p in PROPOSALS:
        prefix = "dep_" if p["kind"] == "deposit_runoff" else "und_"
        current = assumptions[p["kind"]][p["name"]]
        realized, when = ml.realized_worst(df, prefix, p["name"])
        reading = ml.stressed_prediction(models[p["kind"]], panels[p["kind"]], p["name"])
        v, counter = verdict(p["proposed"], current, realized, reading)
        adopted = p["proposed"] if v == "accepted" else counter if v == "counter-proposed" else current
        proposed_run = internal_stress(row, _with(assumptions, p["kind"], p["name"], p["proposed"]))
        adopted_run = internal_stress(row, _with(assumptions, p["kind"], p["name"], adopted))
        out.append({**p, "current": current, "realized_worst": realized, "realized_when": when,
                    "model_reading": reading, "floor": floor_from(realized, reading),
                    "verdict": v, "adopted": adopted,
                    "survival_now": base["survival_days"],
                    "survival_if_proposed": proposed_run["survival_days"],
                    "survival_adopted": adopted_run["survival_days"],
                    "coverage_now": base["coverage_30d"],
                    "coverage_if_proposed": proposed_run["coverage_30d"],
                    "coverage_adopted": adopted_run["coverage_30d"],
                    "memo": None})
    for r in out:
        r["memo"] = memo(r)
    return out


def _pct(x):
    return f"{x * 100:.0f}%"


def memo(r) -> str:
    what = "30 day runoff" if r["kind"] == "deposit_runoff" else "30 day draw rate"
    lines = [
        f"Proposal {r['id']} from the {r['submitted_by']}: {what} on {r['name'].replace('_', ' ')} "
        f"from {_pct(r['current'])} to {_pct(r['proposed'])}.",
        f"Evidence: the worst 30 day figure this segment has produced is {_pct(r['realized_worst'])} "
        f"(window starting {r['realized_when'].date()}); the model's stressed reading of its history is "
        f"{_pct(r['model_reading'])}. With a 10% buffer the floor is {_pct(r['floor'])}.",
    ]
    if r["verdict"] == "rejected":
        why = ("The proposal sits below what the segment has already done once; an assumption "
               "that history has breached is not an assumption."
               if r["proposed"] < r["realized_worst"] else
               "The proposal sits below the evidence floor and the floor is no lower than "
               "the current assumption.")
        lines.append(f"Verdict: rejected. {why} The current {_pct(r['current'])} stands.")
    elif r["verdict"] == "counter-proposed":
        lines.append(f"Verdict: counter-proposed at {_pct(r['adopted'])}. The evidence supports "
                     f"easing from {_pct(r['current'])}, but not to {_pct(r['proposed'])}.")
    else:
        lines.append(f"Verdict: accepted at {_pct(r['proposed'])}. The evidence supports it. Condition: "
                     "re-test at the next quarterly review and on any 20% growth in the segment.")
    lines.append(f"Impact at the as-of date: survival horizon {r['survival_now']} days now, "
                 f"{r['survival_if_proposed']} if adopted as proposed, {r['survival_adopted']} "
                 f"under the verdict; 30 day coverage {r['coverage_now'] * 100:.0f}% now, "
                 f"{r['coverage_if_proposed'] * 100:.0f}% as proposed, "
                 f"{r['coverage_adopted'] * 100:.0f}% under the verdict. Survival horizon limit "
                 f"status under the verdict: {status(r['survival_adopted'], 'survival_days')}.")
    return " ".join(lines)


def summary_table(results) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({"id": r["id"], "assumption": f"{r['kind'].replace('_', ' ')}: {r['name'].replace('_', ' ')}",
                     "current": _pct(r["current"]), "proposed": _pct(r["proposed"]),
                     "realized worst": _pct(r["realized_worst"]), "model reading": _pct(r["model_reading"]),
                     "floor": _pct(r["floor"]), "verdict": r["verdict"], "adopted": _pct(r["adopted"]),
                     "survival now / proposed / verdict":
                         f"{r['survival_now']} / {r['survival_if_proposed']} / {r['survival_adopted']}"})
    return pd.DataFrame(rows)
