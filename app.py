import datetime as dt
import html
import math
import statistics
from zoneinfo import ZoneInfo

import requests
import streamlit as st

st.set_page_config(page_title="NBA AI Predictor", page_icon="🏀", layout="centered")
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HISTORY_URL = "https://raw.githubusercontent.com/D3c000/NBA-ai-predictor-/main/prediction_history.json"
HEADERS = {"User-Agent": "Mozilla/5.0 NBAResearchDashboard/1.1"}
NZ = ZoneInfo("Pacific/Auckland")
EAST = ZoneInfo("America/New_York")
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

st.markdown("""<style>
[data-testid="stSidebar"] {min-width: 210px}
[data-testid="stSidebarNav"] {padding-top: 0.5rem}
.block-container h1 {font-size: 2rem}

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



@st.cache_data(ttl=20, show_spinner=False)
def live_events_on(day):
    response = requests.get(
        f"{BASE}/scoreboard?dates={day:%Y%m%d}&limit=100",
        headers=HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    return response.json().get("events", [])


def today_scoreboard(now):
    nz_today = now.astimezone(NZ).date()
    eastern = now.astimezone(EAST).date()
    games = []
    seen = set()
    for day in (eastern - dt.timedelta(days=1), eastern, eastern + dt.timedelta(days=1)):
        for event in live_events_on(day):
            game_id = str(event.get("id", ""))
            if game_id in seen:
                continue
            seen.add(game_id)
            try:
                tipoff = dt.datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if tipoff.astimezone(NZ).date() == nz_today:
                games.append((tipoff, event))
    return sorted(games, key=lambda entry: entry[0])


@st.fragment(run_every="30s")
def show_live_coverage():
    st.subheader("🔴 NBA live coverage — today in NZ")
    st.caption("Live scores, game clock and final results · Refreshes approximately every 30 seconds while this page is open · ESPN may lag")
    try:
        games = today_scoreboard(dt.datetime.now(dt.timezone.utc))
    except (requests.RequestException, ValueError) as exc:
        st.info(f"Live scores temporarily unavailable: {exc}")
        return
    if not games:
        st.info("No NBA games scheduled to start today in New Zealand.")
        return
    for tipoff, event in games:
        sides = competitors(event)
        away = next((x for x in sides if x.get("homeAway") == "away"), None)
        home = next((x for x in sides if x.get("homeAway") == "home"), None)
        if not home or not away:
            continue
        state = event.get("status", {}).get("type", {}).get("state", "pre")
        status = event.get("status", {})
        if state == "in":
            period = status.get("period")
            clock = status.get("displayClock") or ""
            period_label = f"Q{period}" if isinstance(period, int) and period <= 4 else f"Period {period}" if period else "Live"
            label = f"🔴 LIVE · {period_label} {clock}".strip()
        elif state == "post":
            label = "✅ FINAL"
        else:
            label = f"🕒 Scheduled {tipoff.astimezone(NZ):%I:%M %p} NZ"
        a_score = away.get("score", "—")
        h_score = home.get("score", "—")
        title = (f"{team_name(away)} {a_score} — {h_score} {team_name(home)}"
                 if state in ("in", "post") else f"{team_name(away)} @ {team_name(home)}")
        card(label, title, f"Tipoff {tipoff.astimezone(NZ):%I:%M %p} NZ")
    st.caption(f"Scoreboard checked at {dt.datetime.now(NZ):%I:%M:%S %p} NZ")

@st.cache_data(ttl=60, show_spinner=False)
def get_tracker_history():
    response = requests.get(HISTORY_URL, headers=HEADERS, timeout=12)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_nba_odds(api_key):
    # One AU region + one moneyline market costs one credit per successful call.
    # The two-hour cache helps conserve a free-plan allowance.
    try:
        response = requests.get(
            ODDS_URL,
            params={"apiKey": api_key, "regions": "au", "markets": "h2h",
                    "oddsFormat": "decimal", "dateFormat": "iso"},
            timeout=15,
        )
    except requests.RequestException:
        return None, None, "Could not connect to the odds provider."
    if response.status_code != 200:
        # Never display response URLs or bodies: they may contain the secret key.
        if response.status_code in (401, 403):
            problem = "API key not accepted, or your plan does not allow this request."
        elif response.status_code == 429:
            problem = "Odds API request allowance exceeded."
        else:
            problem = f"Odds API returned HTTP {response.status_code}."
        return None, None, problem
    try:
        payload = response.json()
    except ValueError:
        return None, None, "Odds provider returned invalid data."
    if not isinstance(payload, list):
        return None, None, "Odds provider response was not a game list."
    return payload, response.headers.get("x-requests-remaining"), None


def team_key(value):
    # These names are used by ESPN and odds feeds for the same NBA franchise.
    cleaned = "".join(c.lower() for c in str(value) if c.isalnum())
    alias = {
        "laclippers": "losangelesclippers",
        "nyknicks": "newyorkknicks",
        "brooklynnets": "brooklynnets",
        "goldenstatewarriors": "goldenstatewarriors",
    }
    return alias.get(cleaned, cleaned)


def parse_utc(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def show_odds_comparison(upcoming, predictions):
    st.subheader("💰 Today's NBA bookmaker odds")
    st.caption("Automatic Australian-region bookmaker moneyline quotes (not verified TAB NZ odds). "
               "Results are comparison signals, not proven betting value.")
    try:
        api_key = st.secrets.get("ODDS_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        st.info("Odds are not connected yet. Add ODDS_API_KEY to your Streamlit Cloud Secrets settings.")
        return
    if not upcoming:
        st.info("No more pre-game NBA matches starting today in New Zealand.")
        return

    # Do not incur API charges for a day with no model predictions.
    if not predictions:
        st.info("No predictions to compare with bookmaker quotes today.")
        return

    odds, remaining, error = fetch_nba_odds(api_key)
    if error:
        st.info(error)
        return
    if remaining is not None:
        st.caption(f"Odds API credits remaining (provider response): {remaining}")

    prediction_by_id = {str(p['id']): p for p in predictions}
    comparisons = []
    now = dt.datetime.now(dt.timezone.utc)
    for event in upcoming:
        prediction = prediction_by_id.get(str(event.get("id", "")))
        if not prediction:
            continue
        sides = competitors(event)
        home = next((s for s in sides if s.get("homeAway") == "home"), None)
        away = next((s for s in sides if s.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        tipoff = parse_utc(event.get("date"))
        if not tipoff:
            continue
        matching = [o for o in odds if
                    team_key(o.get("home_team", "")) == team_key(team_name(home)) and
                    team_key(o.get("away_team", "")) == team_key(team_name(away)) and
                    (parse_utc(o.get("commence_time")) is not None) and
                    abs((parse_utc(o.get("commence_time")) - tipoff).total_seconds()) <= 7200]
        if not matching:
            continue
        model_team = team_key(prediction["winner"])
        model_probability = prediction["confidence"] / 100
        for odd_game in matching:
            for book in odd_game.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    updated = parse_utc(market.get("last_update"))
                    if updated is None or updated > now + dt.timedelta(minutes=5):
                        continue
                    age_minutes = (now - updated).total_seconds() / 60
                    if age_minutes > 60:
                        continue  # Never flag comparisons against stale prices.
                    for outcome in market.get("outcomes", []):
                        if team_key(outcome.get("name", "")) != model_team:
                            continue
                        price = num(outcome.get("price"))
                        if price is None or price <= 1:
                            continue
                        implied = 1 / price
                        comparisons.append({
                            "matchup": prediction["matchup"],
                            "team": prediction["winner"],
                            "book": book.get("title", book.get("key", "Bookmaker")),
                            "price": price,
                            "model": model_probability,
                            "implied": implied,
                            "difference": model_probability - implied,
                            "updated": updated,
                            "start": tipoff,
                        })

    if not comparisons:
        st.info("No recent, matching pre-game moneyline odds available for today's model picks. "
                "This can happen when a bookmaker hasn't listed a market or the feed is stale.")
        return
    # Take the most favourable recent quoted decimal price for each game.
    best = {}
    for row in comparisons:
        if row['matchup'] not in best or row['price'] > best[row['matchup']]['price']:
            best[row['matchup']] = row
    for i, row in enumerate(sorted(best.values(), key=lambda r: r['difference'], reverse=True)[:5], 1):
        diff_pp = 100 * row['difference']
        stamp = row['updated'].astimezone(NZ).strftime('%I:%M %p')
        card(f"#{i} · {row['matchup']}",
             f"{row['team']} · {row['price']:.2f} decimal odds",
             f"Bookmaker: {row['book']} · Model: {100*row['model']:.1f}% · "
             f"Break-even: {100*row['implied']:.1f}% · Raw difference: {diff_pp:+.1f} percentage points · "
             f"Odds updated {stamp} NZ")
    st.caption("Positive differences do NOT mean a proven edge: this model's probabilities are uncalibrated. "
               "Prices may change or be unavailable at the bookmaker. No bets are placed. "
               "Quotes refresh at most once every two hours per active Streamlit cache; older-than-60-minute quotes are excluded.")


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
    for offset in range(days + 1):
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
        if statistics.mean(r["minutes"] for r in recent) < 15:
            continue
        for stat in ("PTS", "REB", "AST"):
            values = [r[stat] for r in recent]
            projected = weighted_mean(values)
            volatility = statistics.pstdev(values)
            stability = 1 / (1 + volatility / max(3.0, projected))
            score = stability * min(1, len(recent) / 10)
            projections.append({"name": recent[0]["name"], "team": recent[0]["team"],
                                "market": stat, "projection": round(projected, 1),
                                "average": round(statistics.mean(values), 1),
                                "volatility": round(volatility, 1),
                                "games": len(values), "score": score})
    return projections, failures


def card(kicker, title, detail):
    st.markdown(f'<div class="pick"><div class="kicker">{html.escape(str(kicker))}</div>'
                f'<div class="big">{html.escape(str(title))}</div>'
                f'<div class="detail">{html.escape(str(detail))}</div></div>', unsafe_allow_html=True)


def show_tracker_history():
    st.subheader("📊 Tracked prediction results")
    st.caption("Saved automatically by GitHub Actions. Game-winner predictions only.")
    try:
        data = get_tracker_history()
        if not isinstance(data, dict):
            raise ValueError("Unexpected prediction history format")
    except (requests.RequestException, ValueError) as exc:
        st.info("Prediction history is not available yet. Verify prediction_history.json exists in GitHub, then refresh.")
        with st.expander("History connection details"):
            st.code(str(exc))
        return

    rows = [v for v in data.values() if isinstance(v, dict)]
    finished = [r for r in rows if r.get("status") == "final" and isinstance(r.get("correct"), bool)]
    pending = [r for r in rows if r.get("status") == "pending"]
    wins = sum(r["correct"] for r in finished)

    left, middle, right = st.columns(3)
    left.metric("Saved", len(rows))
    middle.metric("Graded", len(finished))
    right.metric("Pending", len(pending))

    if finished:
        st.metric("Winner accuracy", f"{100 * wins / len(finished):.1f}%", help="Correct predictions divided by graded predictions only")
        st.caption(f"{wins} correct out of {len(finished)} graded predictions. Pending games are excluded.")
    else:
        st.info("No completed predictions have been graded yet. Accuracy will appear after scheduled games finish and the tracker runs again.")

    with st.expander("See saved predictions and results"):
        ordered = sorted(rows, key=lambda r: r.get("game_time") or "", reverse=True)
        for r in ordered:
            status = r.get("status", "unknown")
            result = "✅ Correct" if r.get("correct") is True else "❌ Incorrect" if r.get("correct") is False else "⏳ Pending"
            matchup = f"{r.get('away_team', '?')} @ {r.get('home_team', '?')}"
            probability = num(r.get("estimated_probability"))
            confidence = f" · model estimate {probability * 100:.1f}%" if probability is not None else ""
            actual = f" · Actual: {r['actual_winner']}" if status == "final" and r.get("actual_winner") else ""
            card(matchup, f"{result} · {r.get('predicted_winner', 'Unknown')}",
                 f"Predicted winner{confidence}{actual}")

    st.caption("Historical predictions are preserved. Original records marked recent-form-heuristic-v1 used a different formula; new records marked recency-weighted-v2 use the dashboard’s team winner calculation. Each record is graded using the version that generated it. Estimated probabilities are not calibrated.")




def todays_upcoming():
    now = dt.datetime.now(dt.timezone.utc)
    eastern = now.astimezone(EAST).date()
    nz_day = now.astimezone(NZ).date()
    matches = []
    seen = set()
    for day in (eastern - dt.timedelta(days=1), eastern, eastern + dt.timedelta(days=1)):
        for event in events_on(day):
            event_id = str(event.get("id", ""))
            if event_id in seen:
                continue
            seen.add(event_id)
            tipoff = parse_utc(event.get("date"))
            state = event.get("status", {}).get("type", {}).get("state")
            if tipoff and tipoff.astimezone(NZ).date() == nz_day and tipoff > now and state == "pre":
                matches.append(event)
    return sorted(matches, key=lambda e: e.get("date", ""))


@st.cache_data(ttl=1800, show_spinner=False)
def todays_prediction_data(day_string):
    # Data and projections reused across views; player summaries fetched only on Predictions.
    eastern = dt.datetime.now(EAST).date()
    historic, failures = completed_history(eastern)
    return historic, team_history(historic), failures


def today_games():
    upcoming = todays_upcoming()
    if not upcoming:
        return [], []
    _, teams, _ = todays_prediction_data(str(dt.datetime.now(NZ).date()))
    predictions = [p for e in upcoming if (p := game_prediction(e, teams))]
    predictions.sort(key=lambda p: p["confidence"], reverse=True)
    return upcoming, predictions


def daily_header():
    st.caption(f"🇳🇿 {dt.datetime.now(NZ):%A %d %B %Y} · New Zealand time · Automatic data")


def page_home():
    st.title("🏀 NBA AI Predictor")
    daily_header()
    st.markdown("### Today's NBA overview")
    try:
        fixtures = today_scoreboard(dt.datetime.now(dt.timezone.utc))
        upcoming, predictions = today_games()
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Could not load today's NBA data: {exc}")
        return
    live = sum(e.get('status', {}).get('type', {}).get('state') == 'in' for _, e in fixtures)
    a, b, c = st.columns(3)
    a.metric("Today", len(fixtures))
    b.metric("Live", live)
    c.metric("Upcoming", len(upcoming))
    if predictions:
        st.markdown("### 🏆 Featured game prediction")
        p = predictions[0]
        card(p['matchup'], p['winner'], f"Uncalibrated model estimate: {p['confidence']}% · Recent samples: {p['sample']}")
    else:
        st.info("No eligible pre-game predictions remain for today in New Zealand.")
    st.markdown("### Quick status")
    try:
        records = get_tracker_history()
        rows = [r for r in records.values() if isinstance(r, dict)] if isinstance(records, dict) else []
        graded = [r for r in rows if r.get('status') == 'final' and isinstance(r.get('correct'), bool)]
        if graded:
            st.metric("Tracker winner accuracy", f"{100 * sum(r['correct'] for r in graded) / len(graded):.1f}%", help=f"Based on {len(graded)} graded games; tracker model versions may differ from live predictions")
        else:
            st.caption(f"{len(rows)} saved tracker predictions · None graded yet")
    except (requests.RequestException, ValueError):
        st.caption("Tracker history temporarily unavailable")
    st.caption("Select a page using the menu above. Live scores refresh on the Live page.")


def page_predictions():
    st.title("🏆 Today's predictions")
    daily_header()
    try:
        upcoming, games = today_games()
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"NBA data unavailable: {exc}")
        return
    if not upcoming:
        st.info("No more NBA games scheduled to start today in NZ. Tomorrow's matches appear tomorrow.")
        return
    st.subheader("Top 5 game winners")
    if games:
        for i, p in enumerate(games[:5], 1):
            card(f"#{i} · {p['matchup']}", p['winner'], f"Model estimate {p['confidence']}% · Projected total {p['total']} · Sample (home/away) {p['sample']}")
    else:
        st.info("Insufficient recent team data")
    st.caption("Win estimates are not calibrated or guaranteed.")
    st.subheader("Top 5 player projections")
    with st.spinner("Reading recent player box scores..."):
        historic, _, failures = todays_prediction_data(str(dt.datetime.now(NZ).date()))
        players, box_failures = player_projections(historic, upcoming)
    per_player = {}
    for p in players:
        key = (p['name'], p['team'])
        if key not in per_player or p['score'] > per_player[key]['score']:
            per_player[key] = p
    for i, p in enumerate(sorted(per_player.values(), key=lambda x: x['score'], reverse=True)[:5], 1):
        label = {'PTS': 'points', 'REB': 'rebounds', 'AST': 'assists'}[p['market']]
        card(f"#{i} · {p['team']} · {label}", f"{p['name']} — {p['projection']} {label}", f"Average {p['average']} · Volatility {p['volatility']} · {p['games']} games")
    if not per_player:
        st.info("Player projections unavailable for today's games")
    if failures or box_failures:
        st.caption(f"Feed failures: {failures} schedule, {box_failures} player box score")
    st.caption("Player availability is not verified; rankings describe consistency, not betting value.")


def page_live():
    st.title("🔴 Live NBA")
    daily_header()
    show_live_coverage()


def page_odds():
    st.title("💰 Odds scanner")
    daily_header()
    try:
        upcoming, predictions = today_games()
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Could not load predictions: {exc}")
        return
    show_odds_comparison(upcoming, predictions)
    st.caption("Uses Australian-region bookmakers from The Odds API; not verified TAB NZ prices. No bets are placed.")


def page_performance():
    st.title("📊 Performance")
    daily_header()
    show_tracker_history()


def main():
    pages = {
        "🏠 Home": page_home,
        "🏆 Predictions": page_predictions,
        "🔴 Live": page_live,
        "💰 Odds": page_odds,
        "📊 Performance": page_performance,
    }
    with st.sidebar:
        st.title("🏀 NBA 2.0")
        st.caption("Five views · NZ date")
        selected = st.radio("Choose page", list(pages), label_visibility="collapsed")
        if st.button("🔄 Refresh data", use_container_width=True):
            get_json.clear()
            live_events_on.clear()
            get_tracker_history.clear()
            todays_prediction_data.clear()
            st.rerun()
        st.caption("Odds cached up to two hours to conserve API credits")
    st.caption(f"Viewing: {selected.removeprefix('🏠 ').removeprefix('🏆 ').removeprefix('🔴 ').removeprefix('💰 ').removeprefix('📊 ')} · Menu ☰ to switch pages")
    pages[selected]()
    with st.expander("ℹ️ About model limitations"):
        st.write("Statistics are heuristic, not a trained or validated AI model. Prediction probabilities are uncalibrated. Player injuries and starting lineups are not verified. Model versions used by the historical tracker may differ from the current dashboard. The odds display is informational, not a tested betting advantage. ESPN coverage and sportsbook quotes may be delayed.")


if __name__ == "__main__":
    main()
