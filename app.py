"""NBA AI Predictor 2.0 — mobile-first premium dashboard."""
import datetime as dt
import html
import math
import statistics
from zoneinfo import ZoneInfo

import requests
import streamlit as st

st.set_page_config(page_title="NBA AI Predictor 2.0", page_icon="🏀", layout="wide", initial_sidebar_state="collapsed")
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HISTORY_URL = "https://raw.githubusercontent.com/D3c000/NBA-ai-predictor-/main/prediction_history.json"
HEADERS = {"User-Agent": "Mozilla/5.0 NBAResearchDashboard/1.1"}
NZ = ZoneInfo("Pacific/Auckland")
EAST = ZoneInfo("America/New_York")
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

st.markdown('''<style>
:root {color-scheme:dark;--bg:#090f1d;--card:#142037;--border:#304261;--orange:#ff9144;--blue:#5b9dff;--muted:#b2c1d8}
.stApp {background:radial-gradient(ellipse at 95% 0%,#203958 0%,transparent 38%),linear-gradient(160deg,#090f1d,#111c2e);color:#f8fafc}
.block-container {max-width:1040px;padding-top:1.25rem;padding-bottom:4rem}
header[data-testid="stHeader"] {background:transparent}
section[data-testid="stSidebar"] {background:#0c1729;border-right:1px solid #304261}
h1,h2,h3 {color:#fff!important;letter-spacing:-.04em}h1 {font-size:clamp(1.8rem,4vw,2.45rem)!important}
p,.stCaption {line-height:1.55}
[data-testid="stMetric"] {background:linear-gradient(145deg,#1b2c47,#101b2d);padding:16px;border:1px solid var(--border);border-radius:16px;min-height:105px}
[data-testid="stMetricLabel"] {color:#b2c1d8}[data-testid="stMetricValue"] {color:#fff;font-weight:800}
[data-testid="stDataFrame"] {border:1px solid var(--border);border-radius:14px;overflow:hidden}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:18px;border-color:var(--border)}
.stButton>button,.stDownloadButton>button {border:0!important;border-radius:12px!important;min-height:44px;background:linear-gradient(120deg,#ff9b48,#e96920)!important;color:white!important;font-weight:750}
.stButton>button:hover {background:#ffac65!important}
[data-baseweb="tab"] {color:#c6d2e6!important}button[data-baseweb="tab"][aria-selected="true"] {color:#ffab70!important}
.pick {background:linear-gradient(135deg,rgba(29,45,72,.98),rgba(17,28,47,.98));border:1px solid #314665;border-radius:17px;padding:19px;margin:12px 0;box-shadow:0 8px 20px #0002}
.kicker {font-size:.72rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#ffa66b}
.big {font-size:1.22rem;font-weight:850;color:white;margin:8px 0;overflow-wrap:anywhere}
.detail {font-size:.88rem;color:#c1cfe1;line-height:1.65;overflow-wrap:anywhere}
.hero {position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:20px;background:linear-gradient(115deg,#172b4a,#101c30);border:1px solid #385072;border-radius:24px;padding:25px;margin-bottom:21px}
.hero-copy {position:relative;z-index:1;max-width:480px}.eyebrow {display:inline-block;color:#ffb982;background:#ff91441e;border:1px solid #ff914451;border-radius:99px;font-size:.66rem;font-weight:800;letter-spacing:.11em;padding:7px 10px}
.hero h1 {font-size:clamp(2rem,5vw,3.25rem)!important;font-weight:900;line-height:1.07;margin:14px 0}.hero h1 span {color:#ff9a52}.hero p {color:#bccce0;font-size:.92rem;margin-bottom:0}
.hero-art {width:40%;max-width:310px;min-width:180px;flex-shrink:0;filter:drop-shadow(0 20px 20px #0005)}
.feature-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin:15px 0 24px}
.feature {background:linear-gradient(145deg,#1c2e4c,#121d31);border:1px solid #2e4465;padding:15px;border-radius:16px;min-width:0}
.feature .emoji {font-size:1.5rem}.feature strong {display:block;color:white;font-size:.84rem;margin-top:8px}.feature small {display:block;color:#aebfd6;font-size:.72rem;margin-top:3px}
.micro {color:#ffad72;letter-spacing:.11em;text-transform:uppercase;font-size:.73rem;font-weight:800;margin-top:18px}
.nav-note {color:#adbfd8;font-size:.82rem}
@media(max-width:700px) {.block-container {padding:12px 12px 40px}.hero {padding:19px;flex-direction:column;align-items:stretch;border-radius:18px}.hero-art {width:100%;max-width:none;max-height:130px;min-width:0}.feature-grid {grid-template-columns:repeat(2,minmax(0,1fr))}.feature {padding:12px}.pick {padding:15px}.big {font-size:1.1rem}[data-testid="stMetric"] {padding:10px;min-height:90px}}
</style>''', unsafe_allow_html=True)

