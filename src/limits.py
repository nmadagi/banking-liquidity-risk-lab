"""The limit and indicator framework a second line runs the balance sheet
against, and the log of every breach in the history.

Each metric has a trigger (amber: talk about it) and a limit (red: escalate).
The regulatory minimum is not the limit; the internal limit sits above it so
the firm never meets the regulator at the floor.
"""
import pandas as pd

# metric: (label, trigger, limit, higher_is_better, format)
LIMITS = {
    "lcr":              ("LCR", 1.15, 1.10, True, "pct"),
    "nsfr":             ("NSFR", 1.08, 1.05, True, "pct"),
    "survival_days":    ("survival horizon, internal combined stress", 60, 45, True, "days"),
    "uninsured_share":  ("uninsured deposits / total deposits", 0.40, 0.45, False, "pct"),
    "fi_share":         ("financial institution deposits / total deposits", 0.06, 0.09, False, "pct"),
    "loan_to_deposit":  ("loans / deposits", 1.00, 1.10, False, "pct"),
    "undrawn_to_hqla":  ("undrawn commitments / HQLA", 1.50, 1.75, False, "pct"),
    "wholesale_to_hqla": ("30 day wholesale maturities / HQLA", 0.25, 0.30, False, "pct"),
}
REGULATORY_MINIMUM = {"lcr": 1.00, "nsfr": 1.00}


def status(value, key) -> str:
    _, trigger, limit, higher, _ = LIMITS[key]
    if higher:
        return "red" if value < limit else "amber" if value < trigger else "green"
    return "red" if value > limit else "amber" if value > trigger else "green"


def fmt(value, kind) -> str:
    return f"{value:.0f}" if kind == "days" else f"{value * 100:.1f}%"


def table(snap: dict) -> pd.DataFrame:
    rows = []
    for key, (label, trigger, limit, higher, kind) in LIMITS.items():
        rows.append({"indicator": label, "value": fmt(snap[key], kind),
                     "trigger": fmt(trigger, kind), "limit": fmt(limit, kind),
                     "direction": "floor" if higher else "cap",
                     "status": status(snap[key], key),
                     "regulatory minimum": fmt(REGULATORY_MINIMUM[key], kind) if key in REGULATORY_MINIMUM else ""})
    return pd.DataFrame(rows)


def breach_log(hist: pd.DataFrame) -> pd.DataFrame:
    """Contiguous runs of red status per indicator."""
    rows = []
    for key, (label, trigger, limit, higher, kind) in LIMITS.items():
        red = hist[key].apply(lambda v: status(v, key) == "red")
        start = None
        for date, is_red in red.items():
            if is_red and start is None:
                start = date
            elif not is_red and start is not None:
                seg = hist.loc[start:date, key].iloc[:-1]
                rows.append(_run(label, start, seg.index[-1], seg, higher, kind))
                start = None
        if start is not None:
            seg = hist.loc[start:, key]
            rows.append(_run(label, start, seg.index[-1], seg, higher, kind, open_run=True))
    if not rows:
        return pd.DataFrame(columns=["indicator", "from", "to", "business days", "worst", "status"])
    return pd.DataFrame(rows).sort_values("from").reset_index(drop=True)


def _run(label, start, end, seg, higher, kind, open_run=False):
    worst = seg.min() if higher else seg.max()
    return {"indicator": label, "from": start.date(), "to": end.date(),
            "business days": len(seg), "worst": fmt(worst, kind),
            "status": "still in breach" if open_run else "resolved"}


def counts(snap: dict) -> dict:
    s = [status(snap[k], k) for k in LIMITS]
    return {"red": s.count("red"), "amber": s.count("amber"), "green": s.count("green"),
            "red_names": [LIMITS[k][0] for k in LIMITS if status(snap[k], k) == "red"]}
