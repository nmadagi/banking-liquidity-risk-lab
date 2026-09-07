"""The two paragraphs for senior management. Deterministic code decides
what the numbers are; an LLM, if a key is present, only phrases them, and
every number in its draft is checked against the fact set. One invented
figure and the draft is thrown away for the template.
"""
import os
import re


def build_facts(as_of, snap, limit_counts, attribution_driver, attribution_delta_pts,
                deposits_change, verdicts) -> dict:
    return {
        "as_of": str(as_of.date()),
        "lcr_pct": round(snap["lcr"] * 100, 1),
        "nsfr_pct": round(snap["nsfr"] * 100, 1),
        "survival_days": int(snap["survival_days"]),
        "n_red": int(limit_counts["red"]),
        "n_amber": int(limit_counts["amber"]),
        "red_names": list(limit_counts["red_names"]),
        "driver": attribution_driver,
        "driver_lcr_pts": round(attribution_delta_pts, 1),
        "deposits_change_bn": round(deposits_change / 1000, 1),
        "n_rejected": int(sum(v == "rejected" for v in verdicts)),
        "n_counter": int(sum(v == "counter-proposed" for v in verdicts)),
        "n_accepted": int(sum(v == "accepted" for v in verdicts)),
    }


def template(f: dict) -> str:
    reds = f"; in breach: {', '.join(f['red_names'])}" if f["red_names"] else ""
    first = (f"Liquidity position as of {f['as_of']}: LCR {f['lcr_pct']}%, NSFR {f['nsfr_pct']}%, "
             f"survival horizon {f['survival_days']} days under the internal combined stress. "
             f"{f['n_red']} indicators red and {f['n_amber']} amber{reds}.")
    second = (f"Deposits grew {f['deposits_change_bn']}bn over the quarter and the largest single "
              f"driver of the LCR move was {f['driver']} at {f['driver_lcr_pts']} points, because the "
              f"new balances are high-runoff money and were lent out rather than held.")
    third = (f"Assumption challenge this cycle: {f['n_rejected']} proposal rejected, {f['n_counter']} "
             f"counter-proposed, {f['n_accepted']} accepted, each against realized history and the "
             f"model reading.")
    return " ".join([first, second, third])


def numbers_check(text: str, facts: dict) -> bool:
    allowed = set()
    for v in facts.values():
        if isinstance(v, (int, float)):
            allowed.add(float(v))
            allowed.add(abs(float(v)))
    text = text.replace(facts["as_of"], "")
    for n in re.findall(r"\d+(?:\.\d+)?", text):
        if float(n) not in allowed:
            return False
    return True


def narrative(facts: dict) -> tuple:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return template(facts), "template (no API key set)"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-sonnet-5", max_tokens=400,
            messages=[{"role": "user", "content":
                       "Write a three sentence liquidity risk summary for a bank's senior "
                       "management using ONLY these facts and ONLY these numbers, plain prose, "
                       f"no markdown, no dates other than the as-of date: {facts}"}])
        text = msg.content[0].text.strip()
        if numbers_check(text, facts):
            return text, "llm (passed number check)"
        return template(facts), "template (llm draft failed number check)"
    except Exception:
        return template(facts), "template (llm unavailable)"
