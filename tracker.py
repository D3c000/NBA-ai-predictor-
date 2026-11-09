
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
NZ = ZoneInfo("Pacific/Auckland")
ET = ZoneInfo("America/New_York")
DATA_FILE = "prediction_history.json"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch(path):
    try:
        response = session.get(BASE + path, timeout=20)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        print("ESPN request failed:", error)
        return None


def scoreboard(day):
    data = fetch(f"/scoreboard?dates={day:%Y%m%d}&limit=100")
    return data.get("events", []) if data else None


def load_history():
    if not os.path.exists(DATA_FILE):
        return {}

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history):
    temporary = DATA_FILE + ".tmp"

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2, sort_keys=True)

    os.replace(temporary, DATA_FILE)


def teams(event):
    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])

    home = next(
        (team for team in competitors if team.get("homeAway") == "home"),
        None,
    )
    away = next(
        (team for team in competitors if team.get("homeAway") == "away"),
        None,
    )

    return home, away


def score(team):
    try:
        return float(team["score"])
    except (KeyError, TypeError, ValueError):
        return None


def team_id(team):
    return str(team.get("team", {}).get("id", ""))


def team_name(team):
    return team.get("team", {}).get("displayName", "Unknown")


def build_history(now):
    results = {}

    for days_ago in range(1, 25):
        day = now.astimezone(ET).date() - timedelta(days=days_ago)
        events = scoreboard(day)

        if events is None:
            continue

        for event in events:
            if event.get("status", {}).get("type", {}).get("state") != "post":
                continue

            home, away = teams(event)

            if not home or not away:
                continue

            home_score = score(home)
            away_score = score(away)

            if home_score is None or away_score is None:
                continue

            home_id = team_id(home)
            away_id = team_id(away)

            results.setdefault(home_id, []).append(
                (home_score, away_score)
            )
            results.setdefault(away_id, []).append(
                (away_score, home_score)
            )

    return results


def predict(event, results):
    home, away = teams(event)

    if not home or not away:
        return None

    home_games = results.get(team_id(home), [])[:12]
    away_games = results.get(team_id(away), [])[:12]

    if len(home_games) < 5 or len(away_games) < 5:
        return None

    home_diff = sum(a - b for a, b in home_games) / len(home_games)
    away_diff = sum(a - b for a, b in away_games) / len(away_games)

    margin = 2.0 + 0.55 * (home_diff - away_diff)
    probability_home = 1 / (1 + math.exp(-margin / 11.5))

    winner = home if probability_home >= 0.5 else away
    confidence = max(probability_home, 1 - probability_home)

    return {
        "game_id": str(event["id"]),
        "home_team": team_name(home),
        "away_team": team_name(away),
        "predicted_winner": team_name(winner),
        "estimated_probability": round(confidence, 4),
        "predicted_margin_home": round(margin, 2),
        "actual_winner": None,
        "correct": None,
        "status": "pending",
        "game_time": event.get("date"),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "model": "recent-form-heuristic-v1",
    }


def collect_predictions(history, now):
    results = build_history(now)
    candidates = []

    eastern_day = now.astimezone(ET).date()

    for offset in range(3):
        day = eastern_day + timedelta(days=offset)
        events = scoreboard(day)

        if events is None:
            continue

        for event in events:
            event_id = str(event.get("id", ""))

            if event_id in history:
                continue

            state = event.get("status", {}).get("type", {}).get("state")

            if state != "pre":
                continue

            try:
                game_time = datetime.fromisoformat(
                    event["date"].replace("Z", "+00:00")
                )
            except (KeyError, ValueError):
                continue

            if game_time <= now:
                continue

            prediction = predict(event, results)

            if prediction:
                candidates.append(prediction)

    # Select the five highest estimated-confidence games per NZ day.
    by_day = {}

    for prediction in candidates:
        game_time = datetime.fromisoformat(prediction["game_time"])
        nz_day = game_time.astimezone(NZ).date().isoformat()
        by_day.setdefault(nz_day, []).append(prediction)

    count = 0

    for day, predictions in by_day.items():
        predictions.sort(
            key=lambda p: p["estimated_probability"],
            reverse=True,
        )

        for prediction in predictions[:5]:
            history[prediction["game_id"]] = prediction
            count += 1
            print(
                "Saved:",
                day,
                prediction["predicted_winner"],
                prediction["estimated_probability"],
            )

    return count


def check_results(history, now):
    updated = 0
    eastern_day = now.astimezone(ET).date()

    for offset in range(-7, 1):
        day = eastern_day + timedelta(days=offset)
        events = scoreboard(day)

        if events is None:
            continue

        for event in events:
            event_id = str(event.get("id", ""))

            if event_id not in history:
                continue

            prediction = history[event_id]

            if prediction.get("status") == "final":
                continue

            state = event.get("status", {}).get("type", {}).get("state")

            if state != "post":
                continue

            home, away = teams(event)

            if not home or not away:
                continue

            home_score = score(home)
            away_score = score(away)

            if home_score is None or away_score is None:
                continue

            if home_score == away_score:
                continue

            winner = home if home_score > away_score else away
            actual_winner = team_name(winner)

            prediction["actual_winner"] = actual_winner
            prediction["home_score"] = home_score
            prediction["away_score"] = away_score
            prediction["correct"] = (
                prediction["predicted_winner"] == actual_winner
            )
            prediction["status"] = "final"
            prediction["checked_at"] = now.isoformat()

            updated += 1
            print("Checked:", actual_winner, prediction["correct"])

    return updated


def main():
    now = datetime.now(timezone.utc)
    history = load_history()

    print("NBA tracker:", now.astimezone(NZ).isoformat())

    # Grade saved predictions before collecting new ones.
    checked = check_results(history, now)
    added = collect_predictions(history, now)

    save_history(history)

    completed = [
        prediction
        for prediction in history.values()
        if prediction.get("status") == "final"
    ]

    correct = sum(bool(p["correct"]) for p in completed)
    total = len(completed)

    print("New predictions:", added)
    print("Newly checked:", checked)
    print("Total graded:", total)
    print(
        "Game winner accuracy:",
        f"{100 * correct / total:.1f}%" if total else "Not enough data",
    )
    print("Saved:", DATA_FILE)


if __name__ == "__main__":
    main()
