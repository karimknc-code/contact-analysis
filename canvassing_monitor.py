import streamlit as st
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Canvassing Monitor", layout="wide")

# Custom CSS for beautiful dark dashboard
st.markdown("""
<style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        color: #e8ecf1;
    }

    [data-testid="stSidebar"] {
        background: #0a0e15;
        border-right: 1px solid #2d3748;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        background: #0a0e15;
    }

    .metric-card {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
        border: 1px solid #4a5568;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
    }

    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
        border-color: #5a7a9e;
    }

    .metric-label {
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        color: #a0aec0;
        margin-bottom: 8px;
    }

    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #4f9ef5;
        font-family: 'Courier New', monospace;
    }

    .metric-subtitle {
        font-size: 12px;
        color: #718096;
        margin-top: 8px;
    }

    .canvasser-card {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
        border: 1px solid #4a5568;
        border-radius: 12px;
        padding: 28px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }

    .canvasser-name {
        font-size: 24px;
        font-weight: 700;
        color: #fff;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .status-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .status-committed {
        background: rgba(76, 175, 80, 0.15);
        color: #4caf50;
        border: 1px solid rgba(76, 175, 80, 0.3);
    }

    .status-pending {
        background: rgba(255, 152, 0, 0.15);
        color: #ff9800;
        border: 1px solid rgba(255, 152, 0, 0.3);
    }

    .alert-badge {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        background: rgba(244, 67, 54, 0.15);
        color: #f44336;
        border: 1px solid rgba(244, 67, 54, 0.3);
    }

    .metric-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 24px;
    }

    .performance-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin-top: 16px;
    }

    .perf-item {
        background: rgba(79, 158, 245, 0.1);
        border: 1px solid rgba(79, 158, 245, 0.2);
        border-radius: 8px;
        padding: 12px;
        text-align: center;
    }

    .perf-value {
        font-size: 20px;
        font-weight: 700;
        color: #4f9ef5;
        font-family: 'Courier New', monospace;
    }

    .perf-label {
        font-size: 11px;
        color: #a0aec0;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }

    .summary-section {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
        border: 1px solid #4a5568;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 32px;
    }

    .search-box {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
        border: 2px solid #4a5568;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 28px;
    }

    h1, h2, h3 {
        color: #fff;
    }

    h2 {
        margin-top: 0;
        margin-bottom: 24px;
        padding-bottom: 12px;
        border-bottom: 2px solid #4a5568;
        font-size: 20px;
    }

    .list-name {
        font-size: 12px;
        color: #a0aec0;
        margin-top: 8px;
        font-family: 'Courier New', monospace;
    }

    @media (max-width: 1200px) {
        .metric-row {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    @media (max-width: 768px) {
        .metric-row {
            grid-template-columns: 1fr;
        }
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    """Load canvasser data from JSON file"""
    data_path = os.path.join(os.path.dirname(__file__), 'overview_data.json')
    try:
        with open(data_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Data file not found at {data_path}")
        return None

def calculate_metrics(canvasser):
    """Calculate performance metrics for a canvasser"""
    attempts = canvasser.get('attempts', 0)
    canvassed = canvasser.get('canvassed', 0)
    refused = canvasser.get('refused', 0)

    if attempts == 0:
        return {
            'contact_rate': 0,
            'refused_rate': 0,
            'doors': canvasser.get('doors', 0)
        }

    contact_rate = (canvassed / attempts) * 100
    refused_rate = (refused / attempts) * 100

    return {
        'contact_rate': round(contact_rate, 1),
        'refused_rate': round(refused_rate, 1),
        'doors': canvasser.get('doors', 0)
    }

def get_status_color(status):
    """Return badge class for status"""
    return 'status-committed' if status == 'C' else 'status-pending'

def get_status_text(status):
    """Return human-readable status"""
    return 'Committed' if status == 'C' else 'Pending'

def needs_attention(metrics):
    """Check if canvasser needs attention"""
    return metrics['contact_rate'] < 15 or metrics['refused_rate'] > 10

# Load data
data = load_data()

if data is None:
    st.stop()

# Header
st.title("Canvassing Monitor")

# Report summary section
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Canvassers</div>
        <div class="metric-value">{data['total_records']}</div>
        <div class="metric-subtitle">Active Records</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Attempts</div>
        <div class="metric-value">{data['report_summary']['total_attempts']:,}</div>
        <div class="metric-subtitle">Combined Effort</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Doors</div>
        <div class="metric-value">{data['report_summary']['total_doors']:,}</div>
        <div class="metric-subtitle">Unique Locations</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Overall Contact Rate</div>
        <div class="metric-value">{data['report_summary']['contact_rate']}</div>
        <div class="metric-subtitle">Statewide Average</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Search functionality
st.markdown("""
<div class="search-box">
""", unsafe_allow_html=True)

search_term = st.text_input(
    "Search canvasser by name",
    placeholder="Type a name to find specific canvasser...",
    key="search_input"
)

st.markdown("</div>", unsafe_allow_html=True)

# Filter canvassers
if search_term:
    filtered_canvassers = [
        c for c in data['canvassers']
        if search_term.lower() in c['canvasser'].lower()
    ]
else:
    filtered_canvassers = []

# Display results
if search_term:
    if filtered_canvassers:
        st.subheader(f"Search Results: {len(filtered_canvassers)} match(es)")

        for canvasser in filtered_canvassers:
            metrics = calculate_metrics(canvasser)
            needs_attn = needs_attention(metrics)

            st.markdown(f"""
            <div class="canvasser-card">
                <div class="canvasser-name">
                    {canvasser['canvasser']}
                    <span class="{get_status_color(canvasser['status'])}">{get_status_text(canvasser['status'])}</span>
                    {' <span class="alert-badge">Needs Attention</span>' if needs_attn else ''}
                </div>
                <div class="list-name">{canvasser['listName']}</div>

                <div class="performance-grid">
                    <div class="perf-item">
                        <div class="perf-value">{canvasser['attempts']}</div>
                        <div class="perf-label">Attempts</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{metrics['doors']}</div>
                        <div class="perf-label">Doors</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{canvasser['canvassed']}</div>
                        <div class="perf-label">Canvassed</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{metrics['contact_rate']}%</div>
                        <div class="perf-label">Contact Rate</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{canvasser['notHome']}</div>
                        <div class="perf-label">Not Home</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{canvasser['refused']}</div>
                        <div class="perf-label">Refused</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{canvasser['moved']}</div>
                        <div class="perf-label">Moved</div>
                    </div>
                    <div class="perf-item">
                        <div class="perf-value">{metrics['refused_rate']}%</div>
                        <div class="perf-label">Refused Rate</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No canvassers found matching your search. Try another name.")
else:
    st.info("Use the search bar above to find a canvasser and view their performance metrics.")

# Sidebar - File upload and info
st.sidebar.markdown("### Survey File Upload")
uploaded_file = st.sidebar.file_uploader(
    "Upload VAN survey export (CSV)",
    type=['csv'],
    help="Upload a VAN export file to cross-reference with canvassing data"
)

if uploaded_file is not None:
    try:
        survey_df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
        st.sidebar.success(f"Loaded {len(survey_df)} survey records")

        if 'CanvassedBy' in survey_df.columns:
            canvasser_counts = survey_df['CanvassedBy'].value_counts()
            st.sidebar.write("**Survey Responses by Canvasser:**")
            st.sidebar.dataframe(canvasser_counts)
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.markdown(f"""
**Canvassing Monitor**

Sync Date: {data['sync_date']}
Scraped: {data['scraped_at']}

Total Records: {data['total_records']}

Contact Rate Threshold: <15% = Needs Attention
Refused Rate Threshold: >10% = Needs Attention
""")
