"""banking-liquidity-risk-lab: a second line view of one bank's Banking book.

Deposits, loans and undrawn commitments on a synthetic balance sheet; what
each move did to LCR, NSFR and the internal stress; the limits it is run
against; and an evidence-based challenge of proposed assumption changes.
Read the tabs left to right.
"""
import altair as alt
import pandas as pd
import streamlit as st

from data.generate import events, generate
from src import attribution, challenge, limits, ml, narrative
from src import metrics as m

st.set_page_config(page_title="Banking Liquidity Risk Lab", layout="wide")

# Streamlit hashes a cached function's own source, not what it calls. Bump this
# string whenever the generator, metrics or models change.
PIPELINE_VERSION = "2026-09-07-v3-trimmed"

SEGMENT_LABEL = {"retail_stable": "retail, stable (insured)", "retail_less_stable": "retail, less stable (insured)",
                 "small_business": "small business (insured)", "corp_operational": "corporate operational",
                 "corp_nonop": "corporate non-operational", "fi_nonop": "financial institution non-operational",
                 "retail_lines": "retail credit lines", "corp_credit": "corporate credit facilities",
                 "corp_liquidity": "corporate liquidity facilities", "fi_facilities": "financial institution facilities"}


def table(df, wide=()):
    """Full width dataframe; `wide` names text columns that must not be squeezed."""
    config = {c: st.column_config.Column(width="large") for c in wide if c in df.columns}
    try:
        st.dataframe(df, width="stretch", hide_index=True, column_config=config)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, column_config=config)


def chart(c):
    try:
        st.altair_chart(c, width="stretch")
    except Exception:
        st.altair_chart(c, use_container_width=True)


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def bn(x):
    return f"{x / 1000:.1f}bn"


@st.cache_resource(show_spinner="Building the balance sheet, metrics and models...")
def load_all(version: str) -> dict:
    df = generate()
    hist = m.history(df)
    dp, cp = ml.deposit_panel(df), ml.commitment_panel(df)
    sel_d, fit_d = ml.select(df, dp, "dep_", m.DEPOSIT_SEGMENTS)
    sel_c, fit_c = ml.select(df, cp, "und_", m.COMMITMENTS)
    models = {"deposit_runoff": fit_d[ml.chosen_name(sel_d)], "draw": fit_c[ml.chosen_name(sel_c)]}
    panels = {"deposit_runoff": dp, "draw": cp}
    bench_d, _ = ml.benchmark(dp)
    bench_c, _ = ml.benchmark(cp)
    row = df.iloc[-1]
    results = challenge.evaluate(df, row, models, panels)
    imp = ml.importance(models["deposit_runoff"], dp)
    return dict(df=df, hist=hist, panels=panels, models=models, sel_d=sel_d, sel_c=sel_c,
                bench_d=bench_d, bench_c=bench_c, results=results, importance=imp,
                events=events())


L = load_all(PIPELINE_VERSION)
df, hist = L["df"], L["hist"]
as_of = df.index[-1]
row = df.loc[as_of]
snap = m.snapshot(row)
counts = limits.counts(snap)
q_start, q_end = attribution.window_dates(df, "Q2 2026: institutional cash program")
attr, attr_base, attr_final = attribution.attribute(df, q_start, q_end)
drivers_only = attr[~attr["driver"].isin(["interaction", "total"])]
top = drivers_only.loc[drivers_only["d lcr"].abs().idxmax()]
deposits_change = attr_final["deposits"] - attr_base["deposits"]
facts = narrative.build_facts(as_of, snap, counts, top["driver"], top["d lcr"] * 100,
                              deposits_change, [r["verdict"] for r in L["results"]])
text, source = narrative.narrative(facts)

st.title("Banking Liquidity Risk Lab")
st.write(
    "One synthetic bank, its Banking book only: deposits, loans and undrawn commitments. "
    "The app is the second line's view of it: what moved on the balance sheet and what that "
    "did to liquidity, the limits the book is run against, the internal stress next to the "
    "regulatory ratios, and an evidence-based challenge of proposed assumption changes. "
    "All data is synthetic and seeded."
)
st.write(f"As of **{as_of.date()}**, USD millions throughout.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("LCR", pct(snap["lcr"]), f"{(snap['lcr'] - attr_base['lcr']) * 100:+.1f} pts since {q_start.date()}",
          delta_color="normal")
c2.metric("NSFR", pct(snap["nsfr"]), f"{(snap['nsfr'] - attr_base['nsfr']) * 100:+.1f} pts since {q_start.date()}")
c3.metric("Survival horizon, internal stress", f"{snap['survival_days']} days",
          f"{snap['survival_days'] - attr_base['survival_days']:+d} days since {q_start.date()}")
c4.metric("Indicators in breach", f"{counts['red']} red, {counts['amber']} amber")

