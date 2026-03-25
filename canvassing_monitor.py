
import streamlit as st
import streamlit.components.v1 as components
import json
import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Canvassing Monitor", layout="wide")

# ============================================================
# CSS STYLES
# ============================================================
st.markdown("""
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        color: #e8ecf1;
    }
    [data-testid="stSidebar"] { background: #0a0e15; border-right: 1px solid #2d3748; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { background: #0a0e15; }
    .metric-card {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
        border: 1px solid #4a5568; border-radius: 12px; padding: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: all 0.3s ease;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(0,0,0,0.4); border-color: #5a7a9e; }
    .metric-label { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.2px; color: #a0aec0; margin-bottom: 8px; }
    .metric-value { font-size: 32px; font-weight: 700; color: #4f9ef5; font-family: 'Courier New', monospace; }
    .metric-subtitle { font-size: 12px; color: #718096; margin-top: 8px; }
    h1, h2, h3 { color: #fff; }
    h2 { margin-top: 0; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 2px solid #4a5568; font-size: 20px; }
    /* Hide default streamlit expander styling for dark theme */
    .streamlit-expanderHeader { background: #1a202c !important; color: #fff !important; border: 1px solid #4a5568 !important; border-radius: 8px !important; }
    .streamlit-expanderContent { background: #0f1419 !important; border: 1px solid #4a5568 !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data
def load_overview_data():
    """Load canvasser overview data from JSON"""
    data_path = os.path.join(os.path.dirname(__file__), 'overview_data.json')
    try:
        with open(data_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def load_detail_data(list_name):
    """Load individual canvasser detail data if available"""
    safe_name = list_name.replace(' ', '_').replace('/', '_')
    detail_path = os.path.join(os.path.dirname(__file__), 'details', f'{safe_name}.json')
    try:
        with open(detail_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def load_all_detail_files():
    """Load all available detail JSON files"""
    details_dir = os.path.join(os.path.dirname(__file__), 'details')
    if not os.path.exists(details_dir):
        return {}
    all_details = {}
    for fpath in glob.glob(os.path.join(details_dir, '*.json')):
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
                key = data.get('canvasser', os.path.basename(fpath))
                all_details[key] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return all_details

def parse_survey_file(uploaded_file):
    """Parse VAN survey export (handles UTF-16 tab-delimited .xls and UTF-8 .csv)"""
    try:
        # Try UTF-16 tab-delimited first (VAN .xls format)
        content = uploaded_file.read()
        uploaded_file.seek(0)
        try:
            text = content.decode('utf-16')
            df = pd.read_csv(pd.io.common.StringIO(text), sep='\t')
            return df
        except (UnicodeDecodeError, UnicodeError):
            pass
        # Try UTF-8 CSV
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
            return df
        except Exception:
            pass
        # Try UTF-8 tab-delimited
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep='\t')
        return df
    except Exception as e:
        st.sidebar.error(f"Error parsing survey file: {e}")
        return None

def normalize_name(name):
    """Normalize canvasser name for matching. Handles 'First Last' and 'Last, First' formats."""
    if not name or not isinstance(name, str):
        return ""
    name = name.strip().lower()
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2:
            name = f"{parts[1]} {parts[0]}"
    # Remove extra spaces
    name = ' '.join(name.split())
    return name

def match_canvasser_in_survey(canvasser_name, survey_df):
    """Find survey records matching a canvasser name"""
    if survey_df is None or 'CanvassedBy' not in survey_df.columns:
        return None

    norm_target = normalize_name(canvasser_name)
    if not norm_target:
        return None

    # Build normalized lookup
    survey_df = survey_df.copy()
    survey_df['_norm_name'] = survey_df['CanvassedBy'].apply(normalize_name)

    # Exact match
    matches = survey_df[survey_df['_norm_name'] == norm_target]

    # Partial match fallback (last name)
    if matches.empty:
        target_parts = norm_target.split()
        if target_parts:
            last = target_parts[-1]
            matches = survey_df[survey_df['_norm_name'].str.contains(last, na=False)]

    if matches.empty:
        return None
    return matches.drop(columns=['_norm_name'])

# ============================================================
# METRIC CALCULATIONS
# ============================================================

def calculate_metrics(canvasser):
    """Calculate performance metrics from overview data"""
    attempts = canvasser.get('attempts', 0)
    canvassed = canvasser.get('canvassed', 0)
    refused = canvasser.get('refused', 0)
    if attempts == 0:
        return {'contact_rate': 0, 'refused_rate': 0, 'doors': canvasser.get('doors', 0)}
    return {
        'contact_rate': round((canvassed / attempts) * 100, 1),
        'refused_rate': round((refused / attempts) * 100, 1),
        'doors': canvasser.get('doors', 0)
    }

def calculate_time_analysis(detail_data):
    """Analyze active vs idle time from contact timestamps"""
    if not detail_data or 'contacts' not in detail_data:
        return None
    contacts = detail_data['contacts']
    if len(contacts) < 2:
        return None

    timestamps = []
    for c in contacts:
        ts_str = c.get('date_canvassed', '')
        for fmt in ['%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S']:
            try:
                timestamps.append((datetime.strptime(ts_str, fmt), c))
                break
            except ValueError:
                continue

    if len(timestamps) < 2:
        return None

    timestamps.sort(key=lambda x: x[0])

    total_time = (timestamps[-1][0] - timestamps[0][0]).total_seconds() / 60  # minutes
    gaps = []
    idle_periods = []
    active_time = 0

    for i in range(1, len(timestamps)):
        gap_min = (timestamps[i][0] - timestamps[i-1][0]).total_seconds() / 60
        gaps.append(gap_min)
        if gap_min > 15:
            idle_periods.append({
                'start': timestamps[i-1][0].strftime('%I:%M %p'),
                'end': timestamps[i][0].strftime('%I:%M %p'),
                'duration': round(gap_min, 1),
                'after_address': timestamps[i-1][1].get('address', 'Unknown')
            })
        else:
            active_time += gap_min

    idle_time = sum(g for g in gaps if g > 15)
    avg_pace = np.mean([g for g in gaps if g <= 15]) if any(g <= 15 for g in gaps) else 0

    return {
        'start_time': timestamps[0][0].strftime('%I:%M %p'),
        'end_time': timestamps[-1][0].strftime('%I:%M %p'),
        'total_time': round(total_time, 1),
        'active_time': round(active_time, 1),
        'idle_time': round(idle_time, 1),
        'idle_periods': idle_periods,
        'avg_pace': round(avg_pace, 1),
        'contacts_count': len(timestamps)
    }

def detect_fraud(detail_data, survey_matches):
    """Cross-reference scraped contacts vs survey responses by VANID"""
    if detail_data is None or survey_matches is None:
        return None

    contacts = detail_data.get('contacts', [])
    if not contacts:
        return None

    # Get VANIDs from scraped contacts that were actually canvassed (not "Not Home")
    canvassed_vanids = set()
    all_contact_vanids = set()
    for c in contacts:
        vid = str(c.get('vanid', ''))
        if vid:
            all_contact_vanids.add(vid)
            if c.get('contact_result', '').lower() == 'canvassed':
                canvassed_vanids.add(vid)

    # Get VANIDs from survey responses
    survey_vanids = set()
    if 'Voter File VANID' in survey_matches.columns:
        survey_vanids = set(survey_matches['Voter File VANID'].astype(str).unique())

    # Cross-reference
    canvassed_with_survey = canvassed_vanids & survey_vanids
    canvassed_without_survey = canvassed_vanids - survey_vanids
    survey_without_contact = survey_vanids - all_contact_vanids

    verification_rate = 0
    if canvassed_vanids:
        verification_rate = round(len(canvassed_with_survey) / len(canvassed_vanids) * 100, 1)

    return {
        'total_contacts': len(all_contact_vanids),
        'canvassed_contacts': len(canvassed_vanids),
        'survey_responses': len(survey_vanids),
        'verified': len(canvassed_with_survey),
        'canvassed_no_survey': len(canvassed_without_survey),
        'survey_no_contact': len(survey_without_contact),
        'verification_rate': verification_rate,
        'missing_vanids': list(canvassed_without_survey)[:10]  # first 10 for display
    }

def get_status_color(status):
    return 'status-committed' if status == 'C' else 'status-pending'

def get_status_text(status):
    return 'Committed' if status == 'C' else 'Pending'

def compute_attention_status(metrics, time_analysis=None, fraud_info=None):
    """Composite status: returns (needs_attention: bool, reasons: list)"""
    reasons = []
    if metrics['contact_rate'] < 15:
        reasons.append(f"Low contact rate ({metrics['contact_rate']}%)")
    if metrics['refused_rate'] > 10:
        reasons.append(f"High refused rate ({metrics['refused_rate']}%)")
    if time_analysis and len(time_analysis.get('idle_periods', [])) >= 3:
        reasons.append(f"{len(time_analysis['idle_periods'])} idle periods (>15min)")
    if fraud_info and fraud_info.get('verification_rate', 100) < 50 and fraud_info.get('canvassed_contacts', 0) > 0:
        reasons.append(f"Low survey verification ({fraud_info['verification_rate']}%)")
    return (len(reasons) > 0, reasons)

# ============================================================
# RENDERING FUNCTIONS
# ============================================================

def render_performance_card(canvasser, metrics, needs_attn, attn_reasons):
    """Render the top-level performance card"""
    attn_badge = '<span class="alert-badge">NEEDS ATTENTION</span>' if needs_attn else '<span style="display:inline-block;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;text-transform:uppercase;background:rgba(76,175,80,0.15);color:#4caf50;border:1px solid rgba(76,175,80,0.3);">OK</span>'

    reasons_html = ""
    if needs_attn and attn_reasons:
        items = "".join(f'<div style="color:#f44336;font-size:12px;margin:2px 0;">• {r}</div>' for r in attn_reasons)
        reasons_html = f'<div style="margin-top:8px;">{items}</div>'

    card_html = f"""
    <html><head><style>
        body {{ margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:transparent; }}
        .card {{ background:linear-gradient(135deg,#1a202c 0%,#2d3748 100%); border:1px solid #4a5568; border-radius:12px; padding:28px; }}
        .name {{ font-size:22px; font-weight:700; color:#fff; margin-bottom:8px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
        .status-committed {{ display:inline-block; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:600; text-transform:uppercase; background:rgba(76,175,80,0.15); color:#4caf50; border:1px solid rgba(76,175,80,0.3); }}
        .status-pending {{ display:inline-block; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:600; text-transform:uppercase; background:rgba(255,152,0,0.15); color:#ff9800; border:1px solid rgba(255,152,0,0.3); }}
        .alert-badge {{ display:inline-block; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:600; text-transform:uppercase; background:rgba(244,67,54,0.15); color:#f44336; border:1px solid rgba(244,67,54,0.3); }}
        .list {{ font-size:12px; color:#a0aec0; margin-bottom:16px; font-family:'Courier New',monospace; }}
        .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
        .item {{ background:rgba(79,158,245,0.1); border:1px solid rgba(79,158,245,0.2); border-radius:8px; padding:12px; text-align:center; }}
        .val {{ font-size:20px; font-weight:700; color:#4f9ef5; font-family:'Courier New',monospace; }}
        .lbl {{ font-size:11px; color:#a0aec0; text-transform:uppercase; letter-spacing:0.5px; margin-top:4px; }}
    </style></head><body>
    <div class="card">
        <div class="name">
            {canvasser['canvasser']}
            <span class="{get_status_color(canvasser['status'])}">{get_status_text(canvasser['status'])}</span>
            {attn_badge}
        </div>
        <div class="list">{canvasser['listName']}</div>
        {reasons_html}
        <div class="grid">
            <div class="item"><div class="val">{canvasser['attempts']}</div><div class="lbl">Attempts</div></div>
            <div class="item"><div class="val">{metrics['doors']}</div><div class="lbl">Doors</div></div>
            <div class="item"><div class="val">{canvasser['canvassed']}</div><div class="lbl">Canvassed</div></div>
            <div class="item"><div class="val">{metrics['contact_rate']}%</div><div class="lbl">Contact Rate</div></div>
            <div class="item"><div class="val">{canvasser['notHome']}</div><div class="lbl">Not Home</div></div>
            <div class="item"><div class="val">{canvasser['refused']}</div><div class="lbl">Refused</div></div>
            <div class="item"><div class="val">{canvasser['moved']}</div><div class="lbl">Moved</div></div>
            <div class="item"><div class="val">{metrics['refused_rate']}%</div><div class="lbl">Refused Rate</div></div>
        </div>
    </div>
    </body></html>
    """
    height = 240 if not needs_attn else 240 + len(attn_reasons) * 18
    components.html(card_html, height=height)

def render_survey_breakout(survey_matches):
    """Render survey question/response breakdown"""
    if survey_matches is None or survey_matches.empty:
        st.caption("No survey data found for this canvasser. Upload a VAN survey export in the sidebar.")
        return

    if 'SurveyQuestionLongName' not in survey_matches.columns or 'SurveyResponseName' not in survey_matches.columns:
        st.caption("Survey file missing required columns (SurveyQuestionLongName, SurveyResponseName).")
        return

    # Count unique voters surveyed
    if 'Voter File VANID' in survey_matches.columns:
        unique_voters = survey_matches['Voter File VANID'].nunique()
        st.caption(f"**{unique_voters}** voters surveyed  |  **{len(survey_matches)}** total responses")

    # Pivot: questions as rows, responses with counts
    questions = survey_matches['SurveyQuestionLongName'].unique()

    for q in sorted(questions):
        q_data = survey_matches[survey_matches['SurveyQuestionLongName'] == q]
        response_counts = q_data['SurveyResponseName'].value_counts()
        total = response_counts.sum()

        # Build bar chart HTML
        bars_html = ""
        colors = ['#4f9ef5', '#48bb78', '#ed8936', '#fc8181', '#b794f4', '#f6e05e', '#4fd1c5', '#f687b3']
        for idx, (response, count) in enumerate(response_counts.items()):
            pct = round(count / total * 100, 1) if total > 0 else 0
            color = colors[idx % len(colors)]
            bars_html += f'''
            <div style="display:flex;align-items:center;margin:4px 0;gap:8px;">
                <div style="width:140px;font-size:12px;color:#a0aec0;text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{response}">{response}</div>
                <div style="flex:1;background:rgba(255,255,255,0.05);border-radius:4px;height:20px;overflow:hidden;">
                    <div style="width:{pct}%;background:{color};height:100%;border-radius:4px;min-width:2px;"></div>
                </div>
                <div style="width:60px;font-size:12px;color:#e8ecf1;font-family:'Courier New',monospace;">{count} ({pct}%)</div>
            </div>'''

        chart_html = f"""
        <html><head><style>body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:transparent;}}</style></head>
        <body>
        <div style="background:linear-gradient(135deg,#1a202c,#2d3748);border:1px solid #4a5568;border-radius:8px;padding:16px;margin-bottom:8px;">
            <div style="font-size:13px;font-weight:600;color:#e8ecf1;margin-bottom:10px;">{q}</div>
            {bars_html}
        </div>
        </body></html>
        """
        bar_count = len(response_counts)
        components.html(chart_html, height=60 + bar_count * 28)

def render_walking_map(detail_data):
    """Render walking path map from detail contact records"""
    if not detail_data or 'contacts' not in detail_data:
        st.caption("Detail data not yet scraped. Request a scrape to see the walking path.")
        return

    contacts = detail_data['contacts']

    # Check if we have geocoded coordinates
    has_coords = any(c.get('lat') and c.get('lng') for c in contacts)

    if has_coords:
        # Build Leaflet map
        coords_data = []
        for c in contacts:
            if c.get('lat') and c.get('lng'):
                result = c.get('contact_result', 'Unknown')
                color = '#48bb78' if result.lower() == 'canvassed' else '#fc8181' if result.lower() == 'refused' else '#ed8936'
                coords_data.append({
                    'lat': c['lat'], 'lng': c['lng'],
                    'address': c.get('address', ''),
                    'result': result,
                    'time': c.get('date_canvassed', ''),
                    'color': color
                })

        if coords_data:
            center_lat = np.mean([c['lat'] for c in coords_data])
            center_lng = np.mean([c['lng'] for c in coords_data])

            markers_js = ""
            path_coords = []
            for i, c in enumerate(coords_data):
                markers_js += f"""
                L.circleMarker([{c['lat']},{c['lng']}], {{radius:6, fillColor:'{c['color']}', color:'#fff', weight:1, fillOpacity:0.9}})
                    .addTo(map).bindPopup('<b>#{i+1}</b><br>{c["address"]}<br>{c["result"]}<br>{c["time"]}');
                """
                path_coords.append(f"[{c['lat']},{c['lng']}]")

            path_js = f"L.polyline([{','.join(path_coords)}], {{color:'#4f9ef5', weight:2, opacity:0.6, dashArray:'5,10'}}).addTo(map);"

            map_html = f"""
            <html><head>
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
            </head><body style="margin:0;padding:0;">
            <div id="map" style="width:100%;height:400px;border-radius:8px;"></div>
            <script>
                var map = L.map('map').setView([{center_lat},{center_lng}], 15);
                L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}@2x.png', {{
                    attribution: '&copy; OSM &copy; CARTO', maxZoom: 19
                }}).addTo(map);
                {markers_js}
                {path_js}
            </script>
            </body></html>
            """
            components.html(map_html, height=420)

    # Always show the address route list
    # Sort contacts by timestamp
    sorted_contacts = sorted(contacts, key=lambda c: c.get('date_canvassed', ''))

    route_items = ""
    for i, c in enumerate(sorted_contacts):
        result = c.get('contact_result', 'Unknown')
        rcolor = '#48bb78' if result.lower() == 'canvassed' else '#fc8181' if result.lower() == 'refused' else '#a0aec0'
        ts = c.get('date_canvassed', '')
        # Extract just the time portion
        time_str = ts.split(' ')[-2] + ' ' + ts.split(' ')[-1] if len(ts.split(' ')) >= 3 else ts
        route_items += f"""
        <div style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);gap:12px;">
            <div style="width:28px;height:28px;border-radius:50%;background:rgba(79,158,245,0.15);display:flex;align-items:center;justify-content:center;font-size:11px;color:#4f9ef5;font-weight:700;flex-shrink:0;">{i+1}</div>
            <div style="flex:1;font-size:13px;color:#e8ecf1;">{c.get('address', 'Unknown')}</div>
            <div style="font-size:11px;color:{rcolor};font-weight:600;width:80px;text-align:center;">{result}</div>
            <div style="font-size:11px;color:#718096;font-family:'Courier New',monospace;width:90px;text-align:right;">{time_str}</div>
        </div>"""

    route_html = f"""
    <html><head><style>body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:transparent;}}</style></head>
    <body>
    <div style="background:linear-gradient(135deg,#1a202c,#2d3748);border:1px solid #4a5568;border-radius:8px;padding:16px;max-height:400px;overflow-y:auto;">
        <div style="font-size:13px;font-weight:600;color:#a0aec0;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px;">
            Walking Route — {len(sorted_contacts)} stops
        </div>
        {route_items}
    </div>
    </body></html>
    """
    list_height = min(420, 80 + len(sorted_contacts) * 38)
    components.html(route_html, height=list_height)

def render_time_analysis(time_data):
    """Render active vs idle time breakdown"""
    if not time_data:
        st.caption("Detail data not yet scraped. Request a scrape for time analysis.")
        return

    active_pct = round(time_data['active_time'] / max(time_data['total_time'], 1) * 100, 1)
    idle_pct = round(time_data['idle_time'] / max(time_data['total_time'], 1) * 100, 1)

    idle_rows = ""
    for ip in time_data['idle_periods']:
        idle_rows += f"""
        <div style="display:flex;justify-content:space-between;padding:6px 8px;background:rgba(244,67,54,0.05);border-radius:4px;margin:4px 0;font-size:12px;">
            <span style="color:#f44336;">{ip['start']} → {ip['end']}</span>
            <span style="color:#a0aec0;">after {ip['after_address']}</span>
            <span style="color:#f44336;font-weight:700;">{ip['duration']} min</span>
        </div>"""

    idle_section = ""
    if time_data['idle_periods']:
        idle_section = f"""
        <div style="margin-top:16px;">
            <div style="font-size:12px;color:#f44336;font-weight:600;margin-bottom:8px;text-transform:uppercase;">
                Idle Periods ({len(time_data['idle_periods'])} gaps &gt; 15 min)
            </div>
            {idle_rows}
        </div>"""

    time_html = f"""
    <html><head><style>body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:transparent;}}</style></head>
    <body>
    <div style="background:linear-gradient(135deg,#1a202c,#2d3748);border:1px solid #4a5568;border-radius:8px;padding:20px;">
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:18px;font-weight:700;color:#4f9ef5;font-family:'Courier New',monospace;">{time_data['start_time']}</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Start</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:18px;font-weight:700;color:#4f9ef5;font-family:'Courier New',monospace;">{time_data['end_time']}</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">End</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:18px;font-weight:700;color:#4f9ef5;font-family:'Courier New',monospace;">{time_data['total_time']} min</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Total Time</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:18px;font-weight:700;color:#4f9ef5;font-family:'Courier New',monospace;">{time_data['avg_pace']} min</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Avg Pace/Door</div>
            </div>
        </div>
        <!-- Active vs Idle bar -->
        <div style="margin-bottom:8px;">
            <div style="display:flex;height:24px;border-radius:6px;overflow:hidden;">
                <div style="width:{active_pct}%;background:#48bb78;" title="Active: {time_data['active_time']} min"></div>
                <div style="width:{idle_pct}%;background:#f44336;" title="Idle: {time_data['idle_time']} min"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;">
                <span style="color:#48bb78;">Active: {time_data['active_time']} min ({active_pct}%)</span>
                <span style="color:#f44336;">Idle: {time_data['idle_time']} min ({idle_pct}%)</span>
            </div>
        </div>
        {idle_section}
    </div>
    </body></html>
    """
    base_height = 200
    idle_height = len(time_data.get('idle_periods', [])) * 36 + (40 if time_data.get('idle_periods') else 0)
    components.html(time_html, height=base_height + idle_height)

def render_fraud_detection(fraud_info):
    """Render fraud detection / verification panel"""
    if not fraud_info:
        st.caption("Need both scraped detail data AND uploaded survey file for verification.")
        return

    rate = fraud_info['verification_rate']
    rate_color = '#48bb78' if rate >= 80 else '#ed8936' if rate >= 50 else '#f44336'

    missing_html = ""
    if fraud_info['canvassed_no_survey']:
        items = "".join(f'<span style="display:inline-block;padding:2px 8px;background:rgba(244,67,54,0.1);border:1px solid rgba(244,67,54,0.2);border-radius:4px;font-size:11px;color:#f44336;margin:2px;font-family:Courier New,monospace;">VANID {v}</span>' for v in fraud_info['missing_vanids'])
        missing_html = f"""
        <div style="margin-top:12px;">
            <div style="font-size:11px;color:#f44336;font-weight:600;margin-bottom:6px;">Canvassed but NO survey response:</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">{items}</div>
            {'<div style="font-size:10px;color:#718096;margin-top:4px;">...and more</div>' if fraud_info['canvassed_no_survey'] > 10 else ''}
        </div>"""

    fraud_html = f"""
    <html><head><style>body{{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:transparent;}}</style></head>
    <body>
    <div style="background:linear-gradient(135deg,#1a202c,#2d3748);border:1px solid #4a5568;border-radius:8px;padding:20px;">
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:{rate_color};font-family:'Courier New',monospace;">{rate}%</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Verification Rate</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#48bb78;font-family:'Courier New',monospace;">{fraud_info['verified']}</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Verified</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#f44336;font-family:'Courier New',monospace;">{fraud_info['canvassed_no_survey']}</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Missing Survey</div>
            </div>
            <div style="text-align:center;padding:12px;background:rgba(79,158,245,0.1);border:1px solid rgba(79,158,245,0.2);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#ed8936;font-family:'Courier New',monospace;">{fraud_info['survey_no_contact']}</div>
                <div style="font-size:10px;color:#a0aec0;text-transform:uppercase;margin-top:4px;">Survey No Contact</div>
            </div>
        </div>
        {missing_html}
    </div>
    </body></html>
    """
    base_height = 130
    if fraud_info['canvassed_no_survey']:
        base_height += 80
    components.html(fraud_html, height=base_height)

# ============================================================
# MAIN APP
# ============================================================

# Load overview data
data = load_overview_data()
if data is None:
    st.error("Overview data not found. Run a scrape to populate data.")
    st.stop()

# Sidebar — Survey Upload
st.sidebar.markdown("### Survey File Upload")
uploaded_file = st.sidebar.file_uploader(
    "Upload VAN survey export",
    type=['csv', 'xls', 'tsv', 'txt'],
    help="Upload a VAN survey export file (.xls or .csv) to cross-reference with canvassing data"
)

survey_df = None
if uploaded_file is not None:
    survey_df = parse_survey_file(uploaded_file)
    if survey_df is not None:
        n_responses = len(survey_df)
        n_canvassers = survey_df['CanvassedBy'].nunique() if 'CanvassedBy' in survey_df.columns else 0
        n_voters = survey_df['Voter File VANID'].nunique() if 'Voter File VANID' in survey_df.columns else 0
        st.sidebar.success(f"Loaded {n_responses} responses | {n_canvassers} canvassers | {n_voters} voters")

st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.markdown(f"""
**Canvassing Monitor**

Sync Date: {data.get('sync_date', 'N/A')}
Scraped: {data.get('scraped_at', 'N/A')}

Total Records: {data.get('total_records', 0)}

**Thresholds:**
Contact Rate < 15% = Needs Attention
Refused Rate > 10% = Needs Attention
Idle Gaps > 15 min = Flagged
Survey Verification < 50% = Flagged
""")

# Header
st.title("Canvassing Monitor")

# Overview metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">Total Canvassers</div><div class="metric-value">{data["total_records"]}</div><div class="metric-subtitle">Active Records</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">Total Attempts</div><div class="metric-value">{data["report_summary"]["total_attempts"]:,}</div><div class="metric-subtitle">Combined Effort</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="metric-label">Total Doors</div><div class="metric-value">{data["report_summary"]["total_doors"]:,}</div><div class="metric-subtitle">Unique Locations</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="metric-label">Overall Contact Rate</div><div class="metric-value">{data["report_summary"]["contact_rate"]}</div><div class="metric-subtitle">Statewide Average</div></div>', unsafe_allow_html=True)

st.markdown("---")

# Search
search_term = st.text_input("Search canvasser by name", placeholder="Type a name to find specific canvasser...", key="search_input")

# Filter
if search_term:
    filtered = [c for c in data['canvassers'] if search_term.lower() in c['canvasser'].lower()]
else:
    filtered = []

# Results
if search_term:
    if filtered:
        st.subheader(f"Search Results: {len(filtered)} match(es)")

        for canvasser in filtered:
            metrics = calculate_metrics(canvasser)

            # Load detail data if available
            detail = load_detail_data(canvasser['listName'])

            # Get survey matches
            survey_matches = match_canvasser_in_survey(canvasser['canvasser'], survey_df)

            # Time analysis
            time_data = calculate_time_analysis(detail)

            # Fraud detection
            fraud_info = detect_fraud(detail, survey_matches)

            # Composite status
            needs_attn, attn_reasons = compute_attention_status(metrics, time_data, fraud_info)

            # 1. Performance Card (always shown)
            render_performance_card(canvasser, metrics, needs_attn, attn_reasons)

            # Collapsible sections
            with st.expander("📊 Survey Breakout", expanded=False):
                render_survey_breakout(survey_matches)

            with st.expander("🗺️ Walking Path", expanded=False):
                render_walking_map(detail)

            with st.expander("⏱️ Time Analysis", expanded=False):
                render_time_analysis(time_data)

            with st.expander("🔍 Verification / Fraud Detection", expanded=False):
                render_fraud_detection(fraud_info)

            st.markdown("---")
    else:
        st.info("No canvassers found matching your search. Try another name.")
else:
    st.info("Use the search bar above to find a canvasser and view their performance metrics.")
