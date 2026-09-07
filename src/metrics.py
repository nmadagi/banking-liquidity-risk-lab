"""Liquidity metrics on one balance sheet snapshot: LCR, NSFR and the
internal 90 day stress projection with its survival horizon.

Regulatory weights follow the US LCR and NSFR rules (12 CFR 249) as
written up in docs/assumptions.md. Internal assumptions are deliberately
harsher and shaped in time; the regulatory ratio is a 30 day snapshot,
the internal test is a day by day cash flow.
"""
import numpy as np
import pandas as pd

DEPOSIT_SEGMENTS = ["retail_stable", "retail_less_stable", "small_business",
                    "corp_operational", "corp_nonop", "fi_nonop"]
COMMITMENTS = ["retail_lines", "corp_credit", "corp_liquidity", "fi_facilities"]
INSURED = {"retail_stable": True, "retail_less_stable": True, "small_business": True,
           "corp_operational": False, "corp_nonop": False, "fi_nonop": False}

# 30 day outflow rates, regulatory (LCR rule) and internal (firm's own scenario)
REG_DEPOSIT_RUNOFF = dict(retail_stable=0.03, retail_less_stable=0.10, small_business=0.05,
                          corp_operational=0.25, corp_nonop=0.40, fi_nonop=1.00)
REG_DRAW = dict(retail_lines=0.05, corp_credit=0.10, corp_liquidity=0.30, fi_facilities=0.40)
REG_HAIRCUT = dict(reserves=0.0, treasuries=0.0, agency_mbs=0.15, corp_bonds=0.50)
REG_INFLOW_RATE = 0.50      # share of contractual loan inflows that counts
REG_INFLOW_CAP = 0.75       # inflows may offset at most 75% of outflows
LOAN_DUE_30D = dict(loan_commercial=0.040, loan_mortgage=0.010, loan_consumer=0.050)

INTERNAL = dict(
    deposit_runoff=dict(retail_stable=0.04, retail_less_stable=0.13, small_business=0.08,
                        corp_operational=0.22, corp_nonop=0.50, fi_nonop=1.00),
    draw=dict(retail_lines=0.06, corp_credit=0.10, corp_liquidity=0.35, fi_facilities=0.45),
    haircut=dict(reserves=0.0, treasuries=0.0, agency_mbs=0.20, corp_bonds=0.60),
    inflow_rate=0.50,           # half of contractual loan inflows are relied on
    wholesale_rollover=0.0,     # no unsecured wholesale rolls
    tail_runoff=0.40,           # extra runoff after day 30, as a share of the 30 day amount, spread to day 90
    front_load_tau=8.0,         # days; about 70% of the 30 day runoff lands in the first ten days
    horizon=90,
)

NSFR_ASF = dict(equity=1.0, wholesale_long=1.0, wholesale_short=0.0, other_liabilities=0.0,
                retail_stable=0.95, retail_less_stable=0.90, small_business=0.95,
                corp_operational=0.50, corp_nonop=0.50, fi_nonop=0.0)
NSFR_RSF = dict(reserves=0.0, treasuries=0.05, agency_mbs=0.15, corp_bonds=0.50,
                loan_commercial=0.85, loan_mortgage=0.65, loan_consumer=0.85,
                other_assets=1.0, undrawn=0.05)


def hqla(row, haircut=REG_HAIRCUT, apply_caps=True) -> dict:
    l1 = row["reserves"] * (1 - haircut["reserves"]) + row["treasuries"] * (1 - haircut["treasuries"])
    l2a = row["agency_mbs"] * (1 - haircut["agency_mbs"])
    l2b = row["corp_bonds"] * (1 - haircut["corp_bonds"])
    if apply_caps:
        l2b = min(l2b, 15 / 85 * (l1 + l2a))          # level 2B at most 15% of total
        l2 = min(l2a + l2b, 40 / 60 * l1)              # level 2 at most 40% of total
        l2b = min(l2b, l2)
        l2a = l2 - l2b
    return dict(level1=l1, level2a=l2a, level2b=l2b, total=l1 + l2a + l2b)


def lcr(row, deposit_runoff=REG_DEPOSIT_RUNOFF, draw=REG_DRAW, haircut=REG_HAIRCUT,
        inflow_rate=REG_INFLOW_RATE, wholesale_rollover=0.0) -> dict:
    h = hqla(row, haircut)
    dep_out = {k: row["dep_" + k] * deposit_runoff[k] for k in DEPOSIT_SEGMENTS}
    draw_out = {k: row["und_" + k] * draw[k] for k in COMMITMENTS}
    ws_out = row["wholesale_short"] * (1 - wholesale_rollover)
    outflows = sum(dep_out.values()) + sum(draw_out.values()) + ws_out
    inflows_raw = sum(row[k] * LOAN_DUE_30D[k] for k in LOAN_DUE_30D) * inflow_rate
    inflows = min(inflows_raw, REG_INFLOW_CAP * outflows)
    net = outflows - inflows
    return dict(hqla=h["total"], hqla_detail=h, deposit_outflows=dep_out,
                draw_outflows=draw_out, wholesale_outflow=ws_out, outflows=outflows,
                inflows=inflows, net_outflows=net, ratio=h["total"] / net)


