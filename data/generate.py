"""Synthetic banking book, one row per business day, all figures USD millions.

Deposits by behavioral segment, loans by type, undrawn commitments by
facility type, wholesale funding, the liquid asset portfolio and equity.
Two stress episodes are planted (a market-wide wobble in late 2023 and an
idiosyncratic confidence event in spring 2025) and one business initiative
(an institutional cash program in Q2 2026 that brings in hot money and
lends it out). Everything is seeded. No real institution, no real clients.

The generator is the only place the "true" stress behavior lives. The
metrics, limits and models downstream never read these parameters; they
only see the balances, which is the same position a second line is in.
"""
import numpy as np
import pandas as pd

SEED = 7
START, END = "2023-01-02", "2026-08-31"

# segment: opening balance, annual drift, daily noise, 30 day outflow at full
# stress (the planted truth), deposit rate pass-through, insured flag
DEPOSIT_SEGMENTS = {
    "retail_stable":      dict(open=30000, drift=0.030, noise=0.0012, stress=0.035, passthrough=0.20, insured=True, recover=0.7),
    "retail_less_stable": dict(open=18000, drift=0.030, noise=0.0025, stress=0.120, passthrough=0.50, insured=True, recover=0.7),
    "small_business":     dict(open=8000,  drift=0.040, noise=0.0020, stress=0.060, passthrough=0.30, insured=True, recover=0.7),
    "corp_operational":   dict(open=20000, drift=0.050, noise=0.0035, stress=0.180, passthrough=0.60, insured=False, recover=0.6),
    "corp_nonop":         dict(open=9000,  drift=0.060, noise=0.0055, stress=0.550, passthrough=0.85, insured=False, recover=0.4),
    "fi_nonop":           dict(open=7000,  drift=0.080, noise=0.0080, stress=0.620, passthrough=0.95, insured=False, recover=0.3),
}

# facility type: opening undrawn, annual drift, 30 day draw at full stress,
# which loan book a draw lands in
COMMITMENTS = {
    "retail_lines":   dict(open=10000, drift=0.03, stress=0.020, book="loan_consumer"),
    "corp_credit":    dict(open=20000, drift=0.04, stress=0.100, book="loan_commercial"),
    "corp_liquidity": dict(open=6000,  drift=0.02, stress=0.350, book="loan_commercial"),
    "fi_facilities":  dict(open=4000,  drift=0.02, stress=0.300, book="loan_commercial"),
}

LOANS = {  # opening balance, annual drift, daily noise
    "loan_commercial": dict(open=40000, drift=0.030, noise=0.0010),
    "loan_mortgage":   dict(open=30000, drift=0.015, noise=0.0005),
    "loan_consumer":   dict(open=12000, drift=0.030, noise=0.0012),
}

OPENING = dict(reserves=9000, treasuries=20000, agency_mbs=9000, corp_bonds=2000,
               other_assets=8000, wholesale_short=6000, wholesale_long=18000,
               other_liabilities=3000, equity=11000)

# start, peak, ramp days, plateau days, decay half-life (business days)
EPISODES = {
    "market_wide_2023":    dict(start="2023-10-02", peak=0.35, ramp=6, plateau=8, half_life=10),
    "idiosyncratic_2025":  dict(start="2025-03-10", peak=1.00, ramp=6, plateau=14, half_life=8),
}
GROWTH_PROGRAM = dict(start="2026-04-01", end="2026-06-30",
                      fi_nonop=2500, corp_nonop=1500, loan_commercial=2000,
                      corp_credit=1000)
CONTINGENCY = dict(hqla_trigger=0.72, draw=6000, reserve_target=9000)   # secured term borrowing once HQLA is down 28% in a stress; repaid only from excess cash

DAILY_OUTFLOW_DIVISOR = 26       # 30 day window at full stress realizes about one "stress" unit
RATE_GAP_SENSITIVITY = 0.00001   # daily outflow per percentage point of rate gap
REPAY_DAYS = 120                 # stress draws repay over this many calm days
RECOVERY_DAYS = 126              # calm days over which part of an episode's deposit loss comes back

FED_FUNDS_PATH = [("2023-01-02", 4.33), ("2023-08-01", 5.33), ("2024-09-18", 5.33),
                  ("2025-01-01", 4.33), ("2025-12-31", 3.90), ("2026-08-31", 3.40)]


def business_days():
    return pd.bdate_range(START, END)


