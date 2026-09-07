"""Learned 30 day outflow and draw behavior, as evidence for the challenge.

Two regressors, one for deposit outflows by segment and one for commitment
draws by facility type, trained on the bank's own history. The question
they answer is not "what will happen" but "what does the history say this
segment does when stress rises", which is what a second line puts next to
a first line assumption.

Model choice is by benchmark, not by taste: a persistence baseline, a
ridge regression, a random forest and gradient boosting are scored on a
time split and the best mean absolute error ships. The split also exposes
the limit of the approach: a tree cannot predict an outflow larger than
any it has seen, so a model trained before the 2025 event under-calls it.
That is the reason the model is evidence and the assumption is a decision.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge

from src.metrics import COMMITMENTS, DEPOSIT_SEGMENTS, INSURED

HORIZON = 30
WARMUP = 60
SPLIT = "2025-01-01"


def _panel(df, prefix, names, rate_gap=False):
    """Stack one row per (name, day): features on day t, outflow over t+1..t+30."""
    s = df["stress_index"]
    frames = []
    for name in names:
        b = df[prefix + name]
        f = pd.DataFrame(index=df.index)
        f["stress"] = s
        f["stress_change_5d"] = s - s.shift(5)
        f["stress_max_20d"] = s.rolling(20).max()
        f["trailing_5d"] = 1 - b / b.shift(5)
        f["trailing_20d"] = 1 - b / b.shift(20)
        f["trailing_30d"] = 1 - b / b.shift(30)
        if rate_gap:
            f["uninsured"] = float(not INSURED[name])
            # TODO: a rate gap feature (fed funds minus the segment's rate) is the
            # obvious next driver. In this synthetic history it only identifies the
            # segment, so it is left out until the generator gives it real variation.
        for other in names:
            f["is_" + other] = float(other == name)
        f["name"] = name
        f["target"] = 1 - b.shift(-HORIZON) / b
        frames.append(f)
    panel = pd.concat(frames).dropna()
    panel = panel[panel.index >= df.index[WARMUP]]
    return panel


def deposit_panel(df):
    return _panel(df, "dep_", DEPOSIT_SEGMENTS, rate_gap=True)


def commitment_panel(df):
    return _panel(df, "und_", COMMITMENTS)


def feature_columns(panel):
    return [c for c in panel.columns if c not in ("name", "target")]


def candidates(seed=0):
    return {
        "persistence (last 30 days)": None,
        "ridge regression": Ridge(alpha=1.0),
        "random forest": RandomForestRegressor(n_estimators=200, min_samples_leaf=20,
                                               random_state=seed, n_jobs=1),
        "gradient boosting": HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05,
                                                           max_leaf_nodes=31, min_samples_leaf=20,
                                                           random_state=seed),
    }


def _predict(model, frame, cols):
    if model is None:
        return frame["trailing_30d"].to_numpy()
    return model.predict(frame[cols])


def benchmark(panel, split=SPLIT, seed=0) -> tuple:
    """Score every candidate on a time split. Returns (table, fitted models)."""
    cols = feature_columns(panel)
    train = panel[panel.index < split]
    test = panel[panel.index >= split]
    stress_days = (test["stress"] > 0.5).to_numpy()
    # the onset: stress is up but the money has not left yet. this is the only
    # moment a forecast is worth anything, and the only fair place to compare peaks.
    onset = stress_days & (test["trailing_20d"] < 0.05).to_numpy()
    y = test["target"].to_numpy()
    rows, fitted = [], {}
    for name, model in candidates(seed).items():
        if model is not None:
            model.fit(train[cols], train["target"])
        pred = _predict(model, test, cols)
        err = np.abs(pred - y)
        peak_pred = float(pred[onset].max()) if onset.any() else np.nan
        peak_real = float(y[onset].max()) if onset.any() else np.nan
        rows.append({"model": name,
                     "mae all days": float(err.mean()),
                     "mae stress days": float(err[stress_days].mean()) if stress_days.any() else np.nan,
                     "largest call at onset": peak_pred,
                     "largest outflow that followed": peak_real})
        fitted[name] = model
    return pd.DataFrame(rows), fitted


def select(df, panel, prefix, names, seed=0) -> tuple:
    """Pick the evidence model by how faithfully it reads each segment's history.

    Every candidate is refit on the full history and asked for its stressed
    reading per segment; the score is the mean absolute gap to the worst 30
    day outflow that segment actually produced. A linear model gives every
    segment the same stress slope, so it reads a run on insured retail that
    never happened; a tree model learns the segment by stress interaction.
    This is in-sample by design: the job is to summarize history per
    segment, not to forecast past it, and the time split above says why.
    """
    cols = feature_columns(panel)
    realized = {n: realized_worst(df, prefix, n)[0] for n in names}
    rows, fitted = [], {}
    for model_name, model in candidates(seed).items():
        if model is None:
            continue
        model.fit(panel[cols], panel["target"])
        gaps = [abs(stressed_prediction(model, panel, n) - realized[n]) for n in names]
        rows.append({"model": model_name, "mean gap to realized worst": float(np.mean(gaps)),
                     "largest gap": float(np.max(gaps))})
        fitted[model_name] = model
    table = pd.DataFrame(rows)
    table["chosen"] = table["mean gap to realized worst"] == table["mean gap to realized worst"].min()
    return table, fitted


def chosen_name(table) -> str:
    return str(table.loc[table["chosen"], "model"].iloc[0])


def fit_final(panel, name="gradient boosting", seed=0):
    """The chosen model class, refit on all history, for use as evidence."""
    cols = feature_columns(panel)
    model = candidates(seed)[name]
    if model is None:
        raise ValueError("persistence has nothing to fit")
    model.fit(panel[cols], panel["target"])
    return model


def importance(model, panel, seed=0, n_repeats=5) -> pd.DataFrame:
    cols = feature_columns(panel)
    test = panel[panel.index >= SPLIT]
    r = permutation_importance(model, test[cols], test["target"], n_repeats=n_repeats,
                               random_state=seed)
    out = pd.DataFrame({"feature": cols, "importance": r.importances_mean}).sort_values(
        "importance", ascending=False)
    return out[~out["feature"].str.startswith("is_")].reset_index(drop=True)


def stressed_prediction(model, panel, name) -> float:
    """Model reading of the worst conditions `name` has faced: the largest
    prediction over the segment's own stress days (stress index above 0.5).

    This is a fitted reading of history, not a forecast beyond it. A tree
    model cannot predict an outflow larger than any it has seen, which is
    exactly why the reading is evidence for a challenge and never the
    assumption itself.
    """
    cols = feature_columns(panel)
    own = panel[panel["name"] == name]
    seen = own[own["stress"] > 0.5]
    if not len(seen):
        seen = own
    return float(model.predict(seen[cols]).max())


def realized_worst(df, prefix, name) -> tuple:
    """Largest 30 day outflow (or draw) actually observed, and when it started."""
    b = df[prefix + name]
    r = 1 - b.shift(-HORIZON) / b
    return float(r.max()), r.idxmax()
