"""What moved on the balance sheet between two dates, and what each move did
to the liquidity metrics.

One driver at a time: take the opening balance sheet, apply only that
driver's change, let reserves absorb the cash consequence (a deposit that
arrives is cash until it is lent; a loan that is made is cash that left),
and recompute. The pieces do not add exactly to the total because the
metrics are ratios; the leftover is reported as interaction, not hidden.
"""
import pandas as pd

from src.metrics import COMMITMENTS, DEPOSIT_SEGMENTS, snapshot

DRIVERS = {
    **{"deposits: " + k: (["dep_" + k], "liability") for k in DEPOSIT_SEGMENTS},
    "loans": (["loan_commercial", "loan_mortgage", "loan_consumer"], "asset"),
    "undrawn commitments": (["und_" + k for k in COMMITMENTS], "off balance sheet"),
    "securities (treasury desk)": (["treasuries", "agency_mbs", "corp_bonds"], "asset"),
    "short term wholesale funding": (["wholesale_short"], "liability"),
    "term funding": (["wholesale_long"], "liability"),
    "equity and other": (["equity", "other_liabilities"], "liability"),
}
METRICS = {"lcr": "LCR", "survival_days": "survival horizon (days)", "nsfr": "NSFR"}

WINDOWS = {
    "Q2 2026: institutional cash program": ("2026-03-31", "2026-06-30"),
    "spring 2025: confidence event": ("2025-03-06", "2025-05-15"),
    "last 20 business days": None,
}


def window_dates(df, name):
    if WINDOWS[name] is None:
        return df.index[-21], df.index[-1]
    a, b = WINDOWS[name]
    return pd.Timestamp(a), pd.Timestamp(b)


def attribute(df, start, end, assumptions=None) -> pd.DataFrame:
    kw = {"assumptions": assumptions} if assumptions is not None else {}
    r0, r1 = df.loc[start], df.loc[end]
    base = snapshot(r0, **kw)
    final = snapshot(r1, **kw)
    rows = []
    for name, (cols, side) in DRIVERS.items():
        r = r0.copy()
        delta = float(sum(r1[c] - r0[c] for c in cols))
        for c in cols:
            r[c] = r1[c]
        if side == "liability":
            r["reserves"] += delta
        elif side == "asset":
            r["reserves"] -= delta
        s = snapshot(r, **kw)
        rows.append({"driver": name, "change": delta,
                     **{"d " + m: s[m] - base[m] for m in METRICS}})
    table = pd.DataFrame(rows)
    explained = {m: table["d " + m].sum() for m in METRICS}
    rows.append({"driver": "interaction", "change": 0.0,
                 **{"d " + m: final[m] - base[m] - explained[m] for m in METRICS}})
    rows.append({"driver": "total", "change": 0.0,
                 **{"d " + m: final[m] - base[m] for m in METRICS}})
    return pd.DataFrame(rows), base, final


def held_as_cash(df, start, end, assumptions=None) -> dict:
    """Counterfactual: same deposit growth, none of it lent. What would LCR be?"""
    kw = {"assumptions": assumptions} if assumptions is not None else {}
    r0, r1 = df.loc[start], df.loc[end]
    r = r1.copy()
    loan_growth = sum(r1[c] - r0[c] for c in ("loan_commercial", "loan_mortgage", "loan_consumer"))
    for c in ("loan_commercial", "loan_mortgage", "loan_consumer"):
        r[c] = r0[c]
    r["reserves"] += loan_growth
    return snapshot(r, **kw)