def stress_index(dates, rng):
    """Base wobble plus the planted episodes, clipped to [0, 1]."""
    n = len(dates)
    base = np.empty(n)
    base[0] = 0.06
    for t in range(1, n):
        base[t] = 0.06 + 0.85 * (base[t - 1] - 0.06) + rng.normal(0, 0.012)
    base = np.clip(base, 0.0, 0.25)
    shape = np.zeros(n)
    for ep in EPISODES.values():
        i0 = dates.get_indexer([pd.Timestamp(ep["start"])])[0]
        for k in range(n - i0):
            if k < ep["ramp"]:
                v = ep["peak"] * (k + 1) / ep["ramp"]
            elif k < ep["ramp"] + ep["plateau"]:
                v = ep["peak"]
            else:
                v = ep["peak"] * 0.5 ** ((k - ep["ramp"] - ep["plateau"]) / ep["half_life"])
            shape[i0 + k] += v
            if v < 0.005:
                break
    return np.clip(base + shape, 0.0, 1.0)


def fed_funds(dates):
    pts = pd.Series({pd.Timestamp(d): r for d, r in FED_FUNDS_PATH})
    return pts.reindex(dates.union(pts.index)).interpolate("time").reindex(dates).to_numpy()


def _spread(dates, start, end, total):
    """Daily increments that add up to `total` between start and end."""
    inc = np.zeros(len(dates))
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    inc[mask] = total / mask.sum()
    return inc


