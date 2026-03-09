import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import json
import os
import time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import re
import ssl
import urllib.request

# SSL context for certificate issues
ssl._create_default_https_context = ssl._create_unverified_context

def convert_google_sheets_url(url):
    """Convert Google Sheets URL to CSV export format"""
    if 'docs.google.com/spreadsheets' in url:
        # Extract the sheet ID
        if '/d/' in url:
            sheet_id = url.split('/d/')[1].split('/')[0]
            # Extract gid if present
            gid = '0'
            if 'gid=' in url:
                gid = url.split('gid=')[1].split('&')[0].split('#')[0]
            # Build CSV export URL
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return url

# Page config
st.set_page_config(
    page_title="Field Canvassing Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for cleaner look
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f2937;
        text-align: center;
        margin-bottom: 1rem;
        padding: 1rem;
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border-radius: 10px;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .alert-box {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid;
    }
    .alert-critical {
        background: #fef2f2;
        border-color: #dc2626;
        color: #991b1b;
    }
    .alert-warning {
        background: #fffbeb;
        border-color: #f59e0b;
        color: #92400e;
    }
    .alert-success {
        background: #f0fdf4;
        border-color: #10b981;
        color: #065f46;
    }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 600;
        margin: 0 0.25rem;
    }
    .badge-green { background: #d1fae5; color: #065f46; }
    .badge-yellow { background: #fef3c7; color: #92400e; }
    .badge-red { background: #fee2e2; color: #991b1b; }
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1f2937;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e5e7eb;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'topline_data' not in st.session_state:
    st.session_state.topline_data = None
if 'team_benchmarks' not in st.session_state:
    st.session_state.team_benchmarks = {}
if 'address_cache' not in st.session_state:
    st.session_state.address_cache = {}

# Helper functions
CACHE_FILE = "address_cache.json"

def load_address_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_address_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)

@st.cache_resource
def get_geocoder():
    return Nominatim(user_agent="field_canvassing_monitor_v2")

def normalize_address(addr):
    """Normalize address for comparison"""
    if pd.isna(addr):
        return ''
    addr = str(addr).strip().upper()
    addr = re.sub(r'\s+(APT|UNIT|#|APARTMENT)\s*\d+.*$', '', addr, flags=re.IGNORECASE)
    addr = re.sub(r'\s+#\d+.*$', '', addr)
    return addr.strip()

def geocode_address(address, cache, geocoder, city="Hamilton Township, NJ"):
    """Geocode address with caching"""
    normalized = normalize_address(address)
    
    if normalized in cache:
        return cache[normalized]
    
    try:
        time.sleep(1)
        # Add city/state if not already in address
        full_address = address if any(x in address.upper() for x in ['NJ', 'NEW JERSEY', 'TRENTON']) else f"{address}, {city}"
        location = geocoder.geocode(full_address)
        if location:
            coords = (location.latitude, location.longitude)
            cache[normalized] = coords
            return coords
        else:
            # No result found
            cache[normalized] = None
            return None
    except Exception as e:
        # Log error but don't crash
        print(f"Geocoding error for {address}: {e}")
        cache[normalized] = None
        return None

def calculate_walk_time(coord1, coord2):
    """Calculate expected walk time in minutes (3 mph walking speed)"""
    if coord1 is None or coord2 is None:
        return None
    distance_miles = geodesic(coord1, coord2).miles
    walk_time_minutes = distance_miles * 20
    return walk_time_minutes

def get_work_hours(date):
    """Get expected work hours based on day of week"""
    if date.weekday() >= 5:  # Weekend
        return {
            'start': datetime.combine(date, datetime.min.time()) + timedelta(hours=12),
            'logging_start': datetime.combine(date, datetime.min.time()) + timedelta(hours=12, minutes=45),
            'logging_end': datetime.combine(date, datetime.min.time()) + timedelta(hours=18, minutes=30),
            'end': datetime.combine(date, datetime.min.time()) + timedelta(hours=19),
            'expected_hours': 5.75,
            'expected_logging_hours': 4.75,
            'door_goal': 75
        }
    else:  # Weekday
        return {
            'start': datetime.combine(date, datetime.min.time()) + timedelta(hours=13),
            'logging_start': datetime.combine(date, datetime.min.time()) + timedelta(hours=13, minutes=45),
            'logging_end': datetime.combine(date, datetime.min.time()) + timedelta(hours=18, minutes=30),
            'end': datetime.combine(date, datetime.min.time()) + timedelta(hours=19),
            'expected_hours': 4.75,
            'expected_logging_hours': 4.75,
            'door_goal': 65
        }

def calculate_fraud_score(df, agent_name):
    """Calculate nuanced fraud score for multi-person canvassing"""
    agent_data = df[df['Name'] == agent_name].copy()
    
    # Group by normalized address and time window (within 2 min)
    agent_data['Normalized_Address'] = agent_data['Address'].apply(normalize_address)
    agent_data['Time_Window'] = agent_data['Date Canvassed'].dt.floor('2min')
    
    multi_person_groups = agent_data.groupby(['Normalized_Address', 'Time_Window']).agg({
        'Success': 'sum',
        'Name': 'count'
    }).reset_index()
    multi_person_groups.columns = ['Address', 'Time', 'Canvassed_Count', 'Total_Count']
    
    # Calculate fraud score
    fraud_score = 0
    instances = []
    
    for _, row in multi_person_groups.iterrows():
        canvassed = row['Canvassed_Count']
        
        if canvassed >= 2:
            instance_score = 0
            
            # Base score by number of people
            if canvassed == 2:
                instance_score += 2
                risk = "🟡 Medium"
            elif canvassed == 3:
                instance_score += 3
                risk = "🟠 Elevated"
            elif canvassed >= 4:
                instance_score += 4
                risk = "🔴 High"
            
            fraud_score += instance_score
            
            instances.append({
                'address': row['Address'],
                'time': row['Time'],
                'count': canvassed,
                'score': instance_score,
                'risk': risk
            })
    
    # Pattern bonus
    total_doors = len(multi_person_groups)
    multi_person_rate = len(instances) / total_doors if total_doors > 0 else 0
    
    if multi_person_rate > 0.3:  # >30% of doors
        fraud_score += 3
    
    return {
        'score': fraud_score,
        'instances': instances,
        'multi_person_rate': multi_person_rate,
        'risk_level': '🟢 Low' if fraud_score < 3 else '🟡 Medium' if fraud_score < 6 else '🔴 High'
    }

# Main app
st.markdown('<div class="main-header">🎯 Field Canvassing Monitor</div>', unsafe_allow_html=True)

# Three-column upload
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📊 Step 1: Topline Data")
    topline_file = st.file_uploader("Team summary CSV", type=['csv'], key='topline')

with col2:
    st.markdown("### 📋 Step 2: Survey Responses")
    survey_file = st.file_uploader("Survey data CSV", type=['csv'], key='survey')

with col3:
    st.markdown("### 👤 Step 3: Individual Agent Data")
    individual_file = st.file_uploader("Agent detail CSV", type=['csv'], key='individual')

# Process Topline Data
if topline_file is not None:
    # Try UTF-16 (Excel export) with skiprows, then UTF-8
    try:
        topline_df = pd.read_csv(topline_file, encoding='utf-16', skiprows=1)
    except:
        try:
            topline_df = pd.read_csv(topline_file, encoding='utf-8-sig')
        except:
            topline_df = pd.read_csv(topline_file)
    
    topline_df.columns = topline_df.columns.str.replace('\ufeff', '').str.strip()
    
    # Find Contact Rate column flexibly
    cr_col = next((c for c in topline_df.columns if 'contact' in c.lower() and 'rate' in c.lower()), None)
    if cr_col:
        topline_df['Contact_Rate_Pct'] = (topline_df[cr_col].astype(float) * 100).round(1)
    else:
        st.error(f"Can't find Contact Rate. Columns: {list(topline_df.columns)}")
        st.stop()
    
    st.session_state.topline_data = topline_df
    
    # Calculate team benchmarks
    benchmarks = {
        'avg_doors': topline_df['Doors'].mean(),
        'avg_contact_rate': topline_df['Contact_Rate_Pct'].mean(),
        'avg_canvassed': topline_df['Canvassed'].mean(),
        'avg_not_home_rate': (topline_df['Not Home'] / topline_df['Doors'] * 100).mean(),
        'top_performer': topline_df.loc[topline_df['Contact_Rate_Pct'].idxmax()]['Canvasser'] if len(topline_df) > 0 else None,
        'top_contact_rate': topline_df['Contact_Rate_Pct'].max(),
    }
    st.session_state.team_benchmarks = benchmarks
    
    # Team Overview Tab
    st.markdown("---")
    st.markdown("## 📊 Team Overview")
    
    # Team metrics
    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Team Size</div>
            <div class="metric-value">{len(topline_df)}</div>
            <div class="badge badge-green">Active Canvassers</div>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Avg Doors</div>
            <div class="metric-value">{benchmarks['avg_doors']:.0f}</div>
            <div class="badge badge-yellow">Per Agent</div>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Avg Contact Rate</div>
            <div class="metric-value">{benchmarks['avg_contact_rate']:.1f}%</div>
            <div class="badge badge-green">Team Average</div>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Top Performer</div>
            <div class="metric-value" style="font-size: 1.5rem;">{benchmarks['top_performer'] or 'N/A'}</div>
            <div class="badge badge-green">{benchmarks['top_contact_rate']:.1f}% Contact</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Leaderboard
    with st.expander("📋 View Team Leaderboard", expanded=False):
        leaderboard = topline_df[['Canvasser', 'Doors', 'Canvassed', 'Contact_Rate_Pct', 'Not Home']].copy()
        leaderboard = leaderboard.sort_values('Doors', ascending=False)
        leaderboard.columns = ['Canvasser', 'Doors', 'Canvassed', 'Contact Rate %', 'Not Home']
        st.dataframe(leaderboard, use_container_width=True, hide_index=True)

# Process Survey Data
if survey_file is not None:
    
    st.markdown("---")
    st.markdown("## 📋 Survey Response Analysis")
    
    # Try UTF-8 first (most survey files), then UTF-16
    try:
        survey_df = pd.read_csv(survey_file, encoding='utf-8')
    except:
        try:
            survey_df = pd.read_csv(survey_file, encoding='utf-16', skiprows=1)
        except:
            survey_df = pd.read_csv(survey_file, encoding='utf-8-sig')
    
    survey_df.columns = survey_df.columns.str.replace('\ufeff', '').str.strip()
    
    # Check what columns actually exist and map them
    col_mapping = {}
    for col in survey_df.columns:
        col_lower = col.lower().strip()
        col_stripped = col.strip()
        
        # ID column - be more flexible
        if 'ID' not in col_mapping:
            if (col_stripped in ['ID', 'ID ', ' ID', 'Voter File VANID'] or 
                (col_lower == 'id') or 
                ('vanid' in col_lower) or
                (col_stripped.startswith('ID') and len(col_stripped) <= 4)):
                col_mapping['ID'] = col
        
        # CanvassedBy
        if 'CanvassedBy' not in col_mapping and 'canvassed' in col_lower and 'by' in col_lower:
            col_mapping['CanvassedBy'] = col
        
        # Question
        if 'Question' not in col_mapping and 'question' in col_lower and 'long' in col_lower:
            col_mapping['Question'] = col
        
        # Response
        if 'Response' not in col_mapping and 'response' in col_lower and 'name' in col_lower:
            col_mapping['Response'] = col
        
        # Date
        if 'Date' not in col_mapping and 'date' in col_lower and 'canvassed' in col_lower:
            col_mapping['Date'] = col
    
    # Verify we have required columns
    if 'ID' not in col_mapping:
        st.error(f"Could not find ID column in survey data. Available columns: {list(survey_df.columns)}")
        st.stop()
    if 'CanvassedBy' not in col_mapping:
        st.error(f"Could not find CanvassedBy column in survey data. Available columns: {list(survey_df.columns)}")
        st.stop()
    
    # Extract and rename columns
    survey_df = survey_df[list(col_mapping.values())].copy()
    survey_df.columns = list(col_mapping.keys())
    
    # Clean canvasser names (remove extra spaces, standardize)
    survey_df['CanvassedBy'] = survey_df['CanvassedBy'].str.strip()
    
    # Store in session state for individual matching
    if 'survey_data' not in st.session_state:
        st.session_state.survey_data = {}
    st.session_state.survey_data = survey_df
    
    # Team overview
    total_surveys = survey_df['ID'].nunique()
    total_canvassers = survey_df['CanvassedBy'].nunique()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Surveys</div>
            <div class="metric-value">{total_surveys}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Active Canvassers</div>
            <div class="metric-value">{total_canvassers}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Create response percentage table - CANVASSERS AS ROWS, QUESTIONS AS COLUMNS
    st.markdown("### 📊 Survey Response Breakdown")
    
    # Clean canvasser names
    survey_df['CanvassedBy'] = survey_df['CanvassedBy'].str.strip()
    
    # Create Question-Response combinations
    survey_df['Question_Response'] = survey_df['Question'] + ' - ' + survey_df['Response']
    
    # Get unique canvassers and question-responses
    canvassers = sorted(survey_df['CanvassedBy'].unique())
    questions_responses = sorted(survey_df['Question_Response'].unique())
    
    # Build table data
    table_data = []
    
    # Calculate total responses per canvasser
    canvasser_totals = survey_df.groupby('CanvassedBy')['ID'].count()
    
    # For each canvasser, calculate percentage for each question-response
    for canvasser in canvassers:
        row = {'Canvasser': canvasser}
        
        for qr in questions_responses:
            qr_data = survey_df[(survey_df['CanvassedBy'] == canvasser) & (survey_df['Question_Response'] == qr)]
            count = len(qr_data)
            row[qr] = count
        
        table_data.append(row)
    
    # Add team total row
    team_row = {'Canvasser': '📊 Team Total'}
    for qr in questions_responses:
        qr_data = survey_df[survey_df['Question_Response'] == qr]
        total = len(qr_data)
        team_row[qr] = total
    
    table_data.append(team_row)
    
    # Create and display dataframe
    response_table = pd.DataFrame(table_data)
    st.dataframe(response_table, use_container_width=True, hide_index=True)
    
    # Activity Timeline - Clean visual showing who's active
    st.markdown("### ⏱️ Real-Time Activity Status")
    
    # Parse DateCanvassed if it exists
    if 'Date' in survey_df.columns:
        survey_df['DateCanvassed_parsed'] = pd.to_datetime(survey_df['Date'], errors='coerce')
        
        # Use the LATEST timestamp in the dataset as "current time" (when data was exported)
        current_time = survey_df['DateCanvassed_parsed'].max()
        
        st.info(f"📸 Data snapshot as of: {current_time.strftime('%B %d, %Y at %I:%M%p')}")
        
        # Get shift start (assuming 1pm start on the same day as latest survey)
        shift_start = current_time.replace(hour=13, minute=0, second=0, microsecond=0)
        total_shift_minutes = (current_time - shift_start).total_seconds() / 60
        
        if total_shift_minutes > 0:
            # For each canvasser, get their activity
            canvasser_activity = []
            for canvasser in canvassers:
                canvasser_surveys = survey_df[survey_df['CanvassedBy'] == canvasser]
                last_survey = canvasser_surveys['DateCanvassed_parsed'].max()
                total_surveys = len(canvasser_surveys)
                
                if pd.notna(last_survey):
                    minutes_since = (current_time - last_survey).total_seconds() / 60
                    minutes_active = (last_survey - shift_start).total_seconds() / 60
                    
                    # Calculate percentage of shift elapsed when last active
                    pct_elapsed = min((minutes_active / total_shift_minutes) * 100, 100)
                    
                    is_idle = minutes_since > 30
                    
                    canvasser_activity.append({
                        'canvasser': canvasser,
                        'total_surveys': total_surveys,
                        'minutes_since': minutes_since,
                        'pct_elapsed': pct_elapsed,
                        'is_idle': is_idle,
                        'last_survey': last_survey
                    })
            
            # Sort by idle status (idle first) then by minutes since
            canvasser_activity.sort(key=lambda x: (not x['is_idle'], -x['pct_elapsed']))
            
            # Display timeline for each canvasser
            for activity in canvasser_activity:
                status_emoji = "🔴" if activity['is_idle'] else "🟢"
                status_text = f"IDLE ({int(activity['minutes_since'])}min)" if activity['is_idle'] else f"Active ({int(activity['minutes_since'])}min ago)"
                bar_color = "#ef4444" if activity['is_idle'] else "#10b981"
                
                # Create visual timeline bar
                filled_width = int(activity['pct_elapsed'])
                empty_width = 100 - filled_width
                
                st.markdown(f"""
                <div style="margin: 1rem 0; padding: 0.5rem; background: #f9fafb; border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <strong>{status_emoji} {activity['canvasser']}</strong>
                        <span style="color: #6b7280; font-size: 0.9rem;">{activity['total_surveys']} surveys | {status_text}</span>
                    </div>
                    <div style="display: flex; align-items: center;">
                        <span style="font-size: 0.8rem; color: #9ca3af; margin-right: 0.5rem;">1pm</span>
                        <div style="flex: 1; height: 20px; background: #e5e7eb; border-radius: 4px; overflow: hidden; display: flex;">
                            <div style="width: {filled_width}%; background: {bar_color}; transition: width 0.3s;"></div>
                            <div style="width: {empty_width}%; background: #e5e7eb;"></div>
                        </div>
                        <span style="font-size: 0.8rem; color: #9ca3af; margin-left: 0.5rem;">Now</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Summary stats
            active_count = sum(1 for a in canvasser_activity if not a['is_idle'])
            idle_count = sum(1 for a in canvasser_activity if a['is_idle'])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("🟢 Active Canvassers", active_count)
            with col2:
                st.metric("🔴 Idle (>30min)", idle_count)
    
    # Outlier Detection
    st.markdown("### 🔍 Outliers Detected")
    
    total_responses = len(survey_df)
    outliers_found = []
    
    for canvasser in canvassers:
        canvasser_outliers = []
        canvasser_total = canvasser_totals.get(canvasser, 1)
        
        for qr in questions_responses:
            # Agent percentage
            canvasser_qr = survey_df[(survey_df['CanvassedBy'] == canvasser) & (survey_df['Question_Response'] == qr)]
            agent_pct = (len(canvasser_qr) / canvasser_total * 100) if canvasser_total > 0 else 0
            
            # Team percentage  
            qr_data = survey_df[survey_df['Question_Response'] == qr]
            team_pct = (len(qr_data) / total_responses * 100) if total_responses > 0 else 0
            
            diff = agent_pct - team_pct
            
            # Flag if >20% deviation
            if abs(diff) > 20:
                severity = "🚨" if abs(diff) > 30 else "⚠️"
                direction = "above" if diff > 0 else "below"
                canvasser_outliers.append(f"{severity} {qr}: {agent_pct:.0f}% ({abs(diff):.0f}% {direction} team avg {team_pct:.0f}%)")
        
        if canvasser_outliers:
            outliers_found.append({
                'canvasser': canvasser,
                'outliers': canvasser_outliers
            })
    
    if outliers_found:
        for outlier in outliers_found:
            st.markdown(f"""
            <div class="alert-box alert-warning">
                <strong>{outlier['canvasser']}</strong><br>
                """ + "<br>".join(outlier['outliers']) + """
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="alert-box alert-success">
            <strong>✅ No Significant Outliers Detected</strong><br>
            All canvassers within 20% of team averages
        </div>
        """, unsafe_allow_html=True)

# Process Individual Agent Data
if individual_file is not None and st.session_state.topline_data is not None:
    
    st.markdown("---")
    st.markdown("## 👤 Individual Agent Analysis")
    
    # Try UTF-8 first, then UTF-16
    df_individual = None
    last_error = None
    for encoding in ['utf-8', 'utf-16', 'utf-8-sig']:
        for skiprows in [0, 1]:
            try:
                individual_file.seek(0)  # Reset file pointer
                test_df = pd.read_csv(individual_file, encoding=encoding, skiprows=skiprows)
                if len(test_df.columns) >= 5 and len(test_df) > 0:
                    df_individual = test_df
                    break
            except Exception as e:
                last_error = e
                continue
        if df_individual is not None:
            break
    
    if df_individual is None or len(df_individual) == 0:
        st.error(f"Can't read individual file. Last error: {last_error}")
        st.stop()
    
    df_individual.columns = df_individual.columns.str.replace('\ufeff', '').str.strip()
    df_individual['Date Canvassed'] = pd.to_datetime(df_individual['Date Canvassed'], errors='coerce')
    if df_individual['Date Canvassed'].dt.tz is not None:
        df_individual['Date Canvassed'] = df_individual['Date Canvassed'].dt.tz_localize(None)
    df_individual = df_individual.sort_values('Date Canvassed')
    
    # Name column in individual data is RESIDENT name, not agent - ignore it
    # Agent name will be detected from survey data
    agent_name = None
    
    # Check if individual data has ID column (check for VanID or ID)
    id_column = None
    if 'VanID' in df_individual.columns:
        id_column = 'VanID'
    elif 'ID' in df_individual.columns:
        id_column = 'ID'
    
    has_id_column = id_column is not None
    
    # Detect canvasser from survey data by matching IDs
    if has_id_column and 'survey_data' in st.session_state and st.session_state.survey_data is not None:
        survey_df = st.session_state.survey_data
        individual_ids = df_individual[id_column].unique()
        
        # Find ALL surveys that match these IDs (regardless of canvasser name)
        matching_surveys = survey_df[survey_df['ID'].isin(individual_ids)]
        
        if len(matching_surveys) > 0:
            # Get the most common canvasser for these IDs
            agent_name = matching_surveys['CanvassedBy'].mode()[0] if len(matching_surveys['CanvassedBy'].mode()) > 0 else "Unknown"
        else:
            agent_name = "Unknown Agent (No surveys found)"
    
    if agent_name is None:
        agent_name = "Unknown Agent"
    
    # has_id_column already set earlier when we detected id_column (VanID or ID)
    # Don't re-check here, just use the existing variable
    survey_validation = None
    
    if has_id_column and 'survey_data' in st.session_state and st.session_state.survey_data is not None:
        # Match individual contacts with survey responses
        survey_df = st.session_state.survey_data
        
        # Get ALL IDs from individual data
        agent_ids = df_individual[id_column].unique()
        
        # Get ALL surveys that match these IDs (don't filter by name)
        agent_surveys = survey_df[survey_df['ID'].isin(agent_ids)]
        
        # Find contacts marked as canvassed (not "Not Home")
        canvassed_contacts = df_individual[df_individual['Contact Result'] != 'Not Home']
        canvassed_ids = canvassed_contacts[id_column].unique() if id_column in canvassed_contacts.columns else []
        
        # Check which canvassed contacts have survey data
        surveyed_ids = agent_surveys['ID'].unique()
        missing_surveys = set(canvassed_ids) - set(surveyed_ids)
        
        survey_validation = {
            'total_canvassed': len(canvassed_ids),
            'with_surveys': len(set(canvassed_ids) & set(surveyed_ids)),
            'missing_surveys': len(missing_surveys),
            'missing_ids': list(missing_surveys),
            'survey_completeness': (len(set(canvassed_ids) & set(surveyed_ids)) / len(canvassed_ids) * 100) if len(canvassed_ids) > 0 else 0
        }
    
    # Get work hours for the day
    work_date = df_individual['Date Canvassed'].iloc[0].date() if len(df_individual) > 0 else datetime.now().date()
    work_hours = get_work_hours(work_date)
    
    # Calculate metrics
    df_individual['Success'] = df_individual['Contact Result'] == 'Canvassed'
    df_individual['Not_Home'] = df_individual['Contact Result'] == 'Not Home'
    df_individual['Normalized_Address'] = df_individual['Address'].apply(normalize_address)
    
    unique_doors = df_individual['Normalized_Address'].nunique()
    total_contacts = len(df_individual)
    
    # Contact rate = everything EXCEPT "Not Home" divided by total doors
    contacted = df_individual[~df_individual['Not_Home']].shape[0]
    contact_rate = (contacted / unique_doors * 100) if unique_doors > 0 else 0
    
    # Successful contacts (Canvassed)
    successful = df_individual['Success'].sum()
    
    # Time analysis
    first_contact = df_individual['Date Canvassed'].min()
    last_contact = df_individual['Date Canvassed'].max()
    active_time = (last_contact - first_contact).total_seconds() / 3600
    doors_per_hour = unique_doors / active_time if active_time > 0 else 0
    
    # Get agent's topline data if available
    agent_topline = st.session_state.topline_data[
        st.session_state.topline_data['Canvasser'].str.lower() == agent_name.lower()
    ]
    
    # Data mismatch check
    data_mismatch = None
    if len(agent_topline) > 0:
        topline_doors = agent_topline['Doors'].iloc[0]
        topline_contact_rate = agent_topline['Contact_Rate_Pct'].iloc[0]
        
        door_diff = abs(unique_doors - topline_doors)
        contact_diff = abs(contact_rate - topline_contact_rate)
        
        if door_diff > 2 or contact_diff > 5:
            data_mismatch = {
                'topline_doors': topline_doors,
                'individual_doors': unique_doors,
                'door_diff': door_diff,
                'topline_contact': topline_contact_rate,
                'individual_contact': contact_rate,
                'contact_diff': contact_diff
            }
    
    # Fraud detection
    fraud_analysis = calculate_fraud_score(df_individual, agent_name)
    
    # Time between contacts
    df_individual['Time_Between'] = df_individual['Date Canvassed'].diff()
    df_individual['Minutes_Between'] = df_individual['Time_Between'].dt.total_seconds() / 60
    
    # Gaps analysis
    long_gaps = df_individual[
        (df_individual['Minutes_Between'] > 30) &
        (df_individual['Date Canvassed'] >= work_hours['logging_start']) &
        (df_individual['Date Canvassed'] <= work_hours['logging_end'])
    ]
    total_gap_time = long_gaps['Minutes_Between'].sum() / 60 if len(long_gaps) > 0 else 0
    
    # Late start check
    late_start = (first_contact - work_hours['logging_start']).total_seconds() / 60 > 60
    
    # ==========================================
    # EXECUTIVE SUMMARY
    # ==========================================
    
    st.markdown(f"""
    <div style="background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin: 2rem 0;">
        <h2 style="margin: 0 0 1rem 0; color: #1f2937;">👤 {agent_name} - Executive Summary</h2>
        <p style="color: #6b7280; margin: 0;">
            List: {df_individual['List Name'].iloc[0] if len(df_individual) > 0 else 'N/A'} | 
            Date: {work_date.strftime('%B %d, %Y')} | 
            Shift: {'Weekend' if work_date.weekday() >= 5 else 'Weekday'} 
            ({work_hours['logging_start'].strftime('%I:%M%p')} - {work_hours['logging_end'].strftime('%I:%M%p')})
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Performance Metrics
    st.markdown('<div class="section-header">🎯 Performance Snapshot</div>', unsafe_allow_html=True)
    
    # Calculate goal tracking
    time_elapsed = active_time
    time_remaining = work_hours['expected_logging_hours'] - time_elapsed if time_elapsed < work_hours['expected_logging_hours'] else 0
    projected_doors = unique_doors + (doors_per_hour * time_remaining) if time_remaining > 0 else unique_doors
    doors_needed = work_hours['door_goal'] - unique_doors
    pace_needed = doors_needed / time_remaining if time_remaining > 0 else 0
    
    # Goal status
    if projected_doors >= work_hours['door_goal']:
        goal_status = "🟢 On Track"
        goal_color = "green"
        goal_message = f"Projected to exceed goal by {int(projected_doors - work_hours['door_goal'])} doors"
    elif projected_doors >= work_hours['door_goal'] * 0.9:
        goal_status = "🟡 Close"
        goal_color = "yellow"
        goal_message = f"Need {int(doors_needed)} more doors ({pace_needed:.1f}/hr pace required)"
    else:
        goal_status = "🔴 Behind"
        goal_color = "red"
        if time_remaining > 0:
            goal_message = f"Short by {int(work_hours['door_goal'] - projected_doors)} doors at current pace"
        else:
            goal_message = f"Shift ended - missed goal by {int(doors_needed)} doors"
    
    perf_cols = st.columns(5)
    
    # Doors
    door_status = "🟢" if unique_doors >= work_hours['door_goal'] else "🟡" if unique_doors >= work_hours['door_goal'] * 0.8 else "🔴"
    with perf_cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Doors Knocked</div>
            <div class="metric-value">{unique_doors}</div>
            <div class="badge badge-{'green' if unique_doors >= work_hours['door_goal'] else 'yellow' if unique_doors >= work_hours['door_goal'] * 0.8 else 'red'}">
                Goal: {work_hours['door_goal']} {door_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Contact Rate
    benchmarks = st.session_state.team_benchmarks
    contact_diff_pct = ((contact_rate - benchmarks['avg_contact_rate']) / benchmarks['avg_contact_rate'] * 100) if benchmarks['avg_contact_rate'] > 0 else 0
    contact_status = "🟢" if abs(contact_diff_pct) < 30 else "🟡" if abs(contact_diff_pct) < 50 else "🔴"
    
    with perf_cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Contact Rate</div>
            <div class="metric-value">{contact_rate:.1f}%</div>
            <div class="badge badge-{'green' if abs(contact_diff_pct) < 30 else 'yellow' if abs(contact_diff_pct) < 50 else 'red'}">
                Team: {benchmarks['avg_contact_rate']:.1f}% {contact_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Doors per hour
    expected_dph = work_hours['door_goal'] / work_hours['expected_logging_hours']
    dph_status = "🟢" if doors_per_hour >= expected_dph else "🟡" if doors_per_hour >= expected_dph * 0.8 else "🔴"
    
    with perf_cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Doors/Hour</div>
            <div class="metric-value">{doors_per_hour:.1f}</div>
            <div class="badge badge-{'green' if doors_per_hour >= expected_dph else 'yellow' if doors_per_hour >= expected_dph * 0.8 else 'red'}">
                Target: {expected_dph:.1f} {dph_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Active time
    time_status = "🟢" if active_time >= work_hours['expected_logging_hours'] * 0.9 else "🟡" if active_time >= work_hours['expected_logging_hours'] * 0.7 else "🔴"
    
    with perf_cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Active Time</div>
            <div class="metric-value">{active_time:.1f}h</div>
            <div class="badge badge-{'green' if active_time >= work_hours['expected_logging_hours'] * 0.9 else 'yellow' if active_time >= work_hours['expected_logging_hours'] * 0.7 else 'red'}">
                Expected: {work_hours['expected_logging_hours']:.1f}h {time_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with perf_cols[4]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Projected Finish</div>
            <div class="metric-value">{int(projected_doors)}</div>
            <div class="badge badge-{goal_color}">
                {goal_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Simple goal status line
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem; background: #f9fafb; border-radius: 8px; margin-top: 1rem;">
        <strong>Goal Progress:</strong> {unique_doors}/{work_hours['door_goal']} doors ({unique_doors/work_hours['door_goal']*100:.0f}%) • 
        {goal_message}
        {f" • {time_remaining:.1f}h remaining" if time_remaining > 0 else ""}
    </div>
    """, unsafe_allow_html=True)
    
    # Critical Alerts
    st.markdown('<div class="section-header">🚨 Critical Alerts</div>', unsafe_allow_html=True)
    
    critical_count = 0
    
    # Multi-person fraud
    if fraud_analysis['score'] >= 6:
        critical_count += 1
        st.markdown(f"""
        <div class="alert-box alert-critical">
            <strong>🔴 Multi-Person Contact Pattern - {fraud_analysis['risk_level']}</strong><br>
            Detected {len(fraud_analysis['instances'])} instances of multiple people marked "Canvassed" at same address/time<br>
            Fraud Score: {fraud_analysis['score']} | Pattern Rate: {fraud_analysis['multi_person_rate']*100:.1f}% of doors
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📋 View Multi-Person Instances"):
            for inst in fraud_analysis['instances']:
                st.write(f"{inst['risk']} {inst['address']} - {inst['count']} people at {inst['time'].strftime('%I:%M%p')} (Score: +{inst['score']})")
    
    # Data mismatch
    if data_mismatch:
        critical_count += 1
        st.markdown(f"""
        <div class="alert-box alert-critical">
            <strong>🔴 Data Mismatch Detected</strong><br>
            Topline: {data_mismatch['topline_doors']} doors, {data_mismatch['topline_contact']:.1f}% contact<br>
            Individual: {data_mismatch['individual_doors']} doors, {data_mismatch['individual_contact']:.1f}% contact<br>
            Difference: {data_mismatch['door_diff']} doors, {data_mismatch['contact_diff']:.1f}% contact rate
        </div>
        """, unsafe_allow_html=True)
    
    # Large time gaps
    if total_gap_time >= 2:
        critical_count += 1
        st.markdown(f"""
        <div class="alert-box alert-critical">
            <strong>🔴 Excessive Downtime</strong><br>
            {total_gap_time:.1f} hours of gaps (>30 min) during work hours<br>
            {len(long_gaps)} separate gap periods detected
        </div>
        """, unsafe_allow_html=True)
    
    # Contact rate deviation
    if abs(contact_diff_pct) > 50:
        critical_count += 1
        direction = "above" if contact_diff_pct > 0 else "below"
        st.markdown(f"""
        <div class="alert-box alert-critical">
            <strong>🔴 Contact Rate Anomaly</strong><br>
            {contact_rate:.1f}% contact rate is {abs(contact_diff_pct):.0f}% {direction} team average ({benchmarks['avg_contact_rate']:.1f}%)<br>
            {"Suspiciously high - verify legitimacy" if contact_diff_pct > 0 else "Critically low - possible effort issue"}
        </div>
        """, unsafe_allow_html=True)
    
    # Survey completeness check
    if survey_validation and survey_validation['survey_completeness'] < 80:
        critical_count += 1
        st.markdown(f"""
        <div class="alert-box alert-critical">
            <strong>🔴 Incomplete Survey Data</strong><br>
            {survey_validation['total_canvassed']} contacts marked "Canvassed"<br>
            Only {survey_validation['with_surveys']} have survey responses ({survey_validation['survey_completeness']:.0f}%)<br>
            {survey_validation['missing_surveys']} contacts missing surveys - possible fabrication
        </div>
        """, unsafe_allow_html=True)
        
        if survey_validation['missing_surveys'] > 0 and survey_validation['missing_surveys'] <= 10:
            with st.expander("📋 View Missing Survey IDs"):
                st.write(f"IDs marked canvassed but no survey logged: {', '.join(map(str, survey_validation['missing_ids']))}")
    
    if critical_count == 0:
        st.markdown("""
        <div class="alert-box alert-success">
            <strong>✅ No Critical Issues Detected</strong>
        </div>
        """, unsafe_allow_html=True)
    
    # Warnings
    st.markdown('<div class="section-header">⚠️ Warnings</div>', unsafe_allow_html=True)
    
    warning_count = 0
    
    # Medium fraud risk
    if 3 <= fraud_analysis['score'] < 6:
        warning_count += 1
        st.markdown(f"""
        <div class="alert-box alert-warning">
            <strong>🟡 Multi-Person Contact Pattern - {fraud_analysis['risk_level']}</strong><br>
            {len(fraud_analysis['instances'])} instances detected. Review manually to verify legitimacy.
        </div>
        """, unsafe_allow_html=True)
    
    # Late start
    if late_start:
        warning_count += 1
        minutes_late = (first_contact - work_hours['logging_start']).total_seconds() / 60
        st.markdown(f"""
        <div class="alert-box alert-warning">
            <strong>🟡 Late Start</strong><br>
            First contact at {first_contact.strftime('%I:%M%p')} ({minutes_late:.0f} min after expected start)
        </div>
        """, unsafe_allow_html=True)
    
    # Below door goal
    if unique_doors < work_hours['door_goal'] and unique_doors >= work_hours['door_goal'] * 0.6:
        warning_count += 1
        st.markdown(f"""
        <div class="alert-box alert-warning">
            <strong>🟡 Below Door Goal</strong><br>
            {unique_doors} doors knocked (Goal: {work_hours['door_goal']}) - {work_hours['door_goal'] - unique_doors} doors short
        </div>
        """, unsafe_allow_html=True)
    
    # Moderate contact rate deviation
    if 30 <= abs(contact_diff_pct) < 50:
        warning_count += 1
        direction = "above" if contact_diff_pct > 0 else "below"
        st.markdown(f"""
        <div class="alert-box alert-warning">
            <strong>🟡 Contact Rate Below Team Average</strong><br>
            {contact_rate:.1f}% is {abs(contact_diff_pct):.0f}% {direction} team average - consider coaching
        </div>
        """, unsafe_allow_html=True)
    
    if warning_count == 0:
        st.markdown("""
        <div class="alert-box alert-success">
            <strong>✅ No Warnings</strong>
        </div>
        """, unsafe_allow_html=True)
    
    # Strengths
    st.markdown('<div class="section-header">✅ Strengths</div>', unsafe_allow_html=True)
    
    strengths = []
    
    if fraud_analysis['score'] < 3:
        strengths.append("• No suspicious multi-person contact patterns")
    
    if abs(contact_diff_pct) < 30:
        strengths.append(f"• Contact rate ({contact_rate:.1f}%) within normal range of team average")
    elif contact_diff_pct > 30:
        strengths.append(f"• Contact rate ({contact_rate:.1f}%) above team average - strong performance")
    
    if doors_per_hour >= expected_dph:
        strengths.append(f"• Doors/hour ({doors_per_hour:.1f}) meets or exceeds target ({expected_dph:.1f})")
    
    if total_gap_time < 1:
        strengths.append("• Consistent work pace with minimal downtime")
    
    if unique_doors >= work_hours['door_goal']:
        strengths.append(f"• Met door goal ({unique_doors}/{work_hours['door_goal']})")
    
    if survey_validation and survey_validation['survey_completeness'] >= 90:
        strengths.append(f"• Excellent survey completeness ({survey_validation['survey_completeness']:.0f}%)")
    
    if strengths:
        st.markdown("""
        <div class="alert-box alert-success">
            <strong>Positive Performance Indicators:</strong><br>
            """ + "<br>".join(strengths) + """
        </div>
        """, unsafe_allow_html=True)
    
    # Survey Validation Report - Always show section for debugging
    st.markdown('<div class="section-header">📋 Survey Validation Report</div>', unsafe_allow_html=True)
    
    # Debug info
    st.write(f"DEBUG: has_id_column = {has_id_column}")
    st.write(f"DEBUG: id_column = {id_column}")
    st.write(f"DEBUG: survey_data in session = {'survey_data' in st.session_state}")
    if 'survey_data' in st.session_state:
        st.write(f"DEBUG: survey_data is not None = {st.session_state.survey_data is not None}")
    
    if has_id_column and 'survey_data' in st.session_state and st.session_state.survey_data is not None:
        st.markdown('<div class="section-header">📋 Survey Validation Report</div>', unsafe_allow_html=True)
        
        survey_df = st.session_state.survey_data
        
        # Get ALL IDs from individual data
        individual_ids = df_individual[id_column].unique()
        
        # Match surveys by ID only (not by name)
        matched_surveys_all = survey_df[survey_df['ID'].isin(individual_ids)]
        
        # Check if ANY surveys exist for these IDs
        if len(matched_surveys_all) == 0:
            st.markdown(f"""
            <div class="alert-box alert-critical">
                <strong>🚨 ZERO SURVEYS FOUND</strong><br>
                No survey responses found for any of the {len(individual_ids)} VanIDs in this data<br>
                Agent marked contacts but NO surveys were logged<br>
                <strong>CRITICAL FRAUD INDICATOR</strong>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Get IDs from individual data that were marked as contacted (not "Not Home")
            contacted_ids = df_individual[~df_individual['Not_Home']][id_column].unique()
            
            # Match surveys to contacted IDs
            matched_surveys = matched_surveys_all[matched_surveys_all['ID'].isin(contacted_ids)]
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">People Contacted</div>
                <div class="metric-value">{len(contacted_ids)}</div>
                <div class="metric-label">Not "Not Home"</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            surveyed_ids = matched_surveys['ID'].nunique()
            completeness_pct = (surveyed_ids/len(contacted_ids)*100) if len(contacted_ids) > 0 else 0
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">With Surveys</div>
                <div class="metric-value">{surveyed_ids}</div>
                <div class="badge badge-{'green' if surveyed_ids >= len(contacted_ids) * 0.9 else 'yellow' if surveyed_ids >= len(contacted_ids) * 0.7 else 'red'}">
                    {completeness_pct:.0f}%
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            missing = len(contacted_ids) - surveyed_ids
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Missing Surveys</div>
                <div class="metric-value">{missing}</div>
                <div class="badge badge-{'green' if missing == 0 else 'yellow' if missing <= 3 else 'red'}">
                    {'None' if missing == 0 else 'Review'}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Survey response breakdown for this agent's actual contacts
        if len(matched_surveys) > 0:
            st.markdown("### Survey Responses (From Agent's Actual Contacts)")
            
            # Create response breakdown
            matched_surveys['Question_Response'] = matched_surveys['Question'] + ' - ' + matched_surveys['Response']
            response_breakdown = matched_surveys['Question_Response'].value_counts().reset_index()
            response_breakdown.columns = ['Question-Response', 'Count']
            
            # Calculate percentages
            total_survey_responses = len(matched_surveys)
            response_breakdown['Percentage'] = (response_breakdown['Count'] / total_survey_responses * 100).round(1)
            response_breakdown['Display'] = response_breakdown['Count'].astype(str) + ' (' + response_breakdown['Percentage'].astype(str) + '%)'
            
            st.dataframe(response_breakdown[['Question-Response', 'Display']], use_container_width=True, hide_index=True, height=400)
        
        # Missing survey details
        if missing > 0:
            st.markdown(f"""
            <div class="alert-box alert-warning">
                <strong>⚠️ {missing} Contact(s) Missing Survey Data</strong><br>
                These contacts were marked as contacted but have no survey responses logged
            </div>
            """, unsafe_allow_html=True)
            
            # Find which IDs are missing surveys
            surveyed_id_set = set(matched_surveys['ID'].unique())
            missing_ids = [id for id in contacted_ids if id not in surveyed_id_set]
            
            if len(missing_ids) <= 10:
                with st.expander("📋 View Missing Survey Contacts"):
                    missing_contacts = df_individual[df_individual[id_column].isin(missing_ids)][
                        [id_column, 'Address', 'Date Canvassed', 'Contact Result']
                    ].copy()
                    missing_contacts['Time'] = missing_contacts['Date Canvassed'].dt.strftime('%I:%M%p')
                    missing_contacts = missing_contacts[[id_column, 'Address', 'Time', 'Contact Result']]
                    st.dataframe(missing_contacts, use_container_width=True, hide_index=True)
        else:
            st.markdown("""
            <div class="alert-box alert-success">
                <strong>✅ Complete Survey Coverage</strong><br>
                All contacted individuals have survey responses logged
            </div>
            """, unsafe_allow_html=True)
    
    elif has_id_column:
        # Has IDs but no survey data uploaded
        st.markdown('<div class="section-header">📋 Survey Validation Report</div>', unsafe_allow_html=True)
        st.info("💡 Upload survey response data (Step 2) to enable survey validation")
    
    # Recommended Actions
    if critical_count > 0 or warning_count > 0:
        st.markdown('<div class="section-header">💡 Recommended Actions</div>', unsafe_allow_html=True)
        
        actions = []
        
        if fraud_analysis['score'] >= 3:
            actions.append("1. Review multi-person contact instances - verify they're legitimate group conversations")
        
        if data_mismatch:
            actions.append("2. Investigate data discrepancy between topline and individual records")
        
        if total_gap_time >= 2:
            actions.append("3. Address time management - identify reason for extended downtime")
        
        if abs(contact_diff_pct) > 30:
            if contact_diff_pct < 0:
                actions.append("4. Provide coaching on contact techniques to improve success rate")
            else:
                actions.append("4. Verify high contact rate is legitimate - may be exemplary or suspicious")
        
        if late_start:
            actions.append("5. Discuss punctuality and shift start expectations")
        
        if unique_doors < work_hours['door_goal']:
            actions.append("6. Set goal to increase doors knocked to meet daily targets")
        
        for action in actions:
            st.markdown(f"**{action}**")
    
    # Detailed Analysis (Collapsible)
    st.markdown("---")
    
    # Route Map Section - PROMINENT
    st.markdown('<div class="section-header">🗺️ Route Analysis</div>', unsafe_allow_html=True)
    
    # Geocode addresses if not already done
    with st.spinner("🗺️ Mapping route..."):
        address_cache = st.session_state.address_cache if st.session_state.address_cache else load_address_cache()
        geocoder = get_geocoder()
        
        # Geocode any missing addresses
        unique_addresses = df_individual['Address'].unique()
        new_addresses = [addr for addr in unique_addresses if normalize_address(addr) not in address_cache]
        
        if len(new_addresses) > 0:
            st.info(f"Geocoding {len(new_addresses)} addresses in {default_city}...")
            progress_bar = st.progress(0)
            for i, addr in enumerate(new_addresses):
                geocode_address(addr, address_cache, geocoder, default_city)
                progress_bar.progress((i + 1) / len(new_addresses))
            save_address_cache(address_cache)
            st.session_state.address_cache = address_cache
        
        # Map coordinates to dataframe
        df_individual['Coordinates'] = df_individual['Address'].apply(
            lambda x: address_cache.get(normalize_address(x))
        )
        
        # Filter out addresses without coordinates
        df_mapped = df_individual[df_individual['Coordinates'].notna()].copy()
        
        if len(df_mapped) > 0:
            # Calculate route metrics
            total_distance = 0
            backtrack_count = 0
            visited_areas = []
            
            # Previous coordinates for comparison
            df_mapped['Prev_Coordinates'] = df_mapped['Coordinates'].shift(1)
            
            route_segments = []
            
            for i in range(1, len(df_mapped)):
                current_coord = df_mapped.iloc[i]['Coordinates']
                prev_coord = df_mapped.iloc[i-1]['Coordinates']
                
                if prev_coord and current_coord:
                    # Calculate distance
                    distance = geodesic(prev_coord, current_coord).miles
                    total_distance += distance
                    
                    # Determine efficiency color
                    if distance < 0.1:  # Less than 0.1 miles (efficient)
                        color = '#10b981'
                        efficiency = 'efficient'
                    elif distance < 0.3:  # 0.1-0.3 miles (moderate)
                        color = '#fbbf24'
                        efficiency = 'moderate'
                    else:  # >0.3 miles (inefficient)
                        color = '#ef4444'
                        efficiency = 'inefficient'
                    
                    route_segments.append({
                        'from': prev_coord,
                        'to': current_coord,
                        'distance': distance,
                        'color': color,
                        'efficiency': efficiency
                    })
                    
                    # Check for backtracking
                    # If they return to an area within 0.2 miles of previous visits
                    for visited_coord in visited_areas:
                        if geodesic(current_coord, visited_coord).miles < 0.2:
                            backtrack_count += 1
                            break
                    
                    visited_areas.append(prev_coord)
            
            # Calculate optimal route (simple approximation using sorted coordinates)
            # Sort by latitude then longitude to get a rough optimal path
            coords_list = [coord for coord in df_mapped['Coordinates'] if coord]
            sorted_coords = sorted(coords_list, key=lambda x: (x[0], x[1]))
            
            optimal_distance = 0
            for i in range(1, len(sorted_coords)):
                optimal_distance += geodesic(sorted_coords[i-1], sorted_coords[i]).miles
            
            efficiency_score = (optimal_distance / total_distance * 100) if total_distance > 0 else 100
            wasted_distance = total_distance - optimal_distance
            
            # Route Metrics Cards
            route_cols = st.columns(4)
            
            with route_cols[0]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Route Efficiency</div>
                    <div class="metric-value">{efficiency_score:.0f}%</div>
                    <div class="badge badge-{'green' if efficiency_score >= 80 else 'yellow' if efficiency_score >= 60 else 'red'}">
                        {'Efficient' if efficiency_score >= 80 else 'Moderate' if efficiency_score >= 60 else 'Poor'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with route_cols[1]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Distance Walked</div>
                    <div class="metric-value">{total_distance:.1f}</div>
                    <div class="metric-label">miles</div>
                </div>
                """, unsafe_allow_html=True)
            
            with route_cols[2]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Wasted Distance</div>
                    <div class="metric-value">{wasted_distance:.1f}</div>
                    <div class="badge badge-{'green' if wasted_distance < 0.5 else 'yellow' if wasted_distance < 1.0 else 'red'}">
                        {wasted_distance/total_distance*100:.0f}% extra
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with route_cols[3]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Backtracks</div>
                    <div class="metric-value">{backtrack_count}</div>
                    <div class="badge badge-{'green' if backtrack_count < 3 else 'yellow' if backtrack_count < 6 else 'red'}">
                        revisits
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Route efficiency insights
            if efficiency_score < 60:
                st.markdown("""
                <div class="alert-box alert-critical">
                    <strong>🔴 Poor Route Efficiency</strong><br>
                    Agent walked significantly more than necessary. Review route for potential time-wasting or verify they actually walked the route.
                </div>
                """, unsafe_allow_html=True)
            elif backtrack_count >= 6:
                st.markdown("""
                <div class="alert-box alert-warning">
                    <strong>🟡 Excessive Backtracking</strong><br>
                    Agent returned to previously covered areas multiple times. May indicate poor planning or potential fraud.
                </div>
                """, unsafe_allow_html=True)
            
            # Create interactive map
            st.markdown("### Route Map")
            
            # Calculate map center
            center_lat = sum(coord[0] for coord in coords_list) / len(coords_list)
            center_lon = sum(coord[1] for coord in coords_list) / len(coords_list)
            
            fig = go.Figure()
            
            # Add route lines
            for segment in route_segments:
                fig.add_trace(go.Scattermapbox(
                    lat=[segment['from'][0], segment['to'][0]],
                    lon=[segment['from'][1], segment['to'][1]],
                    mode='lines',
                    line=dict(width=3, color=segment['color']),
                    showlegend=False,
                    hovertemplate=f"Distance: {segment['distance']:.2f} mi<br>{segment['efficiency']}<extra></extra>"
                ))
            
            # Add contact points
            for idx, row in df_mapped.iterrows():
                coord = row['Coordinates']
                contact_num = df_mapped.index.get_loc(idx) + 1
                
                # Color by result
                if row['Success']:
                    marker_color = '#10b981'
                    marker_symbol = 'circle'
                elif row['Not_Home']:
                    marker_color = '#ef4444'
                    marker_symbol = 'circle'
                else:
                    marker_color = '#fbbf24'
                    marker_symbol = 'circle'
                
                fig.add_trace(go.Scattermapbox(
                    lat=[coord[0]],
                    lon=[coord[1]],
                    mode='markers+text',
                    marker=dict(size=12, color=marker_color, symbol=marker_symbol),
                    text=str(contact_num),
                    textposition='middle center',
                    textfont=dict(size=8, color='white', family='Arial Black'),
                    showlegend=False,
                    hovertemplate=f"<b>Contact #{contact_num}</b><br>" +
                                f"Address: {row['Address']}<br>" +
                                f"Time: {row['Date Canvassed'].strftime('%I:%M%p')}<br>" +
                                f"Result: {row['Contact Result']}<extra></extra>"
                ))
            
            fig.update_layout(
                mapbox=dict(
                    style='open-street-map',
                    center=dict(lat=center_lat, lon=center_lon),
                    zoom=13
                ),
                height=600,
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Legend
            st.markdown("""
            **Map Legend:**
            - 🟢 Green pins/lines = Canvassed / Efficient route
            - 🔴 Red pins/lines = Not Home / Inefficient jumps  
            - 🟡 Yellow pins/lines = Other results / Moderate distance
            - Numbers show order of contacts (1, 2, 3...)
            """)
            
            # Pattern analysis
            with st.expander("🔍 Route Pattern Analysis"):
                st.markdown("#### Spatial Distribution")
                
                # Calculate coverage area
                lats = [coord[0] for coord in coords_list]
                lons = [coord[1] for coord in coords_list]
                
                lat_range = max(lats) - min(lats)
                lon_range = max(lons) - min(lons)
                
                # Approximate coverage area (very rough)
                coverage_area = lat_range * lon_range * 3000  # rough square miles estimate
                
                st.write(f"**Coverage Area:** ~{coverage_area:.2f} sq mi")
                st.write(f"**Density:** {unique_doors / coverage_area:.1f} doors per sq mi" if coverage_area > 0 else "N/A")
                
                # Check for clustering (tight area = suspicious)
                if coverage_area < 0.1:
                    st.markdown("""
                    <div class="alert-box alert-warning">
                        <strong>⚠️ Tight Clustering Detected</strong><br>
                        All contacts within very small area (~{:.3f} sq mi). Verify agent actually walked route vs sitting in one location.
                    </div>
                    """.format(coverage_area), unsafe_allow_html=True)
                
                # Time vs distance analysis
                st.markdown("#### Time vs Distance Analysis")
                
                suspicious_segments = []
                for i, segment in enumerate(route_segments):
                    time_gap = df_mapped.iloc[i+1]['Minutes_Between'] if i+1 < len(df_mapped) else 0
                    expected_time = segment['distance'] * 20  # 20 min per mile walking
                    
                    if time_gap < expected_time * 0.3:  # Logged much faster than possible
                        suspicious_segments.append({
                            'segment': i+1,
                            'distance': segment['distance'],
                            'time_taken': time_gap,
                            'expected': expected_time
                        })
                
                if suspicious_segments:
                    st.markdown(f"""
                    <div class="alert-box alert-critical">
                        <strong>🚨 Impossible Travel Speed Detected</strong><br>
                        {len(suspicious_segments)} route segments were logged faster than physically possible to walk
                    </div>
                    """, unsafe_allow_html=True)
                    
                    for seg in suspicious_segments[:5]:  # Show first 5
                        st.write(f"Segment #{seg['segment']}: {seg['distance']:.2f} mi in {seg['time_taken']:.1f} min (expected {seg['expected']:.1f} min)")
        
        else:
            st.warning("⚠️ Unable to geocode addresses. Showing street-based analysis instead.")
            
            # FALLBACK: Street-based analysis
            st.markdown("### 📍 Street Coverage Analysis (Fallback Mode)")
            
            # Extract street names
            df_individual['Street'] = df_individual['Address'].apply(
                lambda x: ' '.join(str(x).split()[1:]).strip() if pd.notna(x) else 'Unknown'
            )
            
            # Street coverage
            street_counts = df_individual['Street'].value_counts()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Streets Visited")
                fig = px.bar(
                    x=street_counts.index[:10],
                    y=street_counts.values[:10],
                    labels={'x': 'Street', 'y': 'Contacts'},
                    title="Top 10 Streets by Contact Count"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("#### Street Switching Pattern")
                
                # Calculate street switches
                df_individual['Prev_Street'] = df_individual['Street'].shift(1)
                df_individual['Street_Switch'] = df_individual['Street'] != df_individual['Prev_Street']
                
                total_switches = df_individual['Street_Switch'].sum()
                unique_streets = df_individual['Street'].nunique()
                optimal_switches = unique_streets - 1
                excess_switches = total_switches - optimal_switches
                
                st.metric("Total Streets", unique_streets)
                st.metric("Street Switches", total_switches)
                st.metric("Excess Switches", excess_switches, 
                         delta="Possible backtracking" if excess_switches > 5 else "Efficient")
                
                if excess_switches > 10:
                    st.markdown("""
                    <div class="alert-box alert-warning">
                        <strong>⚠️ Excessive Street Switching</strong><br>
                        Agent switched streets {0} more times than necessary. Indicates poor route planning or backtracking.
                    </div>
                    """.format(excess_switches), unsafe_allow_html=True)
            
            # Street sequence
            with st.expander("🗺️ Street Sequence Timeline"):
                street_sequence = df_individual[['Date Canvassed', 'Street', 'Address', 'Contact Result']].copy()
                street_sequence['Time'] = street_sequence['Date Canvassed'].dt.strftime('%I:%M%p')
                street_sequence = street_sequence[['Time', 'Street', 'Address', 'Contact Result']]
                st.dataframe(street_sequence, use_container_width=True, hide_index=True)
            
            st.info("💡 **Tip:** Add a 'City' column to your CSV for full route mapping with interactive maps!")
    
    with st.expander("📊 Additional Charts & Analysis", expanded=False):
        
        # Timeline
        st.markdown("### Activity Timeline")
        
        fig = go.Figure()
        
        for i in range(len(df_individual) - 1):
            current = df_individual.iloc[i]
            next_contact = df_individual.iloc[i + 1]
            
            gap_minutes = (next_contact['Date Canvassed'] - current['Date Canvassed']).total_seconds() / 60
            
            if gap_minutes < 5:
                color = '#10b981'  # Green
            elif gap_minutes < 15:
                color = '#fbbf24'  # Yellow
            elif gap_minutes < 30:
                color = '#f97316'  # Orange
            else:
                color = '#ef4444'  # Red
            
            fig.add_trace(go.Scatter(
                x=[current['Date Canvassed'], next_contact['Date Canvassed']],
                y=[1, 1],
                mode='lines',
                line=dict(color=color, width=10),
                showlegend=False,
                hovertemplate=f"{current['Date Canvassed'].strftime('%I:%M%p')} - {next_contact['Date Canvassed'].strftime('%I:%M%p')}<br>Gap: {gap_minutes:.1f} min<extra></extra>"
            ))
        
        # Add markers for each contact
        fig.add_trace(go.Scatter(
            x=df_individual['Date Canvassed'],
            y=[1] * len(df_individual),
            mode='markers',
            marker=dict(
                size=8,
                color=['#10b981' if x else '#6b7280' for x in df_individual['Success']],
                symbol='circle'
            ),
            showlegend=False,
            hovertemplate='%{x|%I:%M%p}<extra></extra>'
        ))
        
        fig.update_layout(
            title="Activity Timeline (Green=Active, Yellow=Normal, Orange=Slow, Red=Gap)",
            xaxis_title="Time",
            yaxis=dict(showticklabels=False, range=[0.5, 1.5]),
            height=200,
            margin=dict(l=20, r=20, t=40, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Contact Results
        st.markdown("### Contact Results Breakdown")
        result_counts = df_individual['Contact Result'].value_counts()
        
        fig = px.pie(
            values=result_counts.values,
            names=result_counts.index,
            title="Contact Results Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Raw data
        st.markdown("### Raw Contact Data")
        display_cols = ['Date Canvassed', 'Address', 'Contact Result', 'List Name', 'Status']
        st.dataframe(df_individual[display_cols], use_container_width=True, hide_index=True)

elif individual_file is not None and st.session_state.topline_data is None:
    st.warning("⚠️ Please upload Topline Data first to enable team comparisons.")

elif individual_file is None and st.session_state.topline_data is not None:
    st.info("👆 Upload Individual Agent Data to see detailed analysis and comparisons.")
