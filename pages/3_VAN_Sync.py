"""
Civic Operations Group — VAN Data Sync
One-click sync from SmartVAN Activity Report to cantrack.pro.
"""

import streamlit as st
import json
import os
import base64
import urllib.request
import urllib.error
from datetime import datetime

# ─── Page Config ───
st.set_page_config(
    page_title="VAN Sync",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───
st.markdown("""
<style>
    .main .block-container { max-width: 1000px; padding-top: 2rem; }

    .sync-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white; padding: 2rem; border-radius: 12px;
        margin-bottom: 1.5rem; text-align: center;
    }
    .sync-header h1 { color: white; margin: 0 0 0.5rem 0; font-size: 2rem; }
    .sync-header p { color: #a0aec0; margin: 0; font-size: 1rem; }

    .step-card {
        background: #1e293b; border: 1px solid #334155; border-radius: 10px;
        padding: 1.5rem; margin-bottom: 1rem; color: #e2e8f0;
    }
    .step-card h3 { color: #60a5fa; margin: 0 0 0.5rem 0; font-size: 1.1rem; }
    .step-card p { color: #94a3b8; margin: 0.3rem 0; font-size: 0.9rem; }
    .step-card code {
        background: #0f172a; color: #38bdf8; padding: 2px 8px;
        border-radius: 4px; font-size: 0.85rem;
    }

    .bookmarklet-box {
        background: #0f172a; border: 2px dashed #3b82f6; border-radius: 10px;
        padding: 1.5rem; text-align: center; margin: 1rem 0;
    }
    .bookmarklet-box a {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white !important; padding: 12px 28px; border-radius: 8px;
        font-weight: 700; font-size: 1.1rem; text-decoration: none;
        display: inline-block; cursor: grab;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
    }
    .bookmarklet-box p { color: #64748b; margin-top: 0.8rem; font-size: 0.85rem; }

    .status-success {
        background: #064e3b; border: 1px solid #059669; color: #a7f3d0;
        padding: 1rem 1.5rem; border-radius: 8px; margin: 1rem 0;
    }
    .status-error {
        background: #7f1d1d; border: 1px solid #dc2626; color: #fecaca;
        padding: 1rem 1.5rem; border-radius: 8px; margin: 1rem 0;
    }
    .status-info {
        background: #1e3a5f; border: 1px solid #3b82f6; color: #bfdbfe;
        padding: 1rem 1.5rem; border-radius: 8px; margin: 1rem 0;
    }

    .sync-history {
        background: #1e293b; border: 1px solid #334155; border-radius: 10px;
        padding: 1.5rem; color: #e2e8f0;
    }
    .sync-history h3 { color: #60a5fa; margin: 0 0 1rem 0; }

    /* Dark theme overrides */
    .stTextArea textarea {
        background: #0f172a !important; color: #e2e8f0 !important;
        border: 1px solid #334155 !important; font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
#  GITHUB PUSH LOGIC
# ═══════════════════════════════════════════════

GITHUB_REPO = "karimknc-code/contact-analysis"
GITHUB_FILE = "overview_data.json"

def get_github_token():
    """Get token from environment variable."""
    return os.environ.get("GITHUB_PAT", "")

def push_to_github(json_content, commit_message="Sync overview data from VAN"):
    """Push JSON content to GitHub repo via API."""
    token = get_github_token()
    if not token:
        return False, "GitHub token not configured. Set GITHUB_PAT environment variable."

    # First, get the current file SHA (needed for updates)
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CanTrack-Sync"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            current = json.loads(resp.read().decode())
            sha = current.get("sha", "")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sha = ""  # File doesn't exist yet
        else:
            return False, f"Error reading current file: {e.code} {e.reason}"
    except Exception as e:
        return False, f"Error: {str(e)}"

    # Push the update
    content_b64 = base64.b64encode(json_content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": commit_message,
        "content": content_b64,
        "sha": sha
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            commit_sha = result.get("commit", {}).get("sha", "unknown")[:7]
            return True, f"Pushed successfully. Commit: {commit_sha}"
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"Push failed: {e.code} {e.reason} — {body[:200]}"
    except Exception as e:
        return False, f"Push failed: {str(e)}"


def validate_overview_json(raw_text):
    """Validate that pasted JSON matches expected overview_data.json format."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {str(e)}"

    # Check required fields
    if "canvassers" not in data:
        return None, "Missing 'canvassers' array in JSON."
    if not isinstance(data["canvassers"], list):
        return None, "'canvassers' must be a list."
    if len(data["canvassers"]) == 0:
        return None, "No canvasser records found."

    # Check canvasser record structure
    required_fields = ["canvasser", "attempts", "doors"]
    sample = data["canvassers"][0]
    missing = [f for f in required_fields if f not in sample]
    if missing:
        return None, f"Canvasser records missing fields: {', '.join(missing)}"

    return data, None


def build_overview_json(canvassers):
    """Build a properly structured overview_data.json from canvasser rows."""
    total_attempts = sum(c.get("attempts", 0) for c in canvassers)
    total_doors = sum(c.get("doors", 0) for c in canvassers)
    total_canvassed = sum(c.get("canvassed", 0) for c in canvassers)
    total_not_home = sum(c.get("notHome", 0) for c in canvassers)
    contact_rate = f"{round(total_canvassed / total_attempts * 100)}%" if total_attempts > 0 else "0%"

    return {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "sync_date": datetime.now().strftime("%-m/%-d/%y"),
        "report_summary": {
            "total_attempts": total_attempts,
            "total_doors": total_doors,
            "total_canvassed": total_canvassed,
            "total_not_home": total_not_home,
            "contact_rate": contact_rate
        },
        "total_records": len(canvassers),
        "canvassers": canvassers
    }


# ═══════════════════════════════════════════════
#  BOOKMARKLET GENERATOR
# ═══════════════════════════════════════════════

BOOKMARKLET_JS = r"""
javascript:void(function(){
    var rows=document.querySelectorAll('table tbody tr');
    if(!rows.length){alert('No table found. Navigate to the Activity Report first.');return;}
    var data=[];
    rows.forEach(function(tr){
        var cells=tr.querySelectorAll('td');
        if(cells.length>=13){
            var name=cells[1]?cells[1].innerText.trim():'';
            if(!name)return;
            data.push({
                canvasser:name,
                listName:cells[0]?cells[0].innerText.trim():'',
                attempts:parseInt(cells[3]?cells[3].innerText.trim():0)||0,
                doors:parseInt(cells[4]?cells[4].innerText.trim():0)||0,
                canvassed:parseInt(cells[5]?cells[5].innerText.trim():0)||0,
                notHome:parseInt(cells[6]?cells[6].innerText.trim():0)||0,
                moved:parseInt(cells[7]?cells[7].innerText.trim():0)||0,
                refused:parseInt(cells[8]?cells[8].innerText.trim():0)||0,
                status:cells[12]?cells[12].innerText.trim():''
            });
        }
    });
    if(!data.length){alert('No rows scraped. Make sure the Activity Report table is visible.');return;}
    var prev=[];
    try{prev=JSON.parse(localStorage.getItem('cantrack_scrape')||'[]');}catch(e){}
    var merged=prev.concat(data);
    localStorage.setItem('cantrack_scrape',JSON.stringify(merged));
    var pageInfo=document.querySelector('.pager')||document.querySelector('[class*=pag]');
    var msg='Scraped '+data.length+' rows (total: '+merged.length+').\n\n';
    msg+='If more pages remain, click Next and run this bookmarklet again.\n';
    msg+='When done with all pages, click OK to copy the JSON.';
    if(confirm(msg)){
        var json=JSON.stringify(merged,null,2);
        var ta=document.createElement('textarea');
        ta.value=json;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        localStorage.removeItem('cantrack_scrape');
        alert('JSON copied to clipboard! ('+merged.length+' records)\nPaste it in the VAN Sync page on cantrack.pro.');
    }
}())
""".strip().replace('\n', '').replace('    ', '')


# ═══════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════

# Header
st.markdown("""
<div class="sync-header">
    <h1>VAN Data Sync</h1>
    <p>Sync SmartVAN Activity Report data to cantrack.pro in seconds</p>
</div>
""", unsafe_allow_html=True)

# Current sync status
data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "overview_data.json")
current_data = None
if os.path.exists(data_path):
    try:
        with open(data_path, "r") as f:
            current_data = json.load(f)
    except:
        pass

if current_data:
    sync_date = current_data.get("sync_date", "Unknown")
    scraped_at = current_data.get("scraped_at", "Unknown")
    total_records = current_data.get("total_records", 0)
    summary = current_data.get("report_summary", {})

    st.markdown(f"""
    <div class="status-info">
        <strong>Last Sync:</strong> {sync_date} &nbsp;|&nbsp;
        <strong>Records:</strong> {total_records} &nbsp;|&nbsp;
        <strong>Attempts:</strong> {summary.get('total_attempts', 0):,} &nbsp;|&nbsp;
        <strong>Contact Rate:</strong> {summary.get('contact_rate', 'N/A')}
        <br><small>Scraped: {scraped_at}</small>
    </div>
    """, unsafe_allow_html=True)

# ─── How It Works ───
st.markdown("### How It Works")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="step-card">
        <h3>Step 1: Scrape VAN</h3>
        <p>Click the bookmarklet while on SmartVAN's Activity Report. It scrapes the table and copies JSON to your clipboard.</p>
        <p><code>Handles pagination</code></p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="step-card">
        <h3>Step 2: Paste Here</h3>
        <p>Paste the JSON into the text box below and hit <strong>Push to GitHub</strong>.</p>
        <p><code>Auto-validates format</code></p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="step-card">
        <h3>Step 3: Auto-Deploy</h3>
        <p>Railway detects the GitHub push and redeploys cantrack.pro automatically. Done.</p>
        <p><code>~30 seconds</code></p>
    </div>
    """, unsafe_allow_html=True)

# ─── Bookmarklet ───
st.markdown("### Bookmarklet")
st.markdown(f"""
<div class="bookmarklet-box">
    <a href="{BOOKMARKLET_JS}" onclick="return false;">📋 Scrape VAN</a>
    <p>Drag this button to your bookmarks bar. Then click it when you're on SmartVAN's Activity Report.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="step-card">
    <h3>Pagination</h3>
    <p>The bookmarklet accumulates data across pages. Run it on each page of the Activity Report:</p>
    <p>1. Set "Show" dropdown to <code>100</code> records</p>
    <p>2. Click the bookmarklet on page 1 → click <strong>Cancel</strong> in the dialog</p>
    <p>3. Click <strong>Next</strong> to go to page 2 → click the bookmarklet again → <strong>Cancel</strong></p>
    <p>4. Repeat for page 3 → click the bookmarklet → click <strong>OK</strong> to copy all data</p>
</div>
""", unsafe_allow_html=True)

# ─── Paste & Push ───
st.markdown("### Sync Data")

paste_mode = st.radio(
    "Input mode",
    ["Paste scraped JSON (from bookmarklet)", "Paste full overview_data.json"],
    horizontal=True,
    label_visibility="collapsed"
)

json_input = st.text_area(
    "Paste JSON data here",
    height=250,
    placeholder='Paste the JSON copied by the bookmarklet, or a full overview_data.json...',
    key="json_paste"
)

col_push, col_clear = st.columns([1, 4])

with col_push:
    push_btn = st.button("🚀 Push to GitHub", type="primary", use_container_width=True)

with col_clear:
    if st.button("Clear"):
        st.session_state.json_paste = ""
        st.rerun()

if push_btn and json_input.strip():
    with st.spinner("Validating and pushing..."):
        if paste_mode == "Paste scraped JSON (from bookmarklet)":
            # Raw canvasser array from bookmarklet
            try:
                raw = json.loads(json_input.strip())
                if isinstance(raw, list):
                    # It's a raw array of canvassers
                    overview = build_overview_json(raw)
                elif isinstance(raw, dict) and "canvassers" in raw:
                    # Already structured
                    overview = raw
                    # Refresh timestamps
                    overview["scraped_at"] = datetime.utcnow().isoformat() + "Z"
                    overview["sync_date"] = datetime.now().strftime("%-m/%-d/%y")
                else:
                    st.markdown('<div class="status-error">Unexpected format. Expected array of canvassers or object with "canvassers" key.</div>', unsafe_allow_html=True)
                    st.stop()
            except json.JSONDecodeError as e:
                st.markdown(f'<div class="status-error">Invalid JSON: {e}</div>', unsafe_allow_html=True)
                st.stop()
        else:
            # Full overview_data.json
            overview, err = validate_overview_json(json_input.strip())
            if err:
                st.markdown(f'<div class="status-error">{err}</div>', unsafe_allow_html=True)
                st.stop()

        # Show preview
        n = len(overview.get("canvassers", []))
        summary = overview.get("report_summary", {})
        st.markdown(f"""
        <div class="status-info">
            <strong>Preview:</strong> {n} canvassers &nbsp;|&nbsp;
            Attempts: {summary.get('total_attempts', 0):,} &nbsp;|&nbsp;
            Doors: {summary.get('total_doors', 0):,} &nbsp;|&nbsp;
            Contact Rate: {summary.get('contact_rate', 'N/A')}
        </div>
        """, unsafe_allow_html=True)

        # Push
        json_str = json.dumps(overview, indent=2)
        ts = datetime.now().strftime("%m/%d %H:%M")
        success, msg = push_to_github(json_str, f"VAN Sync: {n} records — {ts}")

        if success:
            st.markdown(f'<div class="status-success">✅ {msg}<br>Railway will auto-deploy in ~30 seconds.</div>', unsafe_allow_html=True)
            st.balloons()
        else:
            st.markdown(f'<div class="status-error">❌ {msg}</div>', unsafe_allow_html=True)

elif push_btn:
    st.warning("Paste some JSON data first.")

# ─── Footer ───
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.85rem;">
    Civic Operations Group (NJ) — VAN Sync powered by GitHub API + Railway Auto-Deploy
</div>
""", unsafe_allow_html=True)