def nsfr(row) -> dict:
    asf = (row["equity"] * NSFR_ASF["equity"] + row["wholesale_long"] * NSFR_ASF["wholesale_long"]
           + row["wholesale_short"] * NSFR_ASF["wholesale_short"]
           + row["other_liabilities"] * NSFR_ASF["other_liabilities"]
           + sum(row["dep_" + k] * NSFR_ASF[k] for k in DEPOSIT_SEGMENTS))
    undrawn = sum(row["und_" + k] for k in COMMITMENTS)
    rsf = (sum(row[k] * NSFR_RSF[k] for k in ("reserves", "treasuries", "agency_mbs", "corp_bonds",
                                              "loan_commercial", "loan_mortgage", "loan_consumer",
                                              "other_assets"))
           + undrawn * NSFR_RSF["undrawn"])
    return dict(asf=asf, rsf=rsf, ratio=asf / rsf)


def runoff_path(total_30d: float, assumptions=INTERNAL) -> np.ndarray:
    """Daily outflow amounts over the horizon: front loaded to day 30, then a slow tail."""
    h = assumptions["horizon"]
    tau = assumptions["front_load_tau"]
    t = np.arange(1, 31)
    cum = (1 - np.exp(-t / tau)) / (1 - np.exp(-30 / tau))
    daily = np.diff(np.concatenate([[0.0], cum])) * total_30d
    tail = np.full(h - 30, total_30d * assumptions["tail_runoff"] / (h - 30))
    return np.concatenate([daily, tail])


def internal_stress(row, assumptions=INTERNAL) -> dict:
    """Day by day projection under the internal combined scenario."""
    h = assumptions["horizon"]
    out = np.zeros(h)
    by_source = {}
    for k in DEPOSIT_SEGMENTS:
        p = runoff_path(row["dep_" + k] * assumptions["deposit_runoff"][k], assumptions)
        by_source["dep_" + k] = p.sum()
        out += p
    for k in COMMITMENTS:
        p = runoff_path(row["und_" + k] * assumptions["draw"][k], assumptions)
        p[30:] = 0.0                      # draws are a 30 day phenomenon in this scenario
        by_source["und_" + k] = p.sum()
        out += p
    ws = np.zeros(h)
    ws[:30] = row["wholesale_short"] * (1 - assumptions["wholesale_rollover"]) / 30
    by_source["wholesale_short"] = ws.sum()
    out += ws
    inflow = np.full(h, sum(row[k] * LOAN_DUE_30D[k] for k in LOAN_DUE_30D) * assumptions["inflow_rate"] / 30)
    net = out - inflow
    cum = np.cumsum(net)
    cbc = hqla(row, assumptions["haircut"], apply_caps=False)["total"]
    breach = np.where(cum > cbc)[0]
    survival = int(breach[0] + 1) if len(breach) else h + 1
    return dict(daily_net=net, cumulative=cum, cbc=cbc, survival_days=survival,
                coverage_30d=cbc / cum[29], by_source=by_source, net_30d=cum[29])


def snapshot(row, assumptions=INTERNAL) -> dict:
    """The headline numbers for one date."""
    l, n, s = lcr(row), nsfr(row), internal_stress(row, assumptions)
    deposits = sum(row["dep_" + k] for k in DEPOSIT_SEGMENTS)
    loans = sum(row[k] for k in LOAN_DUE_30D)
    undrawn = sum(row["und_" + k] for k in COMMITMENTS)
    uninsured = sum(row["dep_" + k] for k in DEPOSIT_SEGMENTS if not INSURED[k])
    return dict(lcr=l["ratio"], nsfr=n["ratio"], survival_days=s["survival_days"],
                coverage_30d=s["coverage_30d"], hqla=l["hqla"], net_outflows=l["net_outflows"],
                deposits=deposits, loans=loans, undrawn=undrawn,
                uninsured_share=uninsured / deposits, fi_share=row["dep_fi_nonop"] / deposits,
                loan_to_deposit=loans / deposits, undrawn_to_hqla=undrawn / l["hqla"],
                wholesale_to_hqla=row["wholesale_short"] / l["hqla"])


def history(df: pd.DataFrame, assumptions=INTERNAL) -> pd.DataFrame:
    """Every metric, every day."""
    rows = [snapshot(r, assumptions) for _, r in df.iterrows()]
    return pd.DataFrame(rows, index=df.index)