st.write("**For senior management.** " + text)
st.caption(f"Narrative source: {source}. Every number in it comes from the fact set below the app; "
           "an LLM may phrase it, and a draft with a figure not in the facts is discarded.")

tab1, tab2, tab3, tab4 = st.tabs(["1 Balance sheet: what moved", "2 Limits and indicators",
                                  "3 Stress: internal vs regulatory", "4 Challenge"])

with tab1:
    window = st.selectbox("Window", list(attribution.WINDOWS), index=0)
    a, b = attribution.window_dates(df, window)
    t, base, final = attribution.attribute(df, a, b)
    cash = attribution.held_as_cash(df, a, b)
    st.write(
        f"From {a.date()} to {b.date()}: deposits {bn(final['deposits'] - base['deposits'])}, "
        f"loans {bn(final['loans'] - base['loans'])}, undrawn commitments "
        f"{bn(final['undrawn'] - base['undrawn'])}. LCR {pct(base['lcr'])} to {pct(final['lcr'])}, "
        f"NSFR {pct(base['nsfr'])} to {pct(final['nsfr'])}, survival horizon "
        f"{base['survival_days']} to {final['survival_days']} days."
    )
    if window.startswith("Q2 2026"):
        st.write(
            f"**Deposits grew and the balance sheet looks healthier, yet LCR fell "
            f"{(base['lcr'] - final['lcr']) * 100:.0f} points.** Lending the new money cost "
            f"{-drivers_only.set_index('driver').loc['loans', 'd lcr'] * 100:.0f} points on its own. The new deposits "
            f"themselves added almost nothing, because financial institution money carries a 100% runoff weight: "
            f"a dollar in is a dollar of HQLA and a dollar of outflow. Had the same deposits been held as cash, "
            f"LCR would be {pct(cash['lcr'])} and the survival horizon {cash['survival_days']} days."
        )
    view = t.copy()
    view["change (USD m)"] = view["change"].map(lambda v: f"{v:+,.0f}" if v else "")
    view["LCR (pts)"] = (view["d lcr"] * 100).map(lambda v: f"{v:+.1f}")
    view["NSFR (pts)"] = (view["d nsfr"] * 100).map(lambda v: f"{v:+.1f}")
    table(view[["driver", "change (USD m)", "LCR (pts)", "NSFR (pts)"]], wide=("driver",))
    st.caption("One driver at a time: each row applies only that line's change to the opening balance sheet, "
               "lets reserves absorb the cash consequence, and recomputes. Pieces do not add exactly because "
               "the metrics are ratios; the leftover is shown as interaction.")

with tab2:
    status_view = limits.table(snap)
    status_view["status"] = status_view["status"].str.upper()
    table(status_view, wide=("indicator",))
    log = limits.breach_log(hist)
    open_runs = log[log["status"] == "still in breach"]
    if len(open_runs):
        st.caption("Trigger means talk about it; limit means escalate; the internal limit sits above the regulatory "
                   "minimum on purpose. Open breaches: "
                   + "; ".join(f"{r['indicator']} since {r['from']} (worst {r['worst']})" for _, r in open_runs.iterrows())
                   + ".")
    surv_limit = limits.LIMITS["survival_days"]
    sv = hist[["survival_days"]].rename_axis("date").reset_index()
    line = alt.Chart(sv).mark_line(color="#0d7c7a").encode(
        x=alt.X("date:T", title=None), y=alt.Y("survival_days:Q", title="days (91 = beyond the 90 day horizon)"),
        tooltip=["date:T", "survival_days:Q"])
    rules = alt.Chart(pd.DataFrame({"y": [surv_limit[1], surv_limit[2]], "kind": ["trigger", "limit"]})).mark_rule(
        strokeDash=[4, 4]).encode(y="y:Q", color=alt.Color("kind:N", title=None))
    chart(alt.layer(line, rules).properties(height=260, title="Survival horizon under the internal combined stress"))
    st.write("**The spring 2025 dip is the point.** LCR barely moved then (a low of about 118% against 132% before) "
             "while the bank burned a third of its HQLA, because the fastest money to leave carries a 100% weight: "
             "every dollar of it that goes takes a dollar of HQLA and a dollar of assumed outflow with it, so the "
             "ratio hardly moves while the cash does. The survival horizon caught it. The ratio is a snapshot; the "
             "horizon is a cash flow. A second line watches both.")

