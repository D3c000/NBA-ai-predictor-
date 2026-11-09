import datetime as dt
import math
import statistics
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="NBA AI Predictor", page_icon="🏀", layout="centered")
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {"User-Agent": "Mozilla/5.0 NBAResearchDashboard/1.1"}
NZ = ZoneInfo("Pacific/Auckland")
EAST = ZoneInfo("America/New_York")

st.markdown("""<style>
.block-container {padding-top:1.4rem;max-width:760px}
.pick {border:1px solid rgba(128,128,128,.28);border-radius:14px;padding:16px;margin:12px 0;background:rgba(128,128,128,.06)}
.kicker {font-size:.78rem;letter-spacing:.06em;opacity:.72;text-transform:uppercase}
.big {font-size:1.35rem;font-weight:700;margin:5px 0}
.detail {font-size:.92rem;opacity:.8;line-height:1.6}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=1800, show_spinner=False)
def get_json(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def events_on(day):
    return get_json(f"{BASE}/scoreboard?dates={day:%Y%m%d}&limit=100").get("events", [])


def summary(event_id):
    return get_json(f"{BASE}/summary?event={event_id}")


def competitors(event):
    return event.get("competitions", [{}])[0].get("competitors", [])


def num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def team_id(side):
    return str(side.get("team", {}).get("id", ""))


def team_name(side):
    return side.get("team", {}).get("displayName", "Unknown")


def completed_history(eastern, days=28):
    results = []
    failures = 0
    for offset in range(0, days + 1):
        try:
            day = eastern - dt.timedelta(days=offset)
            for event in events_on(day):
                if event.get("status", {}).get("type", {}).get("completed"):
                    results.append(event)
        except (requests.RequestException, ValueError, KeyError):
            failures += 1
    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results, failures


def team_history(events):
    history = {}
    for event in events:
        sides = competitors(event)
        if len(sides) != 2:
            continue
        for side in sides:
            other = next((x for x in sides if x is not side), None)
            scored = num(side.get("score"))
            conceded = num(other.get("score")) if other else None
            if scored is None or conceded is None:
                continue
            history.setdefault(team_id(side), []).append((scored, conceded))
    return history


def weighted_mean(values, decay=0.88):
    weights = [decay ** i for i in range(len(values))]
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def game_prediction(event, history):
    sides = competitors(event)
    if len(sides) != 2:
        return None
    home = next((x for x in sides if x.get("homeAway") == "home"), sides[0])
    away = next((x for x in sides if x.get("homeAway") == "away"), sides[1])
    h = history.get(team_id(home), [])[:12]
    a = history.get(team_id(away), [])[:12]
    if min(len(h), len(a)) < 6:
        return None
    hd = weighted_mean([s - c for s, c in h])
    ad = weighted_mean([s - c for s, c in a])
    margin = 2.0 + 0.55 * (hd - ad)
    p_home = 1 / (1 + math.exp(-max(-25, min(25, margin)) / 11.5))
    winner = team_name(home) if p_home >= 0.5 else team_name(away)
    total = (weighted_mean([x[0] for x in h]) + weighted_mean([x[1] for x in a]) +
             weighted_mean([x[0] for x in a]) + weighted_mean([x[1] for x in h])) / 2
    return {"matchup": f"{team_name(away)} @ {team_name(home)}", "winner": winner,
            "confidence": round(100 * max(p_home, 1 - p_home), 1),
            "total": round(total, 1), "margin": round(margin, 1),
            "sample": f"{len(h)}/{len(a)}", "id": event.get("id")}


def player_boxscores(event_id):
    data = summary(event_id)
    rows = []
    for team in data.get("boxscore", {}).get("players", []):
        name = team.get("team", {}).get("displayName", "")
        for group in team.get("statistics", []):
            labels = group.get("labels", [])
            for athlete in group.get("athletes", []):
                if athlete.get("didNotPlay", False):
                    continue
                stats = dict(zip(labels, athlete.get("stats", [])))
                minutes = num(str(stats.get("MIN", "0")).split(":")[0], 0)
                player = athlete.get("athlete", {})
                row = {"id": str(player.get("id", "")), "name": player.get("displayName", ""),
                       "team": name, "minutes": minutes}
                for stat in ("PTS", "REB", "AST"):
                    row[stat] = num(stats.get(stat))
                if row["id"] and minutes >= 8 and all(row[s] is not None for s in ("PTS", "REB", "AST")):
                    rows.append(row)
    return rows


def player_projections(events, upcoming, max_games=85):
    active = {team_name(side) for event in upcoming for side in competitors(event)}
    history = {}
    failures = 0
    for event in events[:max_games]:
        try:
            for row in player_boxscores(event["id"]):
                if row["team"] in active:
                    history.setdefault(row["id"], []).append(row)
        except (requests.RequestException, KeyError, ValueError, TypeError):
            failures += 1
    projections = []
    for rows in history.values():
        if len(rows) < 6:
            continue
        recent = rows[:10]
        # Require at least modest recent court time; this is not an injury check.
        if statistics.mean(r["minutes"] for r in recent) < 15:
            continue
        for stat in ("PTS", "REB", "AST"):
            values = [r[stat] for r in recent]
            projected = weighted_mean(values)
            volatility = statistics.pstdev(values)
            # A stability measure, NOT a probability of beating a betting line.
            stability = 1 / (1 + volatility / max(3.0, projected))
            sample_factor = min(1, len(recent) / 10)
            score = stability * sample_factor
            projections.append({"name": recent[0]["name"], "team": recent[0]["team"],
                                "market": stat, "projection": round(projected, 1),
                                "average": round(statistics.mean(values), 1),
                                "volatility": round(volatility, 1),
                                "games": len(values), "score": score})
    return projections, failures


def card(kicker, title, detail):
    import html
    st.markdown(f'<div class="pick"><div class="kicker">{html.escape(kicker)}</div>'
                f'<div class="big">{html.escape(title)}</div>'
                f'<div class="detail">{html.escape(detail)}</div></div>', unsafe_allow_html=True)


def main():
    st.title("🏀 NBA AI Predictor")
    st.caption("Automatic NBA research · New Zealand time · No manual entries")
    st.warning("Experimental projections only. No TAB odds, injury verification, or validated betting edge. No bets are placed.")
    if st.button("🔄 Refresh data"):
        get_json.clear()
        st.rerun()
    eastern = dt.datetime.now(EAST).date()
    now = dt.datetime.now(dt.timezone.utc)
    upcoming = []
    live_count = 0
    try:
        for day in (eastern, eastern + dt.timedelta(days=1)):
            for event in events_on(day):
                status = event.get("status", {}).get("type", {})
                if status.get("completed"):
                    continue
                if status.get("state") == "in":
                    live_count += 1
                    continue
                # Only games whose scheduled tipoff is in the future.
                tipoff = dt.datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
                if tipoff > now:
                    upcoming.append(event)
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Could not load NBA schedule: {exc}")
        st.stop()
    st.caption(f"Updated {dt.datetime.now(NZ):%d %b %Y, %I:%M %p} NZ · {len(upcoming)} pre-game matchups · {live_count} live games excluded")
    if not upcoming:
        st.info("No upcoming pre-game matchups in the current two-day NBA window. Check again later.")
        return
    with st.spinner("Analysing recent NBA results..."):
        events, schedule_failures = completed_history(eastern)
    history = team_history(events)
    games = [result for event in upcoming if (result := game_prediction(event, history))]
    st.subheader("🏆 Top 5 game predictions")
    if games:
        for i, g in enumerate(sorted(games, key=lambda x: x["confidence"], reverse=True)[:5], 1):
            card(f"#{i} · {g['matchup']}", g["winner"],
                 f"Model estimate: {g['confidence']}% · Projected total: {g['total']} · Recent games: {g['sample']} (home/away)")
        st.caption("Percentages are uncalibrated model estimates, not proven win probabilities.")
    else:
        st.info("Not enough recent team data for reliable baseline projections.")
    st.subheader("⭐ Top 5 player projections")
    st.caption("Ranked by recent statistical consistency, not by betting value. Different stat types are not directly comparable.")
    with st.spinner("Analysing recent player performances..."):
        players, box_failures = player_projections(events, upcoming)
    if players:
        # One entry per player to avoid five cards from the same athlete.
        best_by_player = {}
        for p in players:
            key = (p["name"], p["team"])
            if key not in best_by_player or p["score"] > best_by_player[key]["score"]:
                best_by_player[key] = p
        ranked = sorted(best_by_player.values(), key=lambda p: p["score"], reverse=True)[:5]
        for i, p in enumerate(ranked, 1):
            label = {"PTS": "points", "REB": "rebounds", "AST": "assists"}[p["market"]]
            card(f"#{i} · {p['team']} · {label}", f"{p['name']} — {p['projection']} {label}",
                 f"Recent average: {p['average']} · Volatility: {p['volatility']} · Sample: {p['games']} games")
        st.caption("These are descriptive projections, not over/under selections. Player availability is unverified.")
    else:
        st.info("No player projections available. The box-score feed may be temporarily unavailable.")
    if schedule_failures or box_failures:
        st.caption(f"Data limitations: {schedule_failures} schedule requests and {box_failures} box-score requests failed.")
    with st.expander("How the predictions work"):
        st.write("Game predictions use recency-weighted scoring margins and a fixed home-court adjustment. Player projections use up to ten recent box scores. The top-player ranking favours consistency and adequate sample size; it is not a prediction of which bet will win. These simple statistical baselines are not trained AI models or validated for profitability. ESPN endpoints are unofficial and may change. Live bookmaker lines, verified injuries, and out-of-sample evaluation are required before assessing betting value.")

if __name__ == "__main__":
    main()