def generate(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = business_days()
    n = len(dates)
    s = stress_index(dates, rng)
    ff = fed_funds(dates)
    ep25 = pd.Timestamp(EPISODES["idiosyncratic_2025"]["start"])
    i_ep25 = dates.get_indexer([ep25])[0]

    dep = {k: np.empty(n) for k in DEPOSIT_SEGMENTS}
    und = {k: np.empty(n) for k in COMMITMENTS}
    loan = {k: np.empty(n) for k in LOANS}
    bal = {k: np.empty(n) for k in OPENING}
    for k, p in DEPOSIT_SEGMENTS.items():
        dep[k][0] = p["open"]
    for k, p in COMMITMENTS.items():
        und[k][0] = p["open"]
    for k, p in LOANS.items():
        loan[k][0] = p["open"]
    for k, v in OPENING.items():
        bal[k][0] = v

    program = {k: _spread(dates, GROWTH_PROGRAM["start"], GROWTH_PROGRAM["end"], v)
               for k, v in GROWTH_PROGRAM.items() if k not in ("start", "end")}
    stress_drawn = {k: 0.0 for k in COMMITMENTS}
    pre_episode = {k: None for k in DEPOSIT_SEGMENTS}
    loss = {k: 0.0 for k in DEPOSIT_SEGMENTS}
    recovered = {k: 0.0 for k in DEPOSIT_SEGMENTS}
    contingency_outstanding = 0.0
    contingency_date = None
    hqla_ref = None

    for t in range(1, n):
        st = s[t]
        stress_daily = st ** 1.5 / DAILY_OUTFLOW_DIVISOR
        # deposits
        for k, p in DEPOSIT_SEGMENTS.items():
            gap = (1 - p["passthrough"]) * ff[t]
            out = p["stress"] * stress_daily * (1 + 0.10 * rng.normal()) + RATE_GAP_SENSITIVITY * gap * (1 - p["insured"] * 0.5)
            growth = p["drift"] / 252 + p["noise"] * rng.normal()
            b = dep[k][t - 1] * (1 + growth - max(out, 0.0))
            b += program.get(k, np.zeros(n))[t]
            dep[k][t] = b
        # part of what left in an episode comes back once things calm down: customers
        # return, the business rebuilds. how much depends on the segment.
        for k, p in DEPOSIT_SEGMENTS.items():
            if st > 0.3:
                if pre_episode[k] is None:
                    pre_episode[k] = dep[k][t - 1]
                loss[k] = max(loss[k], pre_episode[k] - dep[k][t])
            elif st < 0.15 and loss[k] > 0:
                back = p["recover"] * loss[k] / RECOVERY_DAYS
                if recovered[k] < p["recover"] * loss[k]:
                    dep[k][t] += back
                    recovered[k] += back
                else:
                    loss[k], recovered[k], pre_episode[k] = 0.0, 0.0, None
        # loans and commitments
        for k, p in LOANS.items():
            loan[k][t] = loan[k][t - 1] * (1 + p["drift"] / 252 + p["noise"] * rng.normal())
        loan["loan_commercial"][t] += program["loan_commercial"][t]
        for k, p in COMMITMENTS.items():
            draw = und[k][t - 1] * p["stress"] * stress_daily * (1 + 0.10 * rng.normal())
            draw = max(draw, 0.0)
            u = und[k][t - 1] * (1 + p["drift"] / 252) - draw
            loan[p["book"]][t] += draw
            stress_drawn[k] += draw
            if st < 0.15 and stress_drawn[k] > 0:
                repay = min(stress_drawn[k], stress_drawn[k] / REPAY_DAYS + 1e-9)
                repay = min(repay, stress_drawn[k])
                u += repay
                loan[p["book"]][t] -= repay
                stress_drawn[k] -= repay
            u += program.get(k, np.zeros(n))[t]
            und[k][t] = u
        # funding and capital
        ws = bal["wholesale_short"][t - 1] * (1 + 0.0015 * rng.normal())
        if st > 0.5:
            ws -= 0.03 * st * ws          # unsecured lenders step back in a confidence event
        elif ws < OPENING["wholesale_short"]:
            ws += (OPENING["wholesale_short"] - ws) / 60
        bal["wholesale_short"][t] = ws
        bal["wholesale_long"][t] = bal["wholesale_long"][t - 1]
        bal["other_liabilities"][t] = bal["other_liabilities"][t - 1]
        bal["equity"][t] = bal["equity"][t - 1] * (1 + 0.08 / 252)
        bal["other_assets"][t] = bal["other_assets"][t - 1]
        bal["agency_mbs"][t] = bal["agency_mbs"][t - 1] * (1 - 0.06 / 252)   # paydowns
        bal["corp_bonds"][t] = bal["corp_bonds"][t - 1]
        bal["treasuries"][t] = bal["treasuries"][t - 1]
        # reserves are the plug that keeps assets = liabilities + equity
        liabilities = (sum(dep[k][t] for k in dep) + bal["wholesale_short"][t]
                       + bal["wholesale_long"][t] + bal["other_liabilities"][t] + bal["equity"][t])
        non_reserve_assets = (sum(loan[k][t] for k in loan) + bal["treasuries"][t]
                              + bal["agency_mbs"][t] + bal["corp_bonds"][t] + bal["other_assets"][t])
        reserves = liabilities - non_reserve_assets
        # treasury desk: sell bills when cash runs low, buy when it piles up
        if reserves < 3000:
            sale = min(bal["treasuries"][t], 6000 - reserves)
            bal["treasuries"][t] -= sale
            reserves += sale
        elif reserves > 14000:
            buy = reserves - 10000
            bal["treasuries"][t] += buy
            reserves -= buy
        # contingency funding plan: once a stress has burned through 28% of the liquid
        # asset pool, treasury takes secured term borrowing. it is repaid later, and
        # only out of cash the bank does not need.
        hq = reserves + bal["treasuries"][t] + 0.85 * bal["agency_mbs"][t] + 0.5 * bal["corp_bonds"][t]
        if st > 0.3 and hqla_ref is None:
            hqla_ref = hq
        if st < 0.15:
            hqla_ref = None
        if (hqla_ref is not None and st > 0.5 and contingency_outstanding == 0
                and hq < CONTINGENCY["hqla_trigger"] * hqla_ref):
            contingency_outstanding = CONTINGENCY["draw"]
            contingency_date = dates[t]
            bal["wholesale_long"][t] += CONTINGENCY["draw"]
            reserves += CONTINGENCY["draw"]
        elif contingency_outstanding > 0 and st < 0.15 and reserves > CONTINGENCY["reserve_target"]:
            repay = min(contingency_outstanding, reserves - CONTINGENCY["reserve_target"])
            bal["wholesale_long"][t] -= repay
            reserves -= repay
            contingency_outstanding -= repay
        bal["reserves"][t] = reserves

    out = pd.DataFrame(index=dates)
    for k in DEPOSIT_SEGMENTS:
        out["dep_" + k] = dep[k]
    for k in LOANS:
        out[k] = loan[k]
    for k in ("reserves", "treasuries", "agency_mbs", "corp_bonds", "other_assets"):
        out[k] = bal[k]
    for k in ("wholesale_short", "wholesale_long", "other_liabilities", "equity"):
        out[k] = bal[k]
    for k in COMMITMENTS:
        out["und_" + k] = und[k]
    for k, p in DEPOSIT_SEGMENTS.items():
        out["rate_" + k] = p["passthrough"] * ff       # what the bank pays each segment
    out["stress_index"] = s
    out["fed_funds"] = ff
    out.index.name = "date"
    out.attrs["contingency_date"] = contingency_date
    return out.round(3)


def events() -> pd.DataFrame:
    rows = []
    for name, ep in EPISODES.items():
        start = pd.Timestamp(ep["start"])
        end = start + pd.offsets.BDay(ep["ramp"] + ep["plateau"] + 3 * ep["half_life"])
        rows.append(dict(event=name, start=start, end=end, kind="stress episode"))
    rows.append(dict(event="institutional_cash_program", start=pd.Timestamp(GROWTH_PROGRAM["start"]),
                     end=pd.Timestamp(GROWTH_PROGRAM["end"]), kind="business initiative"))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    print(df.tail(3).T)