# Original, self-contained SVG artwork: no external image files or copyrighted logos.
BALL_ART = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 260" role="img" aria-label="Illustrated basketball and court"><defs><linearGradient id="court" x2="1" y2="1"><stop stop-color="#21466f"/><stop offset="1" stop-color="#0b1830"/></linearGradient><radialGradient id="ball" cx=".32" cy=".27" r=".85"><stop stop-color="#ffc174"/><stop offset=".52" stop-color="#f88a32"/><stop offset="1" stop-color="#b84312"/></radialGradient></defs><rect width="440" height="260" rx="20" fill="url(#court)"/><g fill="none" stroke="#47739c" stroke-width="2" opacity=".48"><rect x="20" y="20" width="400" height="220" rx="8"/><circle cx="220" cy="130" r="85"/><path d="M220 20V240M20 75H95V185H20M420 75H345V185H420"/></g><circle cx="277" cy="127" r="95" fill="#ff9144" opacity=".12"/><circle cx="277" cy="127" r="77" fill="url(#ball)" stroke="#22140f" stroke-width="4"/><g fill="none" stroke="#311a11" stroke-width="6" stroke-linecap="round"><path d="M200 127H354M277 50V204M225 71Q300 127 225 182M329 71Q254 127 329 182"/></g><g fill="#ffad63"><circle cx="85" cy="51" r="4"/><circle cx="390" cy="212" r="3"/></g></svg>'''


def hero():
    st.markdown(f'''<section class="hero"><div class="hero-copy"><div class="eyebrow">BASKETBALL INTELLIGENCE PLATFORM</div><h1>NBA AI<br><span>PREDICTOR 2.0</span></h1><p>Daily NBA matchups, player projections, bookmaker comparisons and a transparent performance tracker.</p></div><div class="hero-art">{BALL_ART}</div></section>''', unsafe_allow_html=True)
    st.markdown('''<div class="feature-grid"><div class="feature"><span class="emoji">🏀</span><strong>Games</strong><small>Winner projections</small></div><div class="feature"><span class="emoji">🎯</span><strong>Player props</strong><small>Recent form</small></div><div class="feature"><span class="emoji">📈</span><strong>Odds &amp; value</strong><small>Market comparisons</small></div><div class="feature"><span class="emoji">🏆</span><strong>Performance</strong><small>Saved results</small></div></div>''', unsafe_allow_html=True)


def card(kicker, title, detail):
    esc = lambda x: html.escape(str(x))
    st.markdown(f'<div class="pick"><div class="kicker">{esc(kicker)}</div><div class="big">{esc(title)}</div><div class="detail">{esc(detail)}</div></div>', unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner=False)
def get_json(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=20, show_spinner=False)
def live_events_on(day):
    response = requests.get(f"{BASE}/scoreboard?dates={day:%Y%m%d}&limit=100", headers=HEADERS, timeout=12)
    response.raise_for_status()
    return response.json().get("events", [])


