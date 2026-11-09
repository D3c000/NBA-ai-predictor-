import datetime as dt
import math
import statistics
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='NBA AI Predictor', page_icon='🏀', layout='wide')
BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
HEADERS = {'User-Agent': 'Mozilla/5.0 NBAResearchDashboard/1.0'}
TZ = ZoneInfo('Pacific/Auckland')

@st.cache_data(ttl=1800, show_spinner=False)
def get_json(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def events_on(day):
    return get_json(f'{BASE}/scoreboard?dates={day:%Y%m%d}&limit=100').get('events', [])


def summary(event_id):
    return get_json(f'{BASE}/summary?event={event_id}')


def competitors(event):
    return event.get('competitions', [{}])[0].get('competitors', [])


def num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def team_id(team):
    return str(team.get('team', {}).get('id', ''))


def team_name(team):
    return team.get('team', {}).get('displayName', 'Unknown')


def recent_games(today, days=24):
    results = []
    for offset in range(1, days + 1):
        day = today - dt.timedelta(days=offset)
        try:
            for event in events_on(day):
                if event.get('status', {}).get('type', {}).get('completed'):
                    sides = competitors(event)
                    if len(sides) == 2:
                        results.append(event)
        except requests.RequestException:
            continue
    return results


def team_history(events):
    history = {}
    for event in events:
        sides = competitors(event)
        if len(sides) != 2:
            continue
        for side in sides:
            other = next((x for x in sides if x is not side), None)
            scored, conceded = num(side.get('score')), num(other.get('score')) if other else None
            if scored is None or conceded is None:
                continue
            history.setdefault(team_id(side), []).append((scored, conceded, int(scored > conceded)))
    return history


def game_prediction(event, history):
    sides = competitors(event)
    if len(sides) != 2:
        return None
    home = next((x for x in sides if x.get('homeAway') == 'home'), sides[0])
    away = next((x for x in sides if x.get('homeAway') == 'away'), sides[1])
    h = history.get(team_id(home), [])[:12]
    a = history.get(team_id(away), [])[:12]
    if len(h) < 5 or len(a) < 5:
        return None
    # Simple, transparent baseline: recent point differential and home court.
    hd = statistics.mean(x[0] - x[1] for x in h)
    ad = statistics.mean(x[0] - x[1] for x in a)
    margin = 2.0 + 0.55 * (hd - ad)
    p_home = 1 / (1 + math.exp(-max(-25, min(25, margin)) / 11.5))
    home_ppg = statistics.mean(x[0] for x in h)
    away_ppg = statistics.mean(x[0] for x in a)
    home_allowed = statistics.mean(x[1] for x in h)
    away_allowed = statistics.mean(x[1] for x in a)
    total = (home_ppg + away_allowed + away_ppg + home_allowed) / 2
    winner = team_name(home) if p_home >= .5 else team_name(away)
    return {'Matchup': f'{team_name(away)} @ {team_name(home)}', 'Predicted winner': winner,
            'Win probability': round(max(p_home, 1-p_home)*100, 1),
            'Projected total': round(total, 1), 'Projected home margin': round(margin, 1),
            'Sample (home/away)': f'{len(h)}/{len(a)}', 'event_id': event.get('id')}


def player_boxscores(event_id):
    data = summary(event_id)
    rows = []
    for team in data.get('boxscore', {}).get('players', []):
        team_label = team.get('team', {}).get('displayName', '')
        for group in team.get('statistics', []):
            labels = group.get('labels', [])
            for athlete in group.get('athletes', []):
                if not athlete.get('didNotPlay', False):
                    vals = athlete.get('stats', [])
                    stats = dict(zip(labels, vals))
                    # ESPN labels generally include MIN, PTS, REB, AST.
                    minutes = str(stats.get('MIN', '0')).split(':')[0]
                    player = athlete.get('athlete', {})
                    row = {'id': str(player.get('id', '')), 'Player': player.get('displayName', ''),
                           'Team': team_label, 'MIN': num(minutes, 0)}
                    for stat in ('PTS', 'REB', 'AST'):
                        row[stat] = num(stats.get(stat))
                    if row['id'] and row['MIN'] >= 8 and all(row[s] is not None for s in ('PTS','REB','AST')):
                        rows.append(row)
    return rows


def player_projections(events, upcoming, max_games=65):
    active_team_names = {team_name(side) for event in upcoming for side in competitors(event)}
    history = {}
    errors = 0
    for event in events[:max_games]:
        try:
            for row in player_boxscores(event['id']):
                if row['Team'] in active_team_names:
                    history.setdefault(row['id'], []).append(row)
        except (requests.RequestException, KeyError, ValueError):
            errors += 1
    projections = []
    for rows in history.values():
        if len(rows) < 4:
            continue
        latest = rows[0]
        for stat in ('PTS', 'REB', 'AST'):
            values = [r[stat] for r in rows[:10]]
            # Recency-weighted average, descriptive projection only.
            weights = [0.85 ** i for i in range(len(values))]
            projected = sum(v*w for v,w in zip(values, weights)) / sum(weights)
            spread = statistics.pstdev(values) if len(values) > 1 else 0
            projections.append({'Player': latest['Player'], 'Team': latest['Team'],
                                'Market': stat, 'Projection': round(projected, 1),
                                'Recent average': round(statistics.mean(values), 1),
                                'Recent volatility': round(spread, 1), 'Games sampled': len(values)})
    return projections, errors


def main():
    st.title('🏀 NBA AI Predictor')
    st.caption('Automatic daily NBA research • New Zealand time • No manual player entry')
    today = dt.datetime.now(TZ).date()
    st.info('Research projections, not verified betting tips. This version does not retrieve TAB odds or confirm injuries. No wagers are placed.')
    if st.button('🔄 Refresh data'):
        get_json.clear()
        st.rerun()
    # NBA schedule date is US Eastern; show current and next US calendar day to avoid NZ timezone gaps.
    eastern = dt.datetime.now(ZoneInfo('America/New_York')).date()
    upcoming = []
    try:
        for day in (eastern, eastern + dt.timedelta(days=1)):
            upcoming.extend(e for e in events_on(day) if not e.get('status', {}).get('type', {}).get('completed'))
    except requests.RequestException as exc:
        st.error(f'Could not load NBA schedule: {exc}')
        st.stop()
    st.subheader('📅 Upcoming NBA games')
    if not upcoming:
        st.warning('No upcoming games found in the current two-day window.')
        st.stop()
    st.write(f'{len(upcoming)} scheduled/live games found. Data as of {dt.datetime.now(TZ):%d %b %Y %I:%M %p} NZ time.')
    with st.spinner('Collecting recent results (this may take a minute on first load)...'):
        history_events = recent_games(eastern)
    history = team_history(history_events)
    game_rows = [p for event in upcoming if (p := game_prediction(event, history))]
    st.subheader('🏆 Game predictions')
    if game_rows:
        st.dataframe(pd.DataFrame(game_rows).drop(columns=['event_id']), hide_index=True, use_container_width=True)
        st.caption('Win probabilities are heuristic model outputs, not calibrated or independently validated probabilities. Projected totals are not bookmaker lines.')
    else:
        st.warning('Insufficient recent completed-game data to generate game projections.')
    st.subheader('⭐ Automatic player projections')
    st.caption('Projected points, rebounds and assists for players seen in recent games on scheduled teams. Not over/under picks without current lines.')
    with st.spinner('Loading recent player box scores...'):
        projections, errors = player_projections(history_events, upcoming)
    if projections:
        df = pd.DataFrame(projections)
        st.dataframe(df.sort_values(['Market','Projection'], ascending=[True, False]),
                     hide_index=True, use_container_width=True)
        st.caption('Player availability and lineup status are not verified. Projections are weighted recent averages, not a trained AI model.')
    else:
        st.warning('No reliable player box scores returned. ESPN may be unavailable or its response format may have changed.')
    if errors:
        st.caption(f'{errors} recent box scores could not be retrieved.')
    st.subheader('📋 Model transparency')
    st.write('Games use recent team point differentials plus a fixed home-court adjustment. Player projections use recent box scores. Neither method has been validated for profitable betting. Before any wager, verify availability, injury reports, TAB lines and prices.')
    st.caption('Public ESPN endpoints are unofficial and may change or rate-limit requests. For a production system, use licensed sports-data and bookmaker feeds, scheduled ingestion, and out-of-sample backtesting.')

if __name__ == '__main__':
    main()
