"""Unit tests for the generator, metrics, attribution, limits, challenge, model and narrative."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.generate import events, generate
from src import attribution, challenge, limits, ml, narrative
from src import metrics as m

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def df():
    return generate()


@pytest.fixture(scope="module")
def hist(df):
    return m.history(df)


@pytest.fixture(scope="module")
def panels(df):
    return {"deposit_runoff": ml.deposit_panel(df), "draw": ml.commitment_panel(df)}


@pytest.fixture(scope="module")
def models(df, panels):
    sel_d, fit_d = ml.select(df, panels["deposit_runoff"], "dep_", m.DEPOSIT_SEGMENTS)
    sel_c, fit_c = ml.select(df, panels["draw"], "und_", m.COMMITMENTS)
    return {"deposit_runoff": fit_d[ml.chosen_name(sel_d)], "draw": fit_c[ml.chosen_name(sel_c)],
            "sel_d": sel_d, "sel_c": sel_c}


def simple_row():
    """A hand-sized balance sheet for hand calculations."""
    r = {"reserves": 100.0, "treasuries": 100.0, "agency_mbs": 100.0, "corp_bonds": 100.0,
         "loan_commercial": 1000.0, "loan_mortgage": 1000.0, "loan_consumer": 100.0, "other_assets": 100.0,
         "wholesale_short": 100.0, "wholesale_long": 500.0, "other_liabilities": 50.0, "equity": 300.0}
    for k in m.DEPOSIT_SEGMENTS:
        r["dep_" + k] = 100.0
    for k in m.COMMITMENTS:
        r["und_" + k] = 100.0
    return pd.Series(r)


# generator

def test_row_count_and_dates(df):
    assert len(df) == len(pd.bdate_range("2023-01-02", "2026-08-31"))
    assert df.index[0] == pd.Timestamp("2023-01-02")


def test_balance_sheet_identity_every_day(df):
    assets = df[["reserves", "treasuries", "agency_mbs", "corp_bonds", "loan_commercial",
                 "loan_mortgage", "loan_consumer", "other_assets"]].sum(axis=1)
    liabs = df[["dep_" + k for k in m.DEPOSIT_SEGMENTS]].sum(axis=1) + df[
        ["wholesale_short", "wholesale_long", "other_liabilities", "equity"]].sum(axis=1)
    assert np.allclose(assets, liabs, atol=0.05)


def test_no_negative_balances(df):
    assert (df.drop(columns=["stress_index", "fed_funds"]) >= 0).all().all()


def test_seeded_and_reproducible(df):
    assert generate().equals(df)


def test_stress_index_bounded_and_peaks_in_2025(df):
    s = df["stress_index"]
    assert s.between(0, 1).all()
    assert s.idxmax().year == 2025 and s.max() == 1.0


def test_program_brings_hot_money(df):
    a, b = pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")
    assert df.loc[b, "dep_fi_nonop"] - df.loc[a, "dep_fi_nonop"] > 2000
    assert df.loc[b, "loan_commercial"] - df.loc[a, "loan_commercial"] > 2000


def test_csv_matches_generator(df):
    on_disk = pd.read_csv(ROOT / "data" / "banking_book.csv", index_col="date", parse_dates=True)
    pd.testing.assert_frame_equal(on_disk, df, check_freq=False, check_exact=False, atol=1e-3)


def test_events_table():
    e = events()
    assert set(e["kind"]) == {"stress episode", "business initiative"}
    assert len(e) == 3


# metrics

def test_lcr_hand_calculation():
    r = simple_row()
    l = m.lcr(r)
    # level 1 = 200; level 2A = 85; level 2B = 50, capped at 15% of total: 15/85 * 285 = 50.29 -> 50 stands
    # level 2 = 135, cap 40% of total: 40/60 * 200 = 133.33 binds -> total 333.33
    assert l["hqla"] == pytest.approx(200 + 133.3333, rel=1e-4)
    dep = 100 * (0.03 + 0.10 + 0.05 + 0.25 + 0.40 + 1.00)
    draw = 100 * (0.05 + 0.10 + 0.30 + 0.40)
    assert l["outflows"] == pytest.approx(dep + draw + 100)
    inflow = 0.5 * (1000 * 0.04 + 1000 * 0.01 + 100 * 0.05)
    assert l["inflows"] == pytest.approx(inflow)
    assert l["ratio"] == pytest.approx(l["hqla"] / (l["outflows"] - inflow))


def test_level2_cap_binds_when_level2_is_large():
    r = simple_row()
    r["agency_mbs"] = 10000.0
    h = m.hqla(r)
    assert h["level2a"] + h["level2b"] == pytest.approx(40 / 60 * h["level1"])


def test_inflow_cap_binds_when_loans_dominate():
    r = simple_row()
    r["loan_commercial"] = 1e6
    l = m.lcr(r)
    assert l["inflows"] == pytest.approx(0.75 * l["outflows"])


def test_nsfr_hand_calculation():
    r = simple_row()
    n = m.nsfr(r)
    asf = 300 + 500 + 100 * (0.95 + 0.90 + 0.95 + 0.50 + 0.50 + 0.0)
    rsf = 100 * 0.05 + 100 * 0.15 + 100 * 0.5 + 1000 * 0.85 + 1000 * 0.65 + 100 * 0.85 + 100 + 400 * 0.05
    assert n["asf"] == pytest.approx(asf) and n["rsf"] == pytest.approx(rsf)


def test_runoff_path_sums_and_front_loads():
    p = m.runoff_path(1000.0)
    assert p[:30].sum() == pytest.approx(1000.0)
    assert p.sum() == pytest.approx(1000.0 * (1 + m.INTERNAL["tail_runoff"]))
    assert p[:10].sum() > 0.65 * 1000


def test_survival_beyond_horizon_with_abundant_hqla():
    r = simple_row()
    r["reserves"] = 1e7
    assert m.internal_stress(r)["survival_days"] == m.INTERNAL["horizon"] + 1


def test_harsher_assumptions_shorten_survival(df):
    row = df.iloc[-1]
    base = m.internal_stress(row)["survival_days"]
    harsh = {**m.INTERNAL, "deposit_runoff": {k: min(1.0, v * 1.5) for k, v in m.INTERNAL["deposit_runoff"].items()}}
    assert m.internal_stress(row, harsh)["survival_days"] < base


def test_history_has_every_metric(hist, df):
    assert len(hist) == len(df)
    for k in limits.LIMITS:
        assert k in hist.columns and hist[k].notna().all()


# attribution

def test_attribution_total_equals_metric_change(df):
    a, b = attribution.window_dates(df, "Q2 2026: institutional cash program")
    t, base, final = attribution.attribute(df, a, b)
    total = t[t["driver"] == "total"].iloc[0]
    assert total["d lcr"] == pytest.approx(final["lcr"] - base["lcr"])
    pieces = t[~t["driver"].isin(["total"])]["d lcr"].sum()
    assert pieces == pytest.approx(total["d lcr"])


def test_interaction_is_small_relative_to_total(df):
    a, b = attribution.window_dates(df, "Q2 2026: institutional cash program")
    t, _, _ = attribution.attribute(df, a, b)
    inter = abs(t.loc[t["driver"] == "interaction", "d lcr"].iloc[0])
    total = abs(t.loc[t["driver"] == "total", "d lcr"].iloc[0])
    assert inter < 0.25 * total


def test_lending_is_the_largest_drag_in_the_program(df):
    a, b = attribution.window_dates(df, "Q2 2026: institutional cash program")
    t, base, final = attribution.attribute(df, a, b)
    drivers = t[~t["driver"].isin(["interaction", "total"])].set_index("driver")
    assert drivers["d lcr"].idxmin() == "loans"
    assert final["lcr"] < base["lcr"] - 0.08


def test_held_as_cash_beats_actual(df):
    a, b = attribution.window_dates(df, "Q2 2026: institutional cash program")
    _, _, final = attribution.attribute(df, a, b)
    assert attribution.held_as_cash(df, a, b)["lcr"] > final["lcr"] + 0.05


def test_last_20_days_window(df):
    a, b = attribution.window_dates(df, "last 20 business days")
    assert (b - a).days >= 26 and b == df.index[-1]


# limits

def test_status_floor_and_cap():
    assert limits.status(1.20, "lcr") == "green"
    assert limits.status(1.12, "lcr") == "amber"
    assert limits.status(1.05, "lcr") == "red"
    assert limits.status(0.30, "uninsured_share") == "green"
    assert limits.status(0.42, "uninsured_share") == "amber"
    assert limits.status(0.50, "uninsured_share") == "red"


def test_limit_table_and_counts(df):
    snap = m.snapshot(df.iloc[-1])
    t = limits.table(snap)
    assert len(t) == len(limits.LIMITS)
    c = limits.counts(snap)
    assert c["red"] + c["amber"] + c["green"] == len(limits.LIMITS)
    assert "LCR" in c["red_names"]


def test_breach_log_runs():
    idx = pd.bdate_range("2024-01-01", periods=10)
    h = pd.DataFrame({k: 10.0 for k in limits.LIMITS}, index=idx)
    h["lcr"] = [1.2, 1.2, 1.0, 1.0, 1.0, 1.2, 1.2, 1.05, 1.05, 1.05]
    h["survival_days"] = 91
    h["nsfr"] = 1.2
    for k in ("uninsured_share", "fi_share", "loan_to_deposit", "undrawn_to_hqla", "wholesale_to_hqla"):
        h[k] = 0.0
    log = limits.breach_log(h)
    lcr_runs = log[log["indicator"] == "LCR"]
    assert list(lcr_runs["business days"]) == [3, 3]
    assert list(lcr_runs["status"]) == ["resolved", "still in breach"]


def test_the_program_puts_lcr_in_breach(hist):
    log = limits.breach_log(hist)
    open_runs = log[log["status"] == "still in breach"]["indicator"].tolist()
    assert "LCR" in open_runs


# challenge

def test_verdict_rules():
    assert challenge.verdict(0.40, 0.50, 0.42, 0.39) == ("rejected", None)
    assert challenge.verdict(0.12, 0.13, 0.109, 0.106) == ("accepted", None)
    assert challenge.verdict(0.30, 0.35, 0.29, 0.28) == ("counter-proposed", 0.32)
    assert challenge.verdict(0.06, 0.08, 0.048, 0.071) == ("rejected", None)


def test_floor_rounds_up_to_whole_percent():
    assert challenge.floor_from(0.291, 0.28) == pytest.approx(0.33)
    assert challenge.floor_from(0.10, 0.10) == pytest.approx(0.11)


def test_three_verdicts_spread(df, models, panels):
    res = challenge.evaluate(df, df.iloc[-1], models, panels)
    verdicts = {r["id"]: r["verdict"] for r in res}
    assert verdicts == {"P1": "rejected", "P2": "accepted", "P3": "counter-proposed"}


def test_memo_text(df, models, panels):
    for r in challenge.evaluate(df, df.iloc[-1], models, panels):
        assert r["verdict"] in r["memo"]
        assert "—" not in r["memo"]
        assert r["adopted"] >= r["realized_worst"]


# model

def test_panels_have_no_gaps(panels):
    for p in panels.values():
        assert not p.isna().any().any()
        assert p["target"].abs().max() < 1.0


def test_target_definition(df, panels):
    p = panels["deposit_runoff"]
    day = p.index[100]
    seg = p.loc[day].iloc[0]["name"] if isinstance(p.loc[day], pd.DataFrame) else p.loc[day]["name"]
    b = df["dep_" + seg]
    i = df.index.get_loc(day)
    expected = 1 - b.iloc[i + ml.HORIZON] / b.iloc[i]
    got = p[(p.index == day) & (p["name"] == seg)]["target"].iloc[0]
    assert got == pytest.approx(expected)


def test_benchmark_has_four_candidates(panels):
    t, _ = ml.benchmark(panels["deposit_runoff"])
    assert len(t) == 4 and t["mae all days"].notna().all()


def test_no_model_calls_the_event_at_onset(panels):
    t, _ = ml.benchmark(panels["deposit_runoff"])
    assert (t["largest call at onset"] < 0.25 * t["largest outflow that followed"]).all()


def test_selection_picks_one_model(models):
    assert models["sel_d"]["chosen"].sum() == 1 and models["sel_c"]["chosen"].sum() == 1


def test_tree_reading_never_exceeds_history(df, models, panels):
    p = panels["deposit_runoff"]
    for k in m.DEPOSIT_SEGMENTS:
        reading = ml.stressed_prediction(models["deposit_runoff"], p, k)
        assert reading <= p["target"].max() + 0.02


def test_history_beat_the_regulatory_weight_somewhere(df):
    beaten = [k for k in m.DEPOSIT_SEGMENTS if ml.realized_worst(df, "dep_", k)[0] > m.REG_DEPOSIT_RUNOFF[k]]
    assert "corp_nonop" in beaten
    for k in m.DEPOSIT_SEGMENTS:
        assert ml.realized_worst(df, "dep_", k)[0] <= m.INTERNAL["deposit_runoff"][k]


def test_importance_excludes_identity(models, panels):
    imp = ml.importance(models["deposit_runoff"], panels["deposit_runoff"], n_repeats=2)
    assert not imp["feature"].str.startswith("is_").any()
    assert imp.iloc[0]["importance"] > 0


# narrative

def facts():
    return narrative.build_facts(pd.Timestamp("2026-08-31"), {"lcr": 1.039, "nsfr": 1.16, "survival_days": 26},
                                 {"red": 2, "amber": 3, "red_names": ["LCR"]}, "loans", -11.5, 3349.0,
                                 ["rejected", "accepted", "counter-proposed"])


def test_template_passes_its_own_number_check():
    f = facts()
    assert narrative.numbers_check(narrative.template(f), f)


def test_invented_number_is_caught():
    f = facts()
    assert not narrative.numbers_check("LCR is 98.2% and survival is 26 days.", f)


def test_template_has_no_em_dash():
    assert "—" not in narrative.template(facts())


def test_no_em_dashes_or_company_names_in_repo():
    banned = re.compile(r"—|jpmorgan|jpmc|chase bank", re.I)
    for path in list(ROOT.glob("*.md")) + list(ROOT.glob("*.py")) + list(ROOT.rglob("src/*.py")) + \
            list(ROOT.rglob("data/*.py")) + list(ROOT.rglob("docs/*.md")):
        assert not banned.search(path.read_text()), path