def today_scoreboard(now):
    nz_today = now.astimezone(NZ).date()
    eastern = now.astimezone(EAST).date()
    games, seen = [], set()
    for day in (eastern - dt.timedelta(days=1), eastern, eastern + dt.timedelta(days=1)):
        for event in live_events_on(day):
            game_id = str(event.get("id", ""))
            if game_id in seen:
                continue
            seen.add(game_id)
            tipoff = parse_utc(event.get("date"))
            if tipoff and tipoff.astimezone(NZ).date() == nz_today:
                games.append((tipoff, event))
    return sorted(games, key=lambda entry: entry[0])


@st.fragment(run_every="30s")
def show_live_coverage():
    st.subheader("🔴 NBA live coverage — today in NZ")
    st.caption("Live scores and game clock · Refreshes approximately every 30 seconds while this page is open · ESPN may lag")
    try:
        games = today_scoreboard(dt.datetime.now(dt.timezone.utc))
    except (requests.RequestException, ValueError) as exc:
        st.info(f"Live scores temporarily unavailable: {exc}")
        return
    if not games:
        st.info("No NBA games scheduled to start today in New Zealand.")
    for tipoff, event in games:
        sides = competitors(event)
        away = next((x for x in sides if x.get("homeAway") == "away"), None)
        home = next((x for x in sides if x.get("homeAway") == "home"), None)
        if not home or not away:
            continue
        status = event.get("status", {})
        state = status.get("type", {}).get("state", "pre")
        if state == "in":
            period = status.get("period")
            clock = status.get("displayClock") or ""
            period_label = f"Q{period}" if isinstance(period, int) and period <= 4 else f"Period {period}" if period else "Live"
            label = f"🔴 LIVE · {period_label} {clock}".strip()
        elif state == "post":
            label = "✅ FINAL"
        else:
            label = f"🕒 Scheduled {tipoff.astimezone(NZ):%I:%M %p} NZ"
        a_score, h_score = away.get("score", "—"), home.get("score", "—")
        title = (f"{team_name(away)} {a_score} — {h_score} {team_name(home)}" if state in ("in", "post") else f"{team_name(away)} @ {team_name(home)}")
        card(label, title, f"Tipoff {tipoff.astimezone(NZ):%I:%M %p} NZ")
    st.caption(f"Scoreboard checked at {dt.datetime.now(NZ):%I:%M:%S %p} NZ")


@st.cache_data(ttl=60, show_spinner=False)
def get_tracker_history():
    response = requests.get(HISTORY_URL, headers=HEADERS, timeout=12)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_nba_odds(api_key):
    try:
        response = requests.get(ODDS_URL, params={"apiKey": api_key, "regions": "au", "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso"}, timeout=15)
    except requests.RequestException:
        return None, None, "Could not connect to the odds provider."
    if response.status_code != 200:
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
    cleaned = "".join(c.lower() for c in str(value) if c.isalnum())
    return {"laclippers": "losangelesclippers", "nyknicks": "newyorkknicks"}.get(cleaned, cleaned)