with tab3:
    l = m.lcr(row)
    n = m.nsfr(row)
    s = m.internal_stress(row)
    st.write(f"LCR = HQLA {l['hqla']:,.0f} / net 30 day outflows {l['net_outflows']:,.0f} = **{pct(l['ratio'])}**. "
             f"NSFR = available {n['asf']:,.0f} / required {n['rsf']:,.0f} = **{pct(n['ratio'])}**. "
             f"Internal combined stress: counterbalancing capacity {s['cbc']:,.0f} against {s['net_30d']:,.0f} "
             f"out by day 30, coverage **{pct(s['coverage_30d'])}**, survival horizon **{s['survival_days']} days**.")
    proj = pd.DataFrame({"day": range(1, len(s["cumulative"]) + 1), "cumulative net outflow": s["cumulative"],
                         "counterbalancing capacity": s["cbc"]})
    long = proj.melt("day", var_name="line", value_name="USD m")
    c = alt.Chart(long).mark_line().encode(x=alt.X("day:Q", title="business day of the stress"),
                                          y=alt.Y("USD m:Q", title="USD m"), color=alt.Color("line:N", title=None),
                                          tooltip=["day:Q", "line:N", alt.Tooltip("USD m:Q", format=",.0f")])
    chart(c.properties(height=260, title="Internal stress: cash out versus cash available"))
    st.caption("Runoff is front loaded (about 70% of the 30 day amount in the first ten days), wholesale does not "
               "roll, draws happen inside 30 days, a slower tail continues to day 90. The horizon is the day the "
               "lines cross. Weights and sources: docs/assumptions.md.")
    rec = []
    for k in m.DEPOSIT_SEGMENTS:
        realized, when = ml.realized_worst(df, "dep_", k)
        reading = ml.stressed_prediction(L["models"]["deposit_runoff"], L["panels"]["deposit_runoff"], k)
        rec.append({"item": "deposits: " + SEGMENT_LABEL[k], "regulatory 30 day weight": pct(m.REG_DEPOSIT_RUNOFF[k], 0),
                    "internal assumption": pct(m.INTERNAL["deposit_runoff"][k], 0),
                    "realized worst": f"{pct(realized)} (from {when.date()})", "model reading": pct(reading),
                    "history beat the regulatory weight": "yes" if realized > m.REG_DEPOSIT_RUNOFF[k] else "no"})
    for k in m.COMMITMENTS:
        realized, when = ml.realized_worst(df, "und_", k)
        reading = ml.stressed_prediction(L["models"]["draw"], L["panels"]["draw"], k)
        rec.append({"item": "undrawn: " + SEGMENT_LABEL[k], "regulatory 30 day weight": pct(m.REG_DRAW[k], 0),
                    "internal assumption": pct(m.INTERNAL["draw"][k], 0),
                    "realized worst": f"{pct(realized)} (from {when.date()})", "model reading": pct(reading),
                    "history beat the regulatory weight": "yes" if realized > m.REG_DRAW[k] else "no"})
    rec = pd.DataFrame(rec)
    beaten = rec[rec["history beat the regulatory weight"] == "yes"]["item"].tolist()
    st.write(f"**Reconciliation by segment.** {len(beaten)} of {len(rec)} lines have already run past their "
             f"regulatory weight in this history ({'; '.join(beaten)}). None has run past its internal assumption. "
             "That gap is why the internal scenario exists, and why the challenge in the next tab starts from "
             "realized history.")
    table(rec, wide=("item", "realized worst"))

with tab4:
    st.write("The first line proposes a change to an internal stress assumption. The second line tests it against "
             "two witnesses, the worst the segment has actually done and the model's reading of its history, puts a "
             "10% buffer on the stronger one, and applies a written rule: below realized history is rejected; at or "
             "above the floor is accepted; in between is counter-proposed at the floor.")
    table(challenge.summary_table(L["results"]), wide=("assumption", "survival now / proposed / verdict"))
    for r in L["results"]:
        with st.expander(f"{r['id']}, {r['verdict']}: {r['kind'].replace('_', ' ')} on "
                         f"{r['name'].replace('_', ' ')}, {pct(r['current'], 0)} to {pct(r['proposed'], 0)}"):
            st.write(f"Submitted rationale: \"{r['rationale']}\"")
            st.write(r["memo"])
    st.write("**The model, and what it cannot do.** Four candidates scored on a time split, trained before 2025 and "
             "tested on 2025 onward, which contains the confidence event. Read the last two columns: when stress had "
             "risen but the money had not yet left, the largest outflow any model called was about a fifth of what "
             "followed. A model trained on calm history cannot see the first severe event coming, and a tree model "
             "cannot predict an outflow larger than any it has seen. That is why the model is a witness in the "
             "challenge and never the assumption. The evidence model is gradient boosting, chosen because it reads "
             "each segment's own worst stress most faithfully; the selection tables and feature importance live in "
             "the code and tests.")
    bd = L["bench_d"].copy()
    for c in ("mae all days", "mae stress days", "largest call at onset", "largest outflow that followed"):
        bd[c] = bd[c].map(lambda v: pct(v, 1))
    table(bd)
    st.caption("Deposit outflow 30 business days ahead, per segment. Persistence predicts the last 30 days' outflow "
               "again. Errors in percentage points of balance.")
