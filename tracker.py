"""Record pre-game NBA winner predictions and grade them from ESPN final results.
Existing prediction records are never recalculated or overwritten.
"""
import concurrent.futures
import datetime as dt
import json
import math
import os
import time
from zoneinfo import ZoneInfo

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
NZ = ZoneInfo("Pacific/Auckland")
EAST = ZoneInfo("America/New_York")
DATA_FILE = "prediction_history.json"
HEADERS = {"User-Agent": "Mozilla/5.0 NBAResearchDashboard/1.1"}


def get_events(day):
    url = f"{BASE}/scoreboard?dates={day:%Y%m%d}&limit=100"
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=13)
            response.raise_for_status()
            return response.json().get("events", [])
        except (requests.RequestException, ValueError) as error:
            print(f"Fetch failed {day} (attempt {attempt + 1}): {error}")
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def fetch_days(days):
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        return dict(zip(days, pool.map(get_events, days)))


def sides(event):
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    home = next((x for x in competitors if x.get("homeAway") == "home"), None)
    away = next((x for x in competitors if x.get("homeAway") == "away"), None)
    return home, away


def numeric(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def name(team):
    return team.get("team", {}).get("displayName", "Unknown")


def team_id(team):
    return str(team.get("team", {}).get("id", ""))


def weighted_mean(values, decay=0.88):
    weights = [decay ** i for i in range(len(values))]
    return sum(x * w for x, w in zip(values, weights)) / sum(weights)


def predict(event, team_history):
    home, away = sides(event)
    if not home or not away:
        return None
    home_games = team_history.get(team_id(home), [])[:12]
    away_games = team_history.get(team_id(away), [])[:12]
    if min(len(home_games), len(away_games)) < 6:
        return None
    home_diff = weighted_mean([p - a for p, a in home_games])
    away_diff = weighted_mean([p - a for p, a in away_games])
    margin = 2.0 + 0.55 * (home_diff - away_diff)
    p_home = 1 / (1 + math.exp(-max(-25, min(25, margin)) / 11.5))
    winner = home if p_home >= 0.5 else away
    return {
        "game_id": str(event["id"]),
        "home_team": name(home),
        "away_team": name(away),
        "predicted_winner": name(winner),
        "estimated_probability": round(max(p_home, 1 - p_home), 4),
        "predicted_margin_home": round(margin, 2),
        "actual_winner": None,
        "correct": None,
        "status": "pending",
        "game_time": event.get("date"),
        "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": "recency-weighted-v2",
    }


def grade(history, day_events, now):
    graded = 0
    for events in day_events.values():
        if events is None:
            continue
        for event in events:
            record = history.get(str(event.get("id", "")))
            if not record or record.get("status") == "final":
                continue
            status = event.get("status", {}).get("type", {})
            if not status.get("completed"):
                continue
            home, away = sides(event)
            if not home or not away:
                continue
            h_score, a_score = numeric(home.get("score")), numeric(away.get("score"))
            if h_score is None or a_score is None or h_score == a_score:
                continue
            actual = name(home if h_score > a_score else away)
            record.update({
                "actual_winner": actual,
                "home_score": h_score,
                "away_score": a_score,
                "correct": record.get("predicted_winner") == actual,
                "status": "final",
                "checked_at": now.isoformat(),
            })
            graded += 1
    return graded


def build_team_history(day_events):
    result = []
    for events in day_events.values():
        if events:
            result.extend(e for e in events if e.get("status", {}).get("type", {}).get("completed"))
    result.sort(key=lambda e: e.get("date", ""), reverse=True)
    history = {}
    for event in result:
        home, away = sides(event)
        if not home or not away:
            continue
        h_score, a_score = numeric(home.get("score")), numeric(away.get("score"))
        if h_score is None or a_score is None:
            continue
        history.setdefault(team_id(home), []).append((h_score, a_score))
        history.setdefault(team_id(away), []).append((a_score, h_score))
    return history


def main():
    now = dt.datetime.now(dt.timezone.utc)
    eastern = now.astimezone(EAST).date()
    today_nz = now.astimezone(NZ).date()
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = {}
    if not isinstance(history, dict):
        raise ValueError("Prediction history must be a JSON object")

    # Grade recent games plus older still-pending games (recover missed updates).
    result_days = [eastern - dt.timedelta(days=i) for i in range(10)]
    for record in history.values():
        if record.get("status") != "pending":
            continue
        pending_start = parse_date(record.get("game_time"))
        if pending_start is not None:
            pending_eastern = pending_start.astimezone(EAST).date()
            if pending_eastern <= eastern and pending_eastern not in result_days:
                result_days.append(pending_eastern)
    fetched = fetch_days(result_days)
    graded = grade(history, fetched, now)

    # Find games starting today in NZ; fetch adjacent ESPN US dates.
    schedule_days = [eastern - dt.timedelta(days=1), eastern, eastern + dt.timedelta(days=1)]
    extras = [day for day in schedule_days if day not in fetched]
    fetched.update(fetch_days(extras))
    candidates = []
    seen = set()
    for day in schedule_days:
        for event in fetched.get(day) or []:
            game_id = str(event.get("id", ""))
            if game_id in seen or game_id in history:
                continue
            seen.add(game_id)
            if event.get("status", {}).get("type", {}).get("state") != "pre":
                continue
            try:
                start = dt.datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                continue
            if start <= now or start.astimezone(NZ).date() != today_nz:
                continue
            candidates.append(event)

    new_count = 0
    # Cap to 5 tracked games per NZ start date, keeping previous picks unchanged.
    existing_today = sum(
        1 for record in history.values()
        if (lambda date: date is not None and date.astimezone(NZ).date() == today_nz)(
            parse_date(record.get("game_time"))
        )
    )
    if candidates and existing_today < 5:
        # Fetch the previous 28 days only when actual new pregame picks are possible.
        past_days = [eastern - dt.timedelta(days=i) for i in range(29)]
        missing = [day for day in past_days if day not in fetched]
        fetched.update(fetch_days(missing))
        # Avoid creating unreliable picks if scoreboard history is missing.
        if sum(fetched.get(day) is None for day in past_days) <= 3:
            team_history = build_team_history({day: fetched[day] for day in past_days})
            ranked = [p for event in candidates if (p := predict(event, team_history))]
            ranked.sort(key=lambda p: p["estimated_probability"], reverse=True)
            for prediction in ranked[:5 - existing_today]:
                history[prediction["game_id"]] = prediction
                new_count += 1

    temp = DATA_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, sort_keys=True)
    os.replace(temp, DATA_FILE)
    finished = [p for p in history.values() if p.get("status") == "final" and isinstance(p.get("correct"), bool)]
    print(f"Saved: {new_count} | Newly graded: {graded} | Total tracked: {len(history)} | Graded: {len(finished)}")
    if finished:
        print(f"Accuracy (all models): {sum(p['correct'] for p in finished) / len(finished):.1%}")


def parse_date(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    main()