def parse_utc(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(dt.timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def show_odds_comparison(upcoming, predictions):
    st.subheader("💰 Today's NBA bookmaker odds")
    st.caption("Australian-region bookmaker moneyline quotes (not verified TAB NZ odds). Comparison signals, not proven betting value.")
    try:
        api_key = st.secrets.get("ODDS_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        st.info("Odds aren't connected yet. Add ODDS_API_KEY to Streamlit Cloud Secrets.")
        return
    if not upcoming:
        st.info("No more pre-game NBA matches starting today in New Zealand.")
        return
    if not predictions:
        st.info("No predictions to compare with bookmaker quotes today.")
        return
    odds, remaining, error = fetch_nba_odds(api_key)
    if error:
        st.info(error)
        return
    if remaining is not None:
        st.caption(f"Odds API credits remaining: {remaining}")
    by_id = {str(p["id"]): p for p in predictions}
    comparisons = []
    now = dt.datetime.now(dt.timezone.utc)
    for event in upcoming:
        prediction = by_id.get(str(event.get("id", "")))
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
        matching = [o for o in odds if team_key(o.get("home_team", "")) == team_key(team_name(home)) and team_key(o.get("away_team", "")) == team_key(team_name(away)) and parse_utc(o.get("commence_time")) is not None and abs((parse_utc(o["commence_time"]) - tipoff).total_seconds()) <= 7200]
        model_team = team_key(prediction["winner"])
        model_probability = prediction["confidence"] / 100
        for odd_game in matching:
            for book in odd_game.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    updated = parse_utc(market.get("last_update"))
                    if updated is None or updated > now + dt.timedelta(minutes=5) or (now - updated).total_seconds() > 3600:
                        continue
                    for outcome in market.get("outcomes", []):
                        if team_key(outcome.get("name", "")) != model_team:
                            continue
                        price = num(outcome.get("price"))
                        if price is None or price <= 1:
                            continue
                        implied = 1 / price
                        comparisons.append({"matchup": prediction["matchup"], "team": prediction["winner"], "book": book.get("title", book.get("key", "Bookmaker")), "price": price, "model": model_probability, "implied": implied, "difference": model_probability - implied, "updated": updated})
    if not comparisons:
        st.info("No recent matching pre-game moneyline odds for today's model picks. Markets may be unavailable or stale.")
        return
    best = {}
    for row in comparisons:
        if row["matchup"] not in best or row["price"] > best[row["matchup"]]["price"]:
            best[row["matchup"]] = row
    for i, row in enumerate(sorted(best.values(), key=lambda r: r["difference"], reverse=True)[:5], 1):
        card(f"#{i} · {row['matchup']}", f"{row['team']} · {row['price']:.2f} decimal odds", f"Bookmaker: {row['book']} · Model: {100*row['model']:.1f}% · Break-even: {100*row['implied']:.1f}% · Raw difference: {100*row['difference']:+.1f} percentage points · Updated {row['updated'].astimezone(NZ):%I:%M %p} NZ")
    st.caption("Positive differences do not prove an edge: model probabilities are uncalibrated. Quotes may change. No bets are placed. Cached up to two hours; quotes older than 60 minutes excluded.")


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
    results, failures = [], 0
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
            if scored is not None and conceded is not None:
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
    h, a = history.get(team_id(home), [])[:12], history.get(team_id(away), [])[:12]
    if min(len(h), len(a)) < 6:
        return None
    hd = weighted_mean([s-c for s,c in h])
    ad = weighted_mean([s-c for s,c in a])
    margin = 2.0 + 0.55 * (hd-ad)
    p_home = 1 / (1 + math.exp(-max(-25, min(25, margin)) / 11.5))
    winner = team_name(home) if p_home >= .5 else team_name(away)
    total = (weighted_mean([x[0] for x in h]) + weighted_mean([x[1] for x in a]) + weighted_mean([x[0] for x in a]) + weighted_mean([x[1] for x in h])) / 2
    return {"matchup": f"{team_name(away)} @ {team_name(home)}", "winner": winner, "confidence": round(100 * max(p_home, 1-p_home), 1), "total": round(total, 1), "margin": round(margin, 1), "sample": f"{len(h)}/{len(a)}", "id": event.get("id")}


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
                row = {"id": str(player.get("id", "")), "name": player.get("displayName", ""), "team": name, "minutes": minutes}
                for stat in ("PTS", "REB", "AST"):
                    row[stat] = num(stats.get(stat))
                if row["id"] and minutes >= 8 and all(row[s] is not None for s in ("PTS", "REB", "AST")):
                    rows.append(row)
    return rows


def player_projections(events, upcoming, max_games=85):
    active = {team_name(side) for event in upcoming for side in competitors(event)}
    history, failures = {}, 0
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
            stability = 1 / (1 + volatility / max(3, projected))
            score = stability * min(1, len(recent) / 10)
            projections.append({"name": recent[0]["name"], "team": recent[0]["team"], "market": stat, "projection": round(projected, 1), "average": round(statistics.mean(values), 1), "volatility": round(volatility, 1), "games": len(values), "score": score})
    return projections, failures


def show_tracker_history():
    st.subheader("📊 Tracked prediction results")
    st.caption("Saved by GitHub Actions. Game-winner predictions only.")
    try:
        data = get_tracker_history()
        if not isinstance(data, dict):
            raise ValueError("Unexpected prediction history format")
    except (requests.RequestException, ValueError) as exc:
        st.info("Prediction history is not available yet. Check prediction_history.json in GitHub, then refresh.")
        with st.expander("History connection details"):
            st.code(str(exc))
        return
    rows = [v for v in data.values() if isinstance(v, dict)]
    finished = [r for r in rows if r.get("status") == "final" and isinstance(r.get("correct"), bool)]
    pending = [r for r in rows if r.get("status") == "pending"]
    wins = sum(r["correct"] for r in finished)
    a, b, c = st.columns(3)
    a.metric("Saved", len(rows))
    b.metric("Graded", len(finished))
    c.metric("Pending", len(pending))
    if finished:
        st.metric("Winner accuracy", f"{100*wins/len(finished):.1f}%", help="Correct predictions divided by graded predictions only")
        st.caption(f"{wins} correct out of {len(finished)} graded predictions. Pending games excluded.")
    else:
        st.info("No completed predictions graded yet. Accuracy will appear after games finish and the tracker runs.")
    with st.expander("See saved predictions and results"):
        for r in sorted(rows, key=lambda r: r.get("game_time") or "", reverse=True):
            result = "✅ Correct" if r.get("correct") is True else "❌ Incorrect" if r.get("correct") is False else "⏳ Pending"
            matchup = f"{r.get('away_team','?')} @ {r.get('home_team','?')}"
            probability = num(r.get("estimated_probability"))
            confidence = f" · Model estimate {probability*100:.1f}%" if probability is not None else ""
            actual = f" · Actual: {r['actual_winner']}" if r.get("status") == "final" and r.get("actual_winner") else ""
            card(matchup, f"{result} · {r.get('predicted_winner','Unknown')}", f"Predicted winner{confidence}{actual}")
    st.caption("Different historical tracker versions may use different formulas. Probabilities are uncalibrated.")


def todays_upcoming():
    now = dt.datetime.now(dt.timezone.utc)
    eastern, nz_day = now.astimezone(EAST).date(), now.astimezone(NZ).date()
    matches, seen = [], set()
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
    eastern = dt.datetime.now(EAST).date()
    historic, failures = completed_history(eastern)
    return historic, team_history(historic), failures


def today_games():
    upcoming = todays_upcoming()
    if not upcoming:
        return [], []
    _, teams, _ = todays_prediction_data(str(dt.datetime.now(NZ).date()))
    predictions = [p for event in upcoming if (p := game_prediction(event, teams))]
    predictions.sort(key=lambda p: p["confidence"], reverse=True)
    return upcoming, predictions


def daily_header():
    st.caption(f"🇳🇿 {dt.datetime.now(NZ):%A %d %B %Y} · New Zealand time · Automatic data")


def page_home():
    hero()
    daily_header()
    st.markdown('<div class="micro">TODAY AT A GLANCE</div>', unsafe_allow_html=True)
    try:
        fixtures = today_scoreboard(dt.datetime.now(dt.timezone.utc))
        upcoming, predictions = today_games()
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Could not load today's NBA data: {exc}")
        return
    live = sum(e.get("status", {}).get("type", {}).get("state") == "in" for _, e in fixtures)
    a, b, c = st.columns(3)
    a.metric("Today", len(fixtures))
    b.metric("Live", live)
    c.metric("Upcoming", len(upcoming))
    if predictions:
        st.subheader("🏆 Featured game prediction")
        p = predictions[0]
        card(p["matchup"], p["winner"], f"Uncalibrated model estimate: {p['confidence']}% · Recent samples: {p['sample']}")
    else:
        st.info("No eligible pre-game predictions remain for today in New Zealand.")
    st.subheader("Quick status")
    try:
        records = get_tracker_history()
        rows = [r for r in records.values() if isinstance(r, dict)] if isinstance(records, dict) else []
        graded = [r for r in rows if r.get("status") == "final" and isinstance(r.get("correct"), bool)]
        if graded:
            st.metric("Tracker winner accuracy", f"{100*sum(r['correct'] for r in graded)/len(graded):.1f}%", help=f"Based on {len(graded)} graded games; tracker versions may differ")
        else:
            st.caption(f"{len(rows)} saved tracker predictions · None graded yet")
    except (requests.RequestException, ValueError):
        st.caption("Tracker history temporarily unavailable")
    st.caption("Use the menu to explore predictions, live scores, odds and results.")


def page_predictions():
    st.title("🏆 Today's predictions")
    daily_header()
    try:
        upcoming, games = today_games()
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"NBA data unavailable: {exc}")
        return
    if not upcoming:
        st.info("No more games scheduled to start today in NZ. Tomorrow's games appear tomorrow.")
        return
    st.subheader("Top 5 game winners")
    if games:
        for i, p in enumerate(games[:5], 1):
            card(f"#{i} · {p['matchup']}", p["winner"], f"Model estimate {p['confidence']}% · Projected total {p['total']} · Sample (home/away) {p['sample']}")
    else:
        st.info("Insufficient recent team data")
    st.caption("Win estimates are not calibrated or guaranteed.")
    st.subheader("Top 5 player projections")
    with st.spinner("Reading recent player box scores..."):
        historic, _, failures = todays_prediction_data(str(dt.datetime.now(NZ).date()))
        players, box_failures = player_projections(historic, upcoming)
    per_player = {}
    for p in players:
        key = (p["name"], p["team"])
        if key not in per_player or p["score"] > per_player[key]["score"]:
            per_player[key] = p
    for i, p in enumerate(sorted(per_player.values(), key=lambda x: x["score"], reverse=True)[:5], 1):
        label = {"PTS": "points", "REB": "rebounds", "AST": "assists"}[p["market"]]
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
    st.caption("Uses Australian-region bookmakers from The Odds API, not verified TAB NZ prices. No bets are placed.")


def page_performance():
    st.title("📊 Performance")
    daily_header()
    show_tracker_history()


def main():
    pages = {"🏠 Home": page_home, "🏆 Predictions": page_predictions, "🔴 Live": page_live, "💰 Odds": page_odds, "📊 Performance": page_performance}
    with st.sidebar:
        st.markdown("### 🏀 NBA AI 2.0")
        st.caption("SPORTS INTELLIGENCE · NZ TIME")
        selected = st.radio("Choose page", list(pages), label_visibility="collapsed")
        st.divider()
        if st.button("🔄 Refresh data", use_container_width=True):
            get_json.clear()
            live_events_on.clear()
            get_tracker_history.clear()
            todays_prediction_data.clear()
            # Odds are deliberately not cleared to conserve API quota.
            st.rerun()
        st.caption("Odds cache: up to 2 hours to conserve API credits")
    st.caption(f"📍 {selected.split(' ',1)[1]} · Tap ☰ to switch pages")
    pages[selected]()
    with st.expander("ℹ️ About model limitations"):
        st.write("Statistics are heuristic, not a trained or validated AI model. Prediction probabilities are uncalibrated. Player injuries and starting lineups are not verified. Historical tracker versions may differ. Odds comparisons are informational, not a tested betting advantage. ESPN and bookmaker data may be delayed.")


if __name__ == "__main__":
    main()
