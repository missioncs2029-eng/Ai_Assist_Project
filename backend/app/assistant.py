"""Grounded assistant. It only answers from stored readings and alerts, cites the numbers it used,
and says plainly when the data cannot answer. (No external LLM is called - see docs/AI_ETHICS.md.)"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from .services import GRID_KG_CO2_PER_KWH, build_dashboard, forecast_tomorrow

HELP = ("I can answer from your stored readings: today's energy, current power, best/weakest asset, open alerts "
        "and why they matter, tomorrow's forecast, and CO₂ avoided. Try: “Why is SOL-003 low?” or “How much energy today?”")


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", text) for w in words)


def answer(db: Session, question: str, now: datetime | None = None) -> dict:
    q = question.lower().strip()
    d = build_dashboard(db, now)
    s, assets = d["summary"], d["assets"]
    open_alerts = [a for a in d["alerts"] if not a["acknowledged"]]
    mentioned = next((a for a in assets if a["id"].lower() in q or a["name"].lower() in q), None)
    src: list[dict] = []

    if _has(q, "hello", "hi", "hey", "help", "what can you"):
        return {"intent": "help", "answer": HELP, "sources": []}

    if mentioned and not _has(q, "forecast", "tomorrow", "co2", "carbon"):
        al = [a for a in open_alerts if a["asset_id"] == mentioned["id"]]
        text = (f"{mentioned['name']} ({mentioned['id']}, {mentioned['location']}) is currently {mentioned['status']}, "
                f"producing {mentioned['power_kw']} kW of its {mentioned['capacity_kw']} kW capacity, with a 7-day "
                f"efficiency of {mentioned['efficiency']}% against clear-sky output.")
        src = [{"label": "Power now", "value": f"{mentioned['power_kw']} kW"},
               {"label": "7-day efficiency", "value": f"{mentioned['efficiency']}%"}]
        if al:
            text += " Open alert: " + al[0]["description"]
            src.append({"label": "Open alerts", "value": str(len(al))})
        else:
            text += " There are no open alerts for it."
        return {"intent": "asset", "answer": text, "sources": src}

    if _has(q, "alert", "problem", "issue", "fault", "wrong", "why", "anomal", "warning", "outage"):
        if not open_alerts:
            return {"intent": "alerts", "answer": "No open alerts. Over the last 72 hours every asset stayed within its expected range.",
                    "sources": [{"label": "Open alerts", "value": "0"}, {"label": "Assets", "value": str(len(assets))}]}
        text = f"There {'is' if len(open_alerts) == 1 else 'are'} {len(open_alerts)} open alert{'s' if len(open_alerts) != 1 else ''}. " \
               + " ".join(f"[{a['severity'].upper()}] {a['description']}" for a in open_alerts[:3])
        return {"intent": "alerts", "answer": text,
                "sources": [{"label": "Open alerts", "value": str(len(open_alerts))}] +
                           [{"label": a["asset_id"] or "fleet", "value": a["kind"]} for a in open_alerts[:3]]}

    if _has(q, "forecast", "tomorrow", "predict", "expect"):
        f = forecast_tomorrow(db, now)
        return {"intent": "forecast",
                "answer": f"For {f['date']} I expect about {f['total_kwh']} kWh, peaking near {f['peak_kw']} kW around {f['peak_time']} IST. "
                          f"This is a simple average of the same hours over the last {f['basis_days']} days, so cloud cover can change it.",
                "sources": [{"label": "Expected energy", "value": f"{f['total_kwh']} kWh"}, {"label": "Basis", "value": f"{f['basis_days']} days"}]}

    if _has(q, "co2", "carbon", "emission", "environment", "green"):
        kg = s["energy_today_kwh"] * GRID_KG_CO2_PER_KWH
        return {"intent": "co2",
                "answer": f"Today's {s['energy_today_kwh']} kWh avoids roughly {kg:.0f} kg of CO₂, assuming about {GRID_KG_CO2_PER_KWH} kg per kWh for the grid (an approximation).",
                "sources": [{"label": "Energy today", "value": f"{s['energy_today_kwh']} kWh"}, {"label": "Assumed factor", "value": f"{GRID_KG_CO2_PER_KWH} kg/kWh"}]}

    if _has(q, "best", "top", "highest", "worst", "lowest", "weakest", "rank", "compare", "efficien"):
        if not assets:
            return {"intent": "rank", "answer": "There are no assets yet.", "sources": []}
        ranked = sorted(assets, key=lambda a: a["efficiency"], reverse=True)
        best, worst = ranked[0], ranked[-1]
        return {"intent": "rank",
                "answer": f"Best by 7-day efficiency: {best['name']} at {best['efficiency']}%. Weakest: {worst['name']} at {worst['efficiency']}%. "
                          "Efficiency compares real output with a clear-sky expectation for the same capacity.",
                "sources": [{"label": a["id"], "value": f"{a['efficiency']}%"} for a in ranked]}

    if _has(q, "now", "current", "live", "right now", "power"):
        return {"intent": "power",
                "answer": f"The fleet is producing {s['current_power_kw']} kW right now: " +
                          ", ".join(f"{a['id']} {a['power_kw']} kW" for a in assets) + ".",
                "sources": [{"label": a["id"], "value": f"{a['power_kw']} kW"} for a in assets]}

    if _has(q, "today", "generated", "energy", "produced", "production", "yield", "kwh"):
        sign = "more" if s["change_percent"] >= 0 else "less"
        return {"intent": "energy",
                "answer": f"The fleet has generated {s['energy_today_kwh']} kWh so far today ({s['target_progress_percent']}% of the clear-sky day), "
                          f"{abs(s['change_percent'])}% {sign} than yesterday at the same hour. Rolling 24-hour performance is {s['performance_percent']}%.",
                "sources": [{"label": "Energy today", "value": f"{s['energy_today_kwh']} kWh"},
                            {"label": "Vs yesterday", "value": f"{s['change_percent']}%"},
                            {"label": "Performance", "value": f"{s['performance_percent']}%"}]}

    return {"intent": "unknown", "answer": "I can't answer that from the stored data, and I won't guess. " + HELP, "sources": []}
