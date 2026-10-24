"""
app.py - AgriPulse Smart Irrigation Advisor Dashboard
======================================================
A modern, professional AgriTech precision irrigation decision-support
dashboard matching the AgriPulse layout specifications:

1. SIDEBAR:
   - AgriPulse logo & brand
   - Navigation: Dashboard, Irrigation Advisor, Water Analytics, Irrigation History,
     Farm Management, DCDSL SQL Lab, Telemetry Simulator
   - Farm plot selector & Farm specifications card
   - Scenic farmland graphic & Simulated-data system status
2. HEADER:
   - "Smart Irrigation Advisor" title, subtitle "Data-Driven Decisions for a Greener Tomorrow"
   - "Academic Prototype" badge, active plot name, live date/time, and theme toggle (Light / Dark)
3. FARM SUMMARY:
   - Selected plot, crop, soil type, area, owner, and location
4. FOUR KPI CARDS:
   - Soil moisture with percentage and progress bar
   - Temperature in Celsius
   - Humidity percentage
   - 24-hour rainfall in millimeters
5. IRRIGATION RECOMMENDATION:
   - Recommendation title, status badge, explanation, urgency, relevant factors, and suggested next action
   - Dosage and runtime displayed only when supported by existing recommendation logic
6. SOIL MOISTURE GAUGE:
   - Circular gauge with Dry, Needs Water, Optimal, and Saturated zones, current moisture, and crop target
7. ANALYTICS:
   - 14-day water-usage bar chart with rainfall trend line
   - Monthly crop-wise water consumption donut chart with center total
8. RIGHT-SIDE COLUMN:
   - Local weather card, quick-action buttons, and recent irrigation records table
"""

import os
import shutil
import base64
import datetime
import textwrap
from typing import Dict, Any, Optional

import streamlit as st
import pandas as pd

# Optional Plotly for AgTech charts
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Backend modules
import db
from advisor import calculate_irrigation_recommendation, CROP_THRESHOLDS, SOIL_FACTORS
import mongodb_manager

# ---------------------------------------------------------------------
# Database Optimization & Cached Data Layer
# ---------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def ensure_db_initialized() -> bool:
    """Ensures SQLite tables and performance indexes are created once per process."""
    db.ensure_database_exists()
    return True

ensure_db_initialized()

@st.cache_data(ttl=60, show_spinner=False)
def get_cached_farms() -> List[Dict[str, Any]]:
    """Caches read-only list of farms for 60 seconds."""
    return db.get_all_farms()

@st.cache_data(ttl=10, show_spinner=False)
def get_cached_latest_sensor_reading(farm_id: int) -> Optional[Dict[str, Any]]:
    """Caches the latest sensor reading for a specific farm for 10 seconds."""
    row = db.get_latest_sensor_reading(farm_id)
    return dict(row) if row else None

@st.cache_data(ttl=15, show_spinner=False)
def get_cached_irrigation_history(farm_id: Optional[int] = None) -> pd.DataFrame:
    """Caches irrigation history for 15 seconds."""
    return db.get_irrigation_history(farm_id=farm_id)

@st.cache_data(ttl=15, show_spinner=False)
def get_cached_sensor_readings_history(farm_id: Optional[int] = None, limit: int = 50) -> pd.DataFrame:
    """Caches historical sensor telemetry for 15 seconds."""
    return db.get_sensor_readings_history(farm_id=farm_id, limit=limit)

@st.cache_data(ttl=30, show_spinner=False)
def get_cached_mongo_status(timeout_ms: int = 800) -> Tuple[str, str, bool]:
    """
    Caches MongoDB connectivity check for 30 seconds to prevent blocking UI on every rerun.
    Returns: (status_code, status_msg, is_connected)
    """
    return mongodb_manager.get_connection_status(timeout_ms=timeout_ms)

@st.cache_data(ttl=10, show_spinner=False)
def get_cached_latest_mongo_reading(farm_id: int) -> Optional[Dict[str, Any]]:
    """Caches latest reading from MongoDB for 10 seconds."""
    return mongodb_manager.get_latest_sensor_reading(farm_id=farm_id)

# Evaluate cached MongoDB status (takes ~0ms on reruns)
mongo_status, mongo_status_msg, mongo_connected = get_cached_mongo_status(timeout_ms=800)

# ---------------------------------------------------------------------
# 1. Page Configuration & State Setup
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="AgriPulse | Smart Irrigation Advisor",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "🏠 Dashboard"

if "selected_farm_id" not in st.session_state:
    st.session_state["selected_farm_id"] = 2  # Default to Sunrise Paddy Fields (Rice)



# Asset Management: Farmland Banner Image
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSET_DIR, exist_ok=True)
FARMLAND_IMG_PATH = os.path.join(ASSET_DIR, "scenic_farmland.jpg")
SRC_IMG_PATH = "/Users/lalitamahajan/.gemini/antigravity-ide/brain/9074f740-1cf4-4e42-aa64-a607c837def5/scenic_farmland_1792829709048.jpg"

if not os.path.exists(FARMLAND_IMG_PATH) and os.path.exists(SRC_IMG_PATH):
    try:
        shutil.copy(SRC_IMG_PATH, FARMLAND_IMG_PATH)
    except Exception:
        pass

def get_image_base64(path: str) -> str:
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
        except Exception:
            return ""
    return ""

farmland_b64 = get_image_base64(FARMLAND_IMG_PATH) or get_image_base64(SRC_IMG_PATH)

def render_html(html_str: str) -> None:
    """
    Renders custom HTML safely by stripping all leading and trailing whitespace
    from each line and joining them with spaces. This guarantees that no line has
    4 or more leading spaces, completely preventing Markdown parsers (CommonMark)
    from misinterpreting nested HTML tags or CSS as indented code blocks (<pre><code>).
    """
    clean_html = " ".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.markdown(clean_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------
# 2. Centralized Theme System (LIGHT & DARK MODE TOKENS)
# ---------------------------------------------------------------------
THEMES = {
    "light": {
        "name": "light",
        "bg": "#F4F8F3",
        "card_bg": "#FFFFFF",
        "card_border": "#E1ECE3",
        "sidebar_bg": "#164B35",
        "sidebar_border": "#1D5D43",
        "sidebar_text": "#E1ECE3",
        "sidebar_muted": "#A2C4B2",
        "sidebar_active_bg": "#FFFFFF",
        "sidebar_active_text": "#164B35",
        "sidebar_status_box": "#0E3625",
        "sidebar_status_border": "#1A523A",
        "primary_green": "#238B57",
        "accent_lime": "#10B981",
        "main_text": "#18372A",
        "secondary_text": "#4F6E5E",
        "shadow": "0 2px 8px rgba(22, 75, 53, 0.05)",
        "rec_box_bg": "#F0F7FF",
        "rec_box_border": "#CFE2FE",
        "rec_box_title": "#0F3B56",
        "rec_box_text": "#374151",
        "chart_bg": "rgba(0,0,0,0)",
        "chart_grid": "#E1ECE3",
        "chart_water_bar": "#238B57",
        "chart_rain_line": "#2563EB",
        "chart_rain_fill": "rgba(37, 99, 235, 0.15)",
        "chart_donut_colors": ["#238B57", "#D97706", "#B45309", "#9CA3AF"],
        "table_header": "#EDF5EF",
        "table_border": "#E1ECE3",
        "table_row_alt": "#F9FCFA",
        "input_bg": "#FFFFFF",
        "input_border": "#CFDDD2",
        "soil_card_bg": "#FDFAF6",
        "soil_card_border": "#EBD9C8",
        "soil_card_text": "#4B382A",
        "gauge_track": "#E5E7EB",
        "gauge_arc": "#238B57",
        "badge_yellow_bg": "#FEF3C7",
        "badge_yellow_text": "#92400E",
        "badge_yellow_border": "#FDE68A",
        "badge_green_bg": "#D1FAE5",
        "badge_green_text": "#065F46",
        "badge_green_border": "#A7F3D0",
        "badge_blue_bg": "#DBEAFE",
        "badge_blue_text": "#1E40AF",
        "badge_blue_border": "#BAE6FD",
        "badge_red_bg": "#FEE2E2",
        "badge_red_text": "#991B1B",
        "badge_red_border": "#FECACA",
        "header_overlay": "linear-gradient(90deg, #FFFFFF 62%, rgba(255,255,255,0.72) 82%)",
        "progress_track": "#E2E8F0",
        "progress_fill": "#238B57",
    },
    "dark": {
        "name": "dark",
        "bg": "#101915",
        "card_bg": "#1B2922",
        "card_border": "#283C32",
        "sidebar_bg": "#12281F",
        "sidebar_border": "#1A3B2E",
        "sidebar_text": "#F0F7F1",
        "sidebar_muted": "#A7B8AC",
        "sidebar_active_bg": "#54C783",
        "sidebar_active_text": "#0A1912",
        "sidebar_status_box": "#0A1712",
        "sidebar_status_border": "#1A3528",
        "primary_green": "#54C783",
        "accent_lime": "#B5F36B",
        "main_text": "#F0F7F1",
        "secondary_text": "#A7B8AC",
        "shadow": "0 2px 10px rgba(0, 0, 0, 0.35)",
        "rec_box_bg": "#14251F",
        "rec_box_border": "#2E4E3F",
        "rec_box_title": "#86EFAC",
        "rec_box_text": "#D1E7DD",
        "chart_bg": "rgba(0,0,0,0)",
        "chart_grid": "#24372C",
        "chart_water_bar": "#54C783",
        "chart_rain_line": "#38BDF8",
        "chart_rain_fill": "rgba(56, 189, 248, 0.20)",
        "chart_donut_colors": ["#54C783", "#FBBF24", "#F97316", "#64748B"],
        "table_header": "#15241D",
        "table_border": "#283C32",
        "table_row_alt": "#1E2F27",
        "input_bg": "#15221C",
        "input_border": "#2E473B",
        "soil_card_bg": "#1F2B24",
        "soil_card_border": "#364A3E",
        "soil_card_text": "#E2E8E4",
        "gauge_track": "#283C32",
        "gauge_arc": "#54C783",
        "badge_yellow_bg": "#362B15",
        "badge_yellow_text": "#FDE047",
        "badge_yellow_border": "#5C481A",
        "badge_green_bg": "#143825",
        "badge_green_text": "#86EFAC",
        "badge_green_border": "#1E573A",
        "badge_blue_bg": "#152C3E",
        "badge_blue_text": "#93C5FD",
        "badge_blue_border": "#1E4766",
        "badge_red_bg": "#3B1B1D",
        "badge_red_text": "#FCA5A5",
        "badge_red_border": "#632529",
        "header_overlay": "linear-gradient(90deg, #1B2922 60%, rgba(27,41,34,0.85) 85%)",
        "progress_track": "#2A3F34",
        "progress_fill": "#54C783",
    },
}

current_theme = st.session_state.get("theme", "light")
T = THEMES[current_theme]


# ---------------------------------------------------------------------
# 3. Dynamic Responsive CSS
# ---------------------------------------------------------------------
render_html(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    /* Global Typography, Overflow Prevention & Background */
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    html, body {{
        overflow-x: hidden !important;
        max-width: 100vw;
        margin: 0;
        padding: 0;
    }}
    .stApp {{
        background-color: {T['bg']} !important;
        color: {T['main_text']} !important;
        overflow-x: hidden !important;
        max-width: 100vw;
    }}
    .main .block-container {{
        padding-top: 1rem;
        padding-bottom: 2.5rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        max-width: 1380px;
        overflow-x: hidden;
    }}

    /* Global Headings */
    h1, h2, h3, h4, h5, h6 {{
        color: {T['main_text']} !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }}
    p, span, label, div {{
        color: {T['main_text']};
    }}

    /* Native Streamlit Card Container Styling */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {T['card_bg']} !important;
        border: 1px solid {T['card_border']} !important;
        border-radius: 12px !important;
        box-shadow: {T['shadow']} !important;
        margin-bottom: 0.6rem !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
        overflow: hidden;
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:hover {{
        border-color: {T['primary_green']} !important;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] > div {{
        padding: 0.85rem 1.05rem !important;
    }}

    /* Recommendation & Factors Styling */
    .rec-inner-box {{
        background-color: {T['rec_box_bg']};
        border: 1px solid {T['rec_box_border']};
        border-radius: 10px;
        padding: 0.95rem 1.15rem;
        margin-top: 0.25rem;
    }}
    .rec-kpi-bar {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin: 0.75rem 0;
        padding: 0.6rem 0.85rem;
        background: {T['card_bg']};
        border: 1px solid {T['card_border']};
        border-radius: 8px;
    }}
    .factors-box {{
        background: {T['card_bg']};
        border: 1px solid {T['card_border']};
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
        font-size: 0.82rem;
        color: {T['main_text']};
        margin-bottom: 0.5rem;
    }}
    .factors-box ul {{
        margin: 0.25rem 0 0 1.1rem;
        padding: 0;
    }}
    .factors-box li {{
        margin-bottom: 0.2rem;
        line-height: 1.35;
    }}
    .action-notice-box {{
        background: {T['table_row_alt']};
        border: 1px solid {T['card_border']};
        border-radius: 8px;
        padding: 0.65rem 0.85rem;
        font-size: 0.82rem;
        color: {T['main_text']};
        line-height: 1.35;
    }}

    /* Button Polish */
    .stButton > button {{
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.86rem !important;
        padding: 0.42rem 0.8rem !important;
        border: 1px solid {T['card_border']} !important;
        transition: all 0.15s ease !important;
    }}
    .stButton > button:hover {{
        border-color: {T['primary_green']} !important;
        transform: translateY(-1px) !important;
    }}
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {{
        background-color: {T['primary_green']} !important;
        color: #FFFFFF !important;
        border: 1px solid {T['primary_green']} !important;
        box-shadow: 0 2px 6px rgba(35, 139, 87, 0.22) !important;
    }}
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover {{
        opacity: 0.92 !important;
        color: #FFFFFF !important;
    }}
    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="baseButton-secondary"] {{
        background-color: {T['card_bg']} !important;
        color: {T['main_text']} !important;
        border: 1px solid {T['card_border']} !important;
    }}

    /* Sidebar Styling & Protection */
    [data-testid="stSidebar"] {{
        background-color: {T['sidebar_bg']} !important;
        border-right: 1px solid {T['sidebar_border']};
        pointer-events: auto !important;
        z-index: 100 !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {T['sidebar_text']};
    }}
    [data-testid="stSidebarContent"] {{
        pointer-events: auto !important;
    }}

    /* Sidebar Navigation Menu Styling */
    .sidebar-nav-label {{
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {T['sidebar_muted']};
        margin: 0.35rem 0 0.5rem 0.2rem;
    }}
    [data-testid="stSidebar"] div.stButton {{
        margin-bottom: 0.18rem !important;
    }}
    [data-testid="stSidebar"] div.stButton > button {{
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding: 0.52rem 0.85rem !important;
        border-radius: 8px !important;
        font-size: 0.92rem !important;
        line-height: 1.3 !important;
        transition: all 0.18s ease !important;
        cursor: pointer !important;
    }}
    /* Inactive Sidebar Nav Items */
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"],
    [data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-secondary"] {{
        background-color: transparent !important;
        color: {T['sidebar_muted']} !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        transform: none !important;
    }}
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover,
    [data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-secondary"]:hover {{
        background-color: rgba(255, 255, 255, 0.09) !important;
        color: #FFFFFF !important;
        border-color: rgba(255, 255, 255, 0.12) !important;
        transform: translateX(3px) !important;
    }}
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"] *,
    [data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-secondary"] * {{
        color: {T['sidebar_muted']} !important;
        font-weight: 500 !important;
        text-align: left !important;
    }}
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover * {{
        color: #FFFFFF !important;
    }}
    /* Active Sidebar Nav Item (Highlighted with green background and lime indicator) */
    [data-testid="stSidebar"] div.stButton > button[kind="primary"],
    [data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-primary"] {{
        background-color: {T['sidebar_active_bg']} !important;
        color: {T['sidebar_active_text']} !important;
        border: 1px solid {T['sidebar_active_bg']} !important;
        border-left: 4px solid {T['accent_lime']} !important;
        font-weight: 700 !important;
        box-shadow: 0 3px 8px rgba(0, 0, 0, 0.25) !important;
        transform: none !important;
    }}
    [data-testid="stSidebar"] div.stButton > button[kind="primary"] *,
    [data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-primary"] * {{
        color: {T['sidebar_active_text']} !important;
        font-weight: 700 !important;
        text-align: left !important;
    }}


    .sidebar-brand {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5rem 0 1.1rem 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
        margin-bottom: 1rem;
    }}
    .sidebar-brand-title {{
        font-size: 1.4rem;
        font-weight: 800;
        color: #ffffff;
        margin: 0;
        line-height: 1.1;
    }}
    .sidebar-brand-sub {{
        font-size: 0.76rem;
        color: {T['primary_green']};
        margin: 0;
    }}
    .sidebar-farm-box {{
        background: {T['sidebar_status_box']};
        border: 1px solid {T['sidebar_status_border']};
        border-radius: 10px;
        padding: 0.85rem;
        margin: 0.8rem 0;
        font-size: 0.82rem;
    }}
    .sidebar-art-container {{
        margin-top: 1rem;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.15);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }}
    .sidebar-status-box {{
        background-color: {T['sidebar_status_box']};
        border: 1px solid {T['sidebar_status_border']};
        border-radius: 8px;
        padding: 0.7rem 0.85rem;
        margin-top: 1rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }}

    /* Header Banner */
    .header-banner {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: {T['header_overlay']}, url('{farmland_b64}') right center / 38% no-repeat, {T['card_bg']};
        border: 1px solid {T['card_border']};
        border-radius: 14px;
        padding: 1.1rem 1.5rem;
        margin-bottom: 0.6rem;
        position: relative;
        overflow: hidden;
        box-shadow: {T['shadow']};
    }}
    .header-title-box {{
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }}
    .header-h1 {{
        font-size: 1.85rem;
        font-weight: 800;
        color: {T['main_text']};
        margin: 0;
        letter-spacing: -0.02em;
    }}
    .header-subtitle {{
        font-size: 0.92rem;
        color: {T['secondary_text']};
        margin: 0.2rem 0 0 0;
        font-weight: 500;
    }}
    .academic-pill {{
        background-color: {T['badge_yellow_bg']};
        color: {T['badge_yellow_text']};
        border: 1px solid {T['badge_yellow_border']};
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.2rem 0.65rem;
        border-radius: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .active-plot-pill {{
        background-color: {T['badge_green_bg']};
        color: {T['badge_green_text']};
        border: 1px solid {T['badge_green_border']};
        font-size: 0.78rem;
        font-weight: 700;
        padding: 0.25rem 0.7rem;
        border-radius: 12px;
    }}
    .datetime-box {{
        background: {T['card_bg']};
        border: 1px solid {T['card_border']};
        border-radius: 10px;
        padding: 0.45rem 0.85rem;
        font-size: 0.82rem;
        color: {T['main_text']};
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        box-shadow: {T['shadow']};
    }}

    /* Farm Summary Strip */
    .strip-item {{
        display: flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.35rem 0.55rem;
        border-radius: 8px;
        background: {T['table_row_alt']};
        border: 1px solid {T['card_border']};
    }}
    .strip-label {{
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        color: {T['secondary_text']};
        letter-spacing: 0.04em;
        margin-bottom: 0.1rem;
    }}
    .strip-value {{
        font-size: 0.86rem;
        font-weight: 700;
        color: {T['main_text']};
        line-height: 1.1;
    }}
    .strip-sub {{
        font-size: 0.72rem;
        color: {T['secondary_text']};
    }}

    /* Accessible Badges */
    .pill-green {{
        background-color: {T['badge_green_bg']};
        color: {T['badge_green_text']};
        border: 1px solid {T['badge_green_border']};
        padding: 0.18rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
    }}
    .pill-yellow {{
        background-color: {T['badge_yellow_bg']};
        color: {T['badge_yellow_text']};
        border: 1px solid {T['badge_yellow_border']};
        padding: 0.18rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
    }}
    .pill-blue {{
        background-color: {T['badge_blue_bg']};
        color: {T['badge_blue_text']};
        border: 1px solid {T['badge_blue_border']};
        padding: 0.18rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
    }}
    .pill-red {{
        background-color: {T['badge_red_bg']};
        color: {T['badge_red_text']};
        border: 1px solid {T['badge_red_border']};
        padding: 0.18rem 0.55rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
    }}

    .widget-title {{
        font-size: 0.88rem;
        font-weight: 700;
        color: {T['main_text']};
        margin-bottom: 0.65rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}

    /* Form Inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox > div > div {{
        background-color: {T['input_bg']} !important;
        color: {T['main_text']} !important;
        border: 1px solid {T['input_border']} !important;
        border-radius: 8px !important;
    }}
    [data-testid="stDataFrame"] {{
        background-color: {T['card_bg']} !important;
        border: 1px solid {T['card_border']} !important;
        border-radius: 8px !important;
    }}

    /* Plotly container constraint */
    .js-plotly-plot, .plot-container {{
        width: 100% !important;
        max-width: 100% !important;
    }}

    /* Mobile Responsive Stacking */
    @media (max-width: 992px) {{
        .main .block-container {{
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }}
    }}
    </style>
    """
)


# ---------------------------------------------------------------------
# 4. Farm Metadata & Synchronized Selection Mapping
# ---------------------------------------------------------------------
try:
    farms = get_cached_farms()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if not farms:
    st.error("No farms found. Please initialize the database with `python3 init_db.py`.")
    st.stop()

farm_id_list = [f["farm_id"] for f in farms]
farm_map = {f["farm_id"]: f"{f['farm_id']} - {f['name']} ({f['crop_type']})" for f in farms}
farm_label_map = {v: k for k, v in farm_map.items()}
farm_options = list(farm_label_map.keys())

# Ensure valid selected_farm_id in session state
if "selected_farm_id" not in st.session_state or st.session_state["selected_farm_id"] not in farm_id_list:
    st.session_state["selected_farm_id"] = farm_id_list[0]

current_farm_id = st.session_state["selected_farm_id"]
current_farm_label = farm_map[current_farm_id]

# Callbacks ensuring sidebar and main selectors stay 100% in sync without double-reruns
def on_sidebar_farm_change():
    chosen_label = st.session_state.get("sb_farm_select", current_farm_label)
    new_fid = farm_label_map.get(chosen_label, farm_id_list[0])
    st.session_state["selected_farm_id"] = new_fid
    st.session_state["main_farm_select"] = chosen_label

def on_main_farm_change():
    chosen_label = st.session_state.get("main_farm_select", current_farm_label)
    new_fid = farm_label_map.get(chosen_label, farm_id_list[0])
    st.session_state["selected_farm_id"] = new_fid
    st.session_state["sb_farm_select"] = chosen_label

# Enforce synchronization before rendering selectboxes
if st.session_state.get("sb_farm_select") != current_farm_label:
    st.session_state["sb_farm_select"] = current_farm_label
if st.session_state.get("main_farm_select") != current_farm_label:
    st.session_state["main_farm_select"] = current_farm_label

# Source of truth: selected_farm is fetched directly from database record
selected_farm = next(f for f in farms if f["farm_id"] == st.session_state["selected_farm_id"])



# ---------------------------------------------------------------------
# SECTION 1: SIDEBAR
# ---------------------------------------------------------------------
with st.sidebar:
    render_html(f"""
    <div class="sidebar-brand">
        <span style="font-size: 2rem;">🌱</span>
        <div>
            <div class="sidebar-brand-title">AgriPulse</div>
            <div class="sidebar-brand-sub">Smart Irrigation Advisor</div>
        </div>
    </div>
    """)

    # 1. Navigation Menu
    nav_options = [
        "🏠 Dashboard",
        "💧 Irrigation Advisor",
        "📊 Water Analytics",
        "⏱️ Irrigation History",
        "🌱 Farm Management",
        "🗄️ DCDSL SQL Lab",
        "📡 Telemetry Simulator",
    ]

    # Process programmatic nav override (e.g. from Quick Actions)
    if "nav_override" in st.session_state:
        override_target = st.session_state.pop("nav_override")
        if override_target in nav_options:
            st.session_state["active_page"] = override_target

    if "active_page" not in st.session_state or st.session_state["active_page"] not in nav_options:
        st.session_state["active_page"] = "🏠 Dashboard"

    render_html(f"""
    <div class="sidebar-nav-label">
        Navigation Menu
    </div>
    """)

    for opt in nav_options:
        is_active = (st.session_state["active_page"] == opt)
        btn_type = "primary" if is_active else "secondary"
        if st.button(
            opt,
            key=f"sb_nav_btn_{opt}",
            type=btn_type,
            use_container_width=True,
        ):
            if st.session_state["active_page"] != opt:
                st.session_state["active_page"] = opt
                st.rerun()

    nav_item = st.session_state["active_page"]

    st.markdown("---")

    # 2. Sidebar Farm Selector
    render_html("<div style='font-size: 0.85rem; font-weight: 700; color: #FFFFFF; margin-bottom: 0.3rem;'>🚜 Target Plot Selector</div>")
    st.selectbox(
        "Sidebar Farm Selector",
        options=farm_options,
        key="sb_farm_select",
        on_change=on_sidebar_farm_change,
        label_visibility="collapsed",
    )

    # 3. Sidebar Farm Details Card
    render_html(f"""
    <div class="sidebar-farm-box">
        <div style="font-weight: 700; color: #FFFFFF; font-size: 0.9rem; margin-bottom: 0.3rem;">{selected_farm['name']}</div>
        <div style="color: {T['sidebar_muted']};">• <strong>Owner:</strong> {selected_farm['owner_name']}</div>
        <div style="color: {T['sidebar_muted']};">• <strong>Location:</strong> {selected_farm['location']}</div>
        <div style="color: {T['sidebar_muted']};">• <strong>Crop:</strong> {selected_farm['crop_type']}</div>
        <div style="color: {T['sidebar_muted']};">• <strong>Area:</strong> {selected_farm['area_acres']} Acres</div>
        <div style="color: {T['sidebar_muted']};">• <strong>Soil:</strong> {selected_farm['soil_type']}</div>
    </div>
    """)

    # 4. Scenic Farmland Graphic
    if farmland_b64:
        render_html(f"""
        <div class="sidebar-art-container">
            <img src="{farmland_b64}" style="width: 100%; height: 140px; object-fit: cover; display: block;" alt="Scenic Farmland" />
        </div>
        """)

    # 5. Hybrid Database & System Status Box
    if mongo_status == "Connected":
        nosql_pill = "🍃 MongoDB Connected"
        nosql_dot = "#10B981"
        nosql_sub = "NoSQL & SQLite Synchronized"
    elif mongo_status == "Offline":
        nosql_pill = "⚠️ MongoDB Offline"
        nosql_dot = "#F59E0B"
        nosql_sub = "SQLite Fallback Active"
    else:
        nosql_pill = "⚪ MongoDB: Not Configured"
        nosql_dot = "#9CA3AF"
        nosql_sub = "Primary SQLite Active"

    render_html(f"""
    <div class="sidebar-status-box">
        <span style="font-size: 0.85rem; color: {nosql_dot};">●</span>
        <div>
            <div style="font-size: 0.82rem; font-weight: 700; color: #ffffff;">{nosql_pill}</div>
            <div style="font-size: 0.72rem; color: {T['sidebar_muted']};">{nosql_sub}</div>
        </div>
    </div>
    """)


# ---------------------------------------------------------------------
# SECTION 2: HEADER BANNER (Title, Subtitle, Badges, Date/Time & Theme)
# ---------------------------------------------------------------------
now_dt = datetime.datetime.now()
formatted_date = now_dt.strftime("%A, %d %b %Y %I:%M %p")

col_hdr_left, col_hdr_right = st.columns([2.5, 1.5])

with col_hdr_left:
    if mongo_status == "Connected":
        nosql_hdr_pill = '<span class="active-plot-pill" style="background:#D1FAE5;color:#065F46;border-color:#A7F3D0;">🍃 MongoDB Connected</span>'
    elif mongo_status == "Offline":
        nosql_hdr_pill = '<span class="academic-pill" style="background:#FEF3C7;color:#92400E;border-color:#FDE68A;">⚠️ MongoDB Offline (SQLite Fallback)</span>'
    else:
        nosql_hdr_pill = '<span class="academic-pill" style="background:#F3F4F6;color:#4B5563;border-color:#E5E7EB;">⚪ SQLite Active (NoSQL Unconfigured)</span>'

    render_html(f"""
    <div class="header-banner">
        <div class="header-title-box">
            <span style="font-size: 2.2rem; color: {T['primary_green']};">🌱</span>
            <div>
                <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
                    <h1 class="header-h1">Smart Irrigation Advisor</h1>
                    <span class="academic-pill">Academic Prototype</span>
                    <span class="active-plot-pill">Active Farm: #{selected_farm['farm_id']} - {selected_farm['name']}</span>
                    {nosql_hdr_pill}
                </div>
                <p class="header-subtitle">Data-Driven Decisions for a Greener Tomorrow</p>
            </div>
        </div>
    </div>
    """)

with col_hdr_right:
    render_html(f"""
    <div style="display: flex; gap: 0.5rem; align-items: center; justify-content: flex-end; margin-bottom: 0.5rem;">
        <div class="datetime-box">
            <span>📅</span>
            <span>{formatted_date}</span>
        </div>
    </div>
    """)

    theme_c1, theme_c2 = st.columns(2)
    with theme_c1:
        if st.button("☀️ Light Mode", use_container_width=True, type="primary" if current_theme == "light" else "secondary"):
            if current_theme != "light":
                st.session_state["theme"] = "light"
                st.rerun()

    with theme_c2:
        if st.button("🌙 Dark Mode", use_container_width=True, type="primary" if current_theme == "dark" else "secondary"):
            if current_theme != "dark":
                st.session_state["theme"] = "dark"
                st.rerun()


# ---------------------------------------------------------------------
# Telemetry Retrieval & Recommendation Computation (Hybrid NoSQL + SQLite)
# ---------------------------------------------------------------------
# Primary: Attempt reading recent telemetry from MongoDB if connected
mongo_reading = None
if mongo_connected:
    try:
        mongo_reading = get_cached_latest_mongo_reading(selected_farm["farm_id"])
    except Exception:
        mongo_reading = None

# Relational SQLite telemetry (cached with 10s TTL)
sqlite_reading = get_cached_latest_sensor_reading(selected_farm["farm_id"])

if mongo_reading:
    latest_reading = {
        "reading_id": str(mongo_reading.get("_id", "")),
        "farm_id": int(mongo_reading.get("farm_id", selected_farm["farm_id"])),
        "soil_moisture_pct": float(mongo_reading.get("soil_moisture_pct", 50.0)),
        "soil_temperature_c": float(mongo_reading.get("soil_temperature_c", 25.0)),
        "ambient_humidity_pct": float(mongo_reading.get("humidity_pct", mongo_reading.get("ambient_humidity_pct", 65.0))),
        "rainfall_last_24h_mm": float(mongo_reading.get("rainfall_mm", mongo_reading.get("rainfall_last_24h_mm", 0.0))),
        "rainfall_forecast_24h_mm": float(mongo_reading.get("rainfall_forecast_24h_mm", 0.0)),
        "is_simulated": mongo_reading.get("is_simulated", 1),
        "source": "MongoDB (NoSQL)",
    }
elif sqlite_reading:
    latest_reading = dict(sqlite_reading)
    latest_reading["source"] = "SQLite (Relational Fallback)"
else:
    latest_reading = None

farm_history_df = get_cached_irrigation_history(farm_id=selected_farm["farm_id"])
all_history_df = get_cached_irrigation_history()

crop_target = CROP_THRESHOLDS.get(selected_farm["crop_type"], {"min_moisture": 30.0, "optimal_moisture": 45.0})

if latest_reading:
    rec = calculate_irrigation_recommendation(
        soil_moisture_pct=latest_reading["soil_moisture_pct"],
        rainfall_forecast_24h_mm=latest_reading["rainfall_forecast_24h_mm"],
        rainfall_last_24h_mm=latest_reading["rainfall_last_24h_mm"],
        soil_temperature_c=latest_reading["soil_temperature_c"],
        crop_type=selected_farm["crop_type"],
        area_acres=selected_farm["area_acres"],
        soil_type=selected_farm["soil_type"],
    )
    c_moist = latest_reading["soil_moisture_pct"]
    c_temp = latest_reading["soil_temperature_c"]
    c_humid = latest_reading["ambient_humidity_pct"]
    c_rain = latest_reading["rainfall_forecast_24h_mm"]
    c_past_rain = latest_reading["rainfall_last_24h_mm"]
else:
    rec = None
    c_moist, c_temp, c_humid, c_rain, c_past_rain = 54.0, 28.2, 75.0, 25.0, 0.0


# ---------------------------------------------------------------------
# SECTION 3: FARM SUMMARY STRIP
# ---------------------------------------------------------------------
with st.container(border=True):
    strip_c1, strip_c2, strip_c3, strip_c4, strip_c5 = st.columns([1.65, 1.0, 1.1, 1.0, 1.25])

    with strip_c1:
        render_html("<div class='strip-label'>🚜 Active Plot Selection</div>")
        st.selectbox(
            "Active Plot Selection",
            options=farm_options,
            key="main_farm_select",
            on_change=on_main_farm_change,
            label_visibility="collapsed",
        )

    with strip_c2:
        render_html(f"""
        <div class="strip-item">
            <span style="font-size: 1.35rem;">🌾</span>
            <div>
                <div class="strip-label">Crop</div>
                <div class="strip-value">{selected_farm['crop_type']}</div>
                <div class="strip-sub">Target: {crop_target['min_moisture']:.0f}%</div>
            </div>
        </div>
        """)

    with strip_c3:
        retention_note = "High retention" if selected_farm['soil_type'] == 'Clay' else ("Rapid drainage" if selected_farm['soil_type'] == 'Sandy' else "Balanced")
        render_html(f"""
        <div class="strip-item">
            <span style="font-size: 1.35rem;">🧱</span>
            <div>
                <div class="strip-label">Soil Type</div>
                <div class="strip-value">{selected_farm['soil_type']}</div>
                <div class="strip-sub">({retention_note})</div>
            </div>
        </div>
        """)

    with strip_c4:
        render_html(f"""
        <div class="strip-item">
            <span style="font-size: 1.35rem;">📐</span>
            <div>
                <div class="strip-label">Area</div>
                <div class="strip-value">{selected_farm['area_acres']} Ac</div>
                <div class="strip-sub">Cultivated</div>
            </div>
        </div>
        """)

    with strip_c5:
        render_html(f"""
        <div class="strip-item">
            <span style="font-size: 1.35rem;">👤</span>
            <div>
                <div class="strip-label">Owner / Zone</div>
                <div class="strip-value">{selected_farm['owner_name']}</div>
                <div class="strip-sub">{selected_farm['location']}</div>
            </div>
        </div>
        """)


# =====================================================================
# VIEW 1: DASHBOARD (SECTIONS 4 - 8)
# =====================================================================
if nav_item == "🏠 Dashboard":

    if mongo_status == "Connected":
        st.success(f"🍃 **MongoDB NoSQL Active:** Connected to `{mongo_status_msg}`. Real-time telemetry for Plot #{selected_farm['farm_id']} is linked via NoSQL collection `sensor_readings`.")
    elif mongo_status == "Offline":
        st.warning(f"⚠️ **MongoDB Offline (SQLite Fallback Active):** Could not reach MongoDB cluster ({mongo_status_msg}). Using reliable local SQLite database. Telemetry, recommendations, and irrigation tracking continue uninterrupted.")
    else:
        st.info("ℹ️ **Database Mode (SQLite Relational Active):** `MONGODB_URI` is not configured in `.env` or Streamlit secrets. Operating seamlessly with full SQLite persistence.")

    # -----------------------------------------------------------------
    # SECTION 4: FOUR KPI METRIC CARDS
    # -----------------------------------------------------------------
    kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)

    with kpi_c1:
        with st.container(border=True):
            if c_moist < 20.0:
                m_badge = '<span class="pill-red">Critical Drought</span>'
            elif c_moist < crop_target["min_moisture"]:
                m_badge = '<span class="pill-yellow">Moderate Deficit</span>'
            elif c_moist <= 75.0:
                m_badge = '<span class="pill-green">Optimal</span>'
            else:
                m_badge = '<span class="pill-blue">Saturated</span>'

            render_html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <span style="display: flex; align-items: center; gap: 0.4rem;">
                    <span style="color: #2563EB; font-size: 1.1rem;">💧</span>
                    <span style="font-size: 0.78rem; font-weight: 700; color: {T['secondary_text']}; text-transform: uppercase; letter-spacing: 0.04em;">Soil Moisture</span>
                </span>
                <span style="font-size: 1.1rem;">🌱</span>
            </div>
            <div style="font-size: 1.95rem; font-weight: 800; color: {T['primary_green']}; letter-spacing: -0.02em; line-height: 1.1;">{c_moist:.0f}%</div>
            <div style="background: {T['progress_track']}; height: 6px; border-radius: 4px; margin: 0.5rem 0; overflow: hidden;">
                <div style="background: {T['progress_fill']}; height: 100%; width: {min(max(c_moist, 0), 100)}%;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.76rem; color: {T['secondary_text']};">
                {m_badge}
                <span>Target: {crop_target['min_moisture']:.0f}%</span>
            </div>
            """)

    with kpi_c2:
        with st.container(border=True):
            t_badge = '<span class="pill-green">Normal</span>' if 22.0 <= c_temp <= 32.0 else '<span class="pill-yellow">Warm</span>'
            temp_pct = min(max((c_temp / 45.0) * 100.0, 0.0), 100.0)
            render_html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <span style="display: flex; align-items: center; gap: 0.4rem;">
                    <span style="color: #EF4444; font-size: 1.1rem;">🌡️</span>
                    <span style="font-size: 0.78rem; font-weight: 700; color: {T['secondary_text']}; text-transform: uppercase; letter-spacing: 0.04em;">Temperature</span>
                </span>
                <span style="font-size: 1.1rem;">🌤️</span>
            </div>
            <div style="font-size: 1.95rem; font-weight: 800; color: {T['primary_green']}; letter-spacing: -0.02em; line-height: 1.1;">{c_temp:.1f}°C</div>
            <div style="background: {T['progress_track']}; height: 6px; border-radius: 4px; margin: 0.5rem 0; overflow: hidden;">
                <div style="background: #F59E0B; height: 100%; width: {temp_pct:.1f}%;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.76rem; color: {T['secondary_text']};">
                {t_badge}
                <span>Ideal: 25–30°C</span>
            </div>
            """)

    with kpi_c3:
        with st.container(border=True):
            h_badge = '<span class="pill-green">Acceptable</span>' if 60.0 <= c_humid <= 85.0 else '<span class="pill-yellow">Moderate</span>'
            humid_pct = min(max(c_humid, 0.0), 100.0)
            render_html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <span style="display: flex; align-items: center; gap: 0.4rem;">
                    <span style="color: #06B6D4; font-size: 1.1rem;">💨</span>
                    <span style="font-size: 0.78rem; font-weight: 700; color: {T['secondary_text']}; text-transform: uppercase; letter-spacing: 0.04em;">Humidity</span>
                </span>
                <span style="font-size: 1.1rem;">🌧️</span>
            </div>
            <div style="font-size: 1.95rem; font-weight: 800; color: {T['primary_green']}; letter-spacing: -0.02em; line-height: 1.1;">{c_humid:.0f}%</div>
            <div style="background: {T['progress_track']}; height: 6px; border-radius: 4px; margin: 0.5rem 0; overflow: hidden;">
                <div style="background: #06B6D4; height: 100%; width: {humid_pct:.1f}%;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.76rem; color: {T['secondary_text']};">
                {h_badge}
                <span>Ideal: 60–80%</span>
            </div>
            """)

    with kpi_c4:
        with st.container(border=True):
            r_badge = '<span class="pill-blue">Rain Expected</span>' if c_rain >= 8.0 else '<span class="pill-green">Clear</span>'
            rain_pct = min(max((c_rain / 50.0) * 100.0, 0.0), 100.0)
            render_html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <span style="display: flex; align-items: center; gap: 0.4rem;">
                    <span style="color: #3B82F6; font-size: 1.1rem;">🌧️</span>
                    <span style="font-size: 0.78rem; font-weight: 700; color: {T['secondary_text']}; text-transform: uppercase; letter-spacing: 0.04em;">24h Rainfall</span>
                </span>
                <span style="font-size: 1.1rem;">🌦️</span>
            </div>
            <div style="font-size: 1.95rem; font-weight: 800; color: {T['primary_green']}; letter-spacing: -0.02em; line-height: 1.1;">{c_rain:.1f} mm</div>
            <div style="background: {T['progress_track']}; height: 6px; border-radius: 4px; margin: 0.5rem 0; overflow: hidden;">
                <div style="background: #3B82F6; height: 100%; width: {rain_pct:.1f}%;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.76rem; color: {T['secondary_text']};">
                {r_badge}
                <span>Past 24h: {c_past_rain:.1f} mm</span>
            </div>
            """)

    # -----------------------------------------------------------------
    # TWO-COLUMN WORKSPACE: LEFT (69%) + RIGHT (31%)
    # -----------------------------------------------------------------
    main_layout_col, right_layout_col = st.columns([2.25, 1.0])

    with main_layout_col:
        # -------------------------------------------------------------
        # SECTIONS 5 & 6: RECOMMENDATION & CIRCULAR MOISTURE GAUGE
        # -------------------------------------------------------------
        rec_col, gauge_col = st.columns([1.18, 1.0])

        with rec_col:
            with st.container(border=True):
                # SECTION 5: IRRIGATION RECOMMENDATION
                if rec:
                    if rec.status_code == "POSTPONE_RAIN":
                        title_text = "Postpone Irrigation"
                        title_icon = "🌧️"
                        pill_badge = '<span class="pill-blue">POSTPONE FOR RAIN</span>'
                        summary_desc = "Significant rainfall is forecast in the next 24 hours. Soil moisture is below target but expected to improve naturally."
                        next_action = f"Hold irrigation cycle. Natural rainfall ({c_rain:.1f} mm forecast) will satisfy soil moisture demand."
                    elif rec.status_code == "IRRIGATE":
                        title_text = "Irrigation Recommended" if rec.urgency != "CRITICAL" else "Critical Irrigation Required"
                        title_icon = "💧" if rec.urgency != "CRITICAL" else "🚨"
                        pill_badge = '<span class="pill-yellow">IRRIGATE</span>' if rec.urgency != "CRITICAL" else '<span class="pill-red">CRITICAL</span>'
                        summary_desc = f"Soil moisture is below the {crop_target['min_moisture']:.0f}% threshold. Water dispensation recommended."
                        next_action = f"Dispense {rec.recommended_liters:,.0f} L via {selected_farm['crop_type']} drip network during early morning hours (~{rec.recommended_duration_min} mins runtime)."
                    elif rec.status_code == "WATERLOG_RISK":
                        title_text = "Waterlog Risk - Do Not Irrigate"
                        title_icon = "⚠️"
                        pill_badge = '<span class="pill-red">SATURATED</span>'
                        summary_desc = "Soil moisture exceeds 75% saturation barrier. Irrigation suspended to prevent root asphyxiation."
                        next_action = "Ensure field drainage channels are clear and open. Do not apply water."
                    else:
                        title_text = "Moisture Optimal"
                        title_icon = "🌿"
                        pill_badge = '<span class="pill-green">OPTIMAL</span>'
                        summary_desc = "Soil water content satisfies plant transpiration demand. Zero artificial water required."
                        next_action = "Maintain regular telemetry monitoring. No pump activation required."

                    # Conditional Dosage & Runtime (Only show when supported by existing logic: recommended_liters > 0)
                    if rec.recommended_liters > 0:
                        dosage_runtime_html = f"""
                        <div>
                            <div style="font-size: 0.7rem; color: {T['secondary_text']}; font-weight: 600;">Target Dosage</div>
                            <div style="font-size: 0.95rem; font-weight: 800; color: {T['main_text']};">💧 {rec.recommended_liters:,.0f} Liters</div>
                        </div>
                        <div>
                            <div style="font-size: 0.7rem; color: {T['secondary_text']}; font-weight: 600;">Estimated Runtime</div>
                            <div style="font-size: 0.95rem; font-weight: 800; color: {T['main_text']};">⏱️ {rec.recommended_duration_min} minutes</div>
                        </div>
                        """
                    else:
                        dosage_runtime_html = f"""
                        <div>
                            <div style="font-size: 0.7rem; color: {T['secondary_text']}; font-weight: 600;">Dispensation Status</div>
                            <div style="font-size: 0.88rem; font-weight: 700; color: {T['secondary_text']};">Equipment Offline / Suspended</div>
                        </div>
                        """

                    reasons_html = "".join([f"<li>{r}</li>" for r in rec.reasons[:3]])

                    render_html(
                        f"""
                        <div style="font-size: 0.95rem; font-weight: 700; color: {T['main_text']}; margin-bottom: 0.65rem;">
                            🌱 Irrigation Recommendation
                        </div>
                        <div class="rec-inner-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; gap: 0.5rem; flex-wrap: wrap;">
                                <div style="font-size: 1.05rem; font-weight: 800; color: {T['rec_box_title']}; display: flex; align-items: center; gap: 0.4rem;">
                                    <span>{title_icon}</span>
                                    <span>{title_text}</span>
                                </div>
                                {pill_badge}
                            </div>
                            <div style="font-size: 0.83rem; color: {T['rec_box_text']}; line-height: 1.35; margin-bottom: 0.5rem;">
                                {summary_desc}
                            </div>
                            <div class="rec-kpi-bar">
                                {dosage_runtime_html}
                                <div>
                                    <div style="font-size: 0.7rem; color: {T['secondary_text']}; font-weight: 600;">Urgency</div>
                                    <div style="font-size: 0.95rem; font-weight: 800; color: {T['primary_green']};">🔔 {rec.urgency}</div>
                                </div>
                            </div>
                            <div class="factors-box">
                                <strong style="color: {T['badge_yellow_text']};">💡 Key Factors</strong>
                                <ul>
                                    {reasons_html}
                                </ul>
                            </div>
                            <div class="action-notice-box">
                                <strong>🎯 Suggested Next Action:</strong><br>{next_action}
                            </div>
                        </div>
                        """
                    )
                else:
                    render_html(
                        f"""
                        <div style="font-size: 0.95rem; font-weight: 700; color: {T['main_text']}; margin-bottom: 0.65rem;">
                            🌱 Irrigation Recommendation
                        </div>
                        <div class="rec-inner-box">
                            <div style="font-size: 1.05rem; font-weight: 800; color: {T['rec_box_title']}; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.4rem;">
                                <span>📡</span>
                                <span>Awaiting Telemetry Reading</span>
                            </div>
                            <div style="font-size: 0.83rem; color: {T['rec_box_text']}; line-height: 1.35; margin-bottom: 0.6rem;">
                                No sensor readings currently found in SQLite for plot <strong>#{selected_farm['farm_id']} - {selected_farm['name']}</strong>.
                            </div>
                            <div class="action-notice-box">
                                <strong>🎯 Suggested Next Action:</strong><br>
                                Use the <strong>Telemetry Simulator</strong> in the sidebar or Quick Actions to inject simulated telemetry.
                            </div>
                        </div>
                        """
                    )

        with gauge_col:
            with st.container(border=True):
                # SECTION 6: SOIL MOISTURE CIRCULAR GAUGE (5 Labeled Zones)
                m_pct = min(max(c_moist, 0.0), 100.0)
                radius = 48
                circumference = 2 * 3.14159 * radius
                offset = circumference * (1 - (m_pct / 100.0))

                if m_pct < 20.0:
                    arc_color = "#EF4444"
                    active_zone_key = "dry"
                    active_zone_badge = '<span class="pill-red">Dry (0–20%)</span>'
                elif m_pct < 40.0:
                    arc_color = "#F97316"
                    active_zone_key = "needs_water"
                    active_zone_badge = '<span class="pill-yellow">Needs Water (20–40%)</span>'
                elif m_pct <= 60.0:
                    arc_color = "#EAB308" if current_theme == "light" else "#FBBF24"
                    active_zone_key = "moderate"
                    active_zone_badge = '<span class="pill-yellow">Moderate (40–60%)</span>'
                elif m_pct <= 80.0:
                    arc_color = T['primary_green']
                    active_zone_key = "optimal"
                    active_zone_badge = '<span class="pill-green">Optimal (60–80%)</span>'
                else:
                    arc_color = "#3B82F6"
                    active_zone_key = "saturated"
                    active_zone_badge = '<span class="pill-blue">Saturated (&gt;80%)</span>'

                dry_pill = '<span class="pill-red" style="font-size:0.65rem; padding: 1px 5px;">Active</span>' if active_zone_key == 'dry' else ''
                water_pill = '<span class="pill-yellow" style="font-size:0.65rem; padding: 1px 5px;">Active</span>' if active_zone_key == 'needs_water' else ''
                mod_pill = '<span class="pill-yellow" style="font-size:0.65rem; padding: 1px 5px;">Active</span>' if active_zone_key == 'moderate' else ''
                opt_pill = '<span class="pill-green" style="font-size:0.65rem; padding: 1px 5px;">Active</span>' if active_zone_key == 'optimal' else ''
                sat_pill = '<span class="pill-blue" style="font-size:0.65rem; padding: 1px 5px;">Active</span>' if active_zone_key == 'saturated' else ''

                render_html(
                    f"""
                    <div style="font-size: 0.95rem; font-weight: 700; color: {T['main_text']}; margin-bottom: 0.65rem;">
                        🌱 Soil Moisture Zone Indicator
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-around; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 0.8rem;">
                        <div style="position: relative; width: 120px; height: 120px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            <svg width="120" height="120" viewBox="0 0 120 120">
                                <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{T['gauge_track']}" stroke-width="11" />
                                <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{arc_color}" stroke-width="11"
                                    stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round"
                                    transform="rotate(-90 60 60)" />
                            </svg>
                            <div style="position: absolute; text-align: center; pointer-events: none;">
                                <div style="font-size: 1.55rem; font-weight: 800; color: {T['main_text']}; line-height: 1;">{m_pct:.0f}%</div>
                                <div style="font-size: 0.65rem; color: {T['secondary_text']}; font-weight: 600; margin-top: 2px;">Moisture</div>
                                <div style="font-size: 0.65rem; color: {T['primary_green']}; font-weight: 700; margin-top: 1px;">Target: {crop_target['min_moisture']:.0f}%</div>
                            </div>
                        </div>

                        <div style="font-size: 0.77rem; color: {T['secondary_text']}; line-height: 1.6; min-width: 135px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.35rem; padding: 1px 0;">
                                <span><span style="color: #EF4444; font-size: 0.85rem;">●</span> 0–20% <strong>Dry</strong></span>
                                {dry_pill}
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.35rem; padding: 1px 0;">
                                <span><span style="color: #F97316; font-size: 0.85rem;">●</span> 20–40% <strong>Needs Water</strong></span>
                                {water_pill}
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.35rem; padding: 1px 0;">
                                <span><span style="color: #EAB308; font-size: 0.85rem;">●</span> 40–60% <strong>Moderate</strong></span>
                                {mod_pill}
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.35rem; padding: 1px 0;">
                                <span><span style="color: {T['primary_green']}; font-size: 0.85rem;">●</span> 60–80% <strong>Optimal</strong></span>
                                {opt_pill}
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.35rem; padding: 1px 0;">
                                <span><span style="color: #3B82F6; font-size: 0.85rem;">●</span> &gt;80% <strong>Saturated</strong></span>
                                {sat_pill}
                            </div>
                        </div>
                    </div>

                    <div style="background: linear-gradient(180deg, #4ADE80 0%, #15803D 10%, #78350F 22%, #451A03 70%, #260E02 100%); height: 38px; border-radius: 8px 8px 0 0; display: flex; align-items: flex-start; justify-content: space-around; padding-top: 1px; box-shadow: inset 0 -2px 6px rgba(0,0,0,0.4);">
                        <span style="font-size: 1rem;">🌱</span>
                        <span style="font-size: 0.85rem;">🌿</span>
                        <span style="font-size: 1rem;">🌱</span>
                        <span style="font-size: 0.85rem;">🌿</span>
                        <span style="font-size: 1rem;">🌱</span>
                    </div>

                    <div style="background: {T['soil_card_bg']}; border: 1px solid {T['soil_card_border']}; border-top: none; border-radius: 0 0 8px 8px; padding: 0.65rem 0.85rem; font-size: 0.78rem; color: {T['soil_card_text']};">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem; flex-wrap: wrap; gap: 0.3rem;">
                            <span><strong>Crop:</strong> {selected_farm['crop_type']}</span>
                            <span><strong>Soil:</strong> {selected_farm['soil_type']} ({retention_note})</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.3rem;">
                            <span><strong>Target:</strong> {crop_target['min_moisture']:.0f}%</span>
                            <span><strong>Status:</strong> {active_zone_badge}</span>
                        </div>
                    </div>
                    """
                )

        # -------------------------------------------------------------
        # SECTION 7: ANALYTICS (14-DAY TREND & CROP DONUT CHART)
        # -------------------------------------------------------------
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            with st.container(border=True):
                render_html(
                    f"""
                    <div style="font-size: 0.92rem; font-weight: 700; color: {T['main_text']}; margin-bottom: 0.5rem;">
                        📊 Water Usage Trend (Last 14 Days)
                    </div>
                    """
                )

                # 14-day rolling window
                today_date = datetime.date.today()
                dates_14 = [today_date - datetime.timedelta(days=i) for i in range(13, -1, -1)]
                x_labels = [d.strftime("%b %d") for d in dates_14]
                iso_keys = [d.strftime("%Y-%m-%d") for d in dates_14]
                iso_to_label = dict(zip(iso_keys, x_labels))

                water_by_label = {lbl: 0.0 for lbl in x_labels}
                rain_by_label = {lbl: 0.0 for lbl in x_labels}

                # Map real irrigation history from SQLite for the active plot
                if not farm_history_df.empty:
                    for _, row in farm_history_df.iterrows():
                        try:
                            r_ts = pd.to_datetime(row["timestamp"])
                            iso_d = r_ts.strftime("%Y-%m-%d")
                            if iso_d in iso_to_label:
                                lbl = iso_to_label[iso_d]
                                water_by_label[lbl] += float(row["water_volume_liters"])
                        except Exception:
                            pass

                # Map real sensor telemetry readings for rainfall for the active plot
                farm_readings_df = get_cached_sensor_readings_history(farm_id=selected_farm["farm_id"], limit=50)
                if not farm_readings_df.empty:
                    for _, row in farm_readings_df.iterrows():
                        try:
                            r_ts = pd.to_datetime(row["timestamp"])
                            iso_d = r_ts.strftime("%Y-%m-%d")
                            if iso_d in iso_to_label:
                                lbl = iso_to_label[iso_d]
                                rain_val = float(row.get("rainfall_forecast_24h_mm", 0.0) or row.get("rainfall_last_24h_mm", 0.0) or 0.0)
                                rain_by_label[lbl] = max(rain_by_label[lbl], rain_val)
                        except Exception:
                            pass

                # Reflect today's active forecast
                today_lbl = today_date.strftime("%b %d")
                if today_lbl in rain_by_label:
                    rain_by_label[today_lbl] = max(rain_by_label[today_lbl], float(c_rain))

                y_water = [water_by_label[lbl] for lbl in x_labels]
                y_rain = [rain_by_label[lbl] for lbl in x_labels]

                if HAS_PLOTLY:
                    fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_trend.add_trace(
                        go.Bar(
                            x=x_labels,
                            y=y_water,
                            name="Water Used (L)",
                            marker_color=T["chart_water_bar"],
                            opacity=0.88,
                        ),
                        secondary_y=False,
                    )
                    fig_trend.add_trace(
                        go.Scatter(
                            x=x_labels,
                            y=y_rain,
                            name="Rainfall (mm)",
                            mode="lines+markers",
                            line=dict(color=T["chart_rain_line"], width=2.5, shape="spline"),
                            marker=dict(size=5, color=T["chart_rain_line"]),
                            fill="tozeroy",
                            fillcolor=T["chart_rain_fill"],
                        ),
                        secondary_y=True,
                    )
                    fig_trend.update_layout(
                        height=240,
                        margin=dict(l=10, r=10, t=20, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10, color=T["main_text"])),
                        paper_bgcolor=T["chart_bg"],
                        plot_bgcolor=T["chart_bg"],
                        font=dict(color=T["main_text"], family="Plus Jakarta Sans"),
                    )
                    fig_trend.update_xaxes(showgrid=False, tickfont=dict(color=T["secondary_text"]))
                    fig_trend.update_yaxes(title_text="Water (L)", secondary_y=False, showgrid=True, gridcolor=T["chart_grid"], title_font=dict(size=9, color=T["secondary_text"]), tickfont=dict(color=T["secondary_text"]))
                    fig_trend.update_yaxes(title_text="Rain (mm)", secondary_y=True, showgrid=False, title_font=dict(size=9, color=T["secondary_text"]), tickfont=dict(color=T["secondary_text"]))
                    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.bar_chart(pd.DataFrame({"Water Used (L)": y_water}, index=x_labels), color=T["chart_water_bar"])

        with chart_col2:
            with st.container(border=True):
                render_html(
                    f"""
                    <div style="font-size: 0.92rem; font-weight: 700; color: {T['main_text']}; margin-bottom: 0.5rem;">
                        🌱 Water Usage by Crop (This Month)
                    </div>
                    """
                )

                if not all_history_df.empty:
                    crop_grp = all_history_df.groupby("crop_type")["water_volume_liters"].sum().reset_index()
                    tot_vol = float(crop_grp["water_volume_liters"].sum())
                    crop_labels = crop_grp["crop_type"].tolist()
                    crop_vals = crop_grp["water_volume_liters"].tolist()
                else:
                    tot_vol = 0.0
                    crop_labels = []
                    crop_vals = []

                if HAS_PLOTLY and tot_vol > 0:
                    fig_donut = go.Figure(
                        data=[
                            go.Pie(
                                labels=crop_labels,
                                values=crop_vals,
                                hole=0.68,
                                marker=dict(colors=T["chart_donut_colors"], line=dict(color=T["card_bg"], width=2)),
                                textinfo="percent",
                                textfont=dict(size=11, color="#FFFFFF"),
                                hoverinfo="label+value+percent",
                            )
                        ]
                    )
                    fig_donut.add_annotation(
                        text=f"<b>{tot_vol:,.0f} L</b><br><span style='font-size:10px;color:{T['secondary_text']};font-weight:600;'>Total Volume</span>",
                        x=0.5,
                        y=0.5,
                        font_size=13,
                        font_color=T["main_text"],
                        showarrow=False,
                    )
                    fig_donut.update_layout(
                        height=240,
                        margin=dict(l=10, r=10, t=20, b=20),
                        showlegend=True,
                        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02, font=dict(size=10, color=T["main_text"])),
                        paper_bgcolor=T["chart_bg"],
                        font=dict(color=T["main_text"], family="Plus Jakarta Sans"),
                    )
                    st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
                elif tot_vol > 0:
                    st.dataframe(pd.DataFrame({"Crop": crop_labels, "Volume (L)": crop_vals}), hide_index=True, use_container_width=True)
                else:
                    render_html(
                        f"""
                        <div style="text-align: center; padding: 3rem 1rem; color: {T['secondary_text']}; font-size: 0.88rem;">
                            🌱 No irrigation events logged in SQLite yet.<br>
                            <span style="font-size:0.75rem;">Log an event in '⏱️ Irrigation History' to view crop breakdown.</span>
                        </div>
                        """
                    )

    # -----------------------------------------------------------------
    # SECTION 8: RIGHT-SIDE COLUMN (WEATHER, ACTIONS, RECENT RECORDS)
    # -----------------------------------------------------------------
    with right_layout_col:
        # Weather Card
        with st.container(border=True):
            render_html(
                f"""
                <div class="widget-title" style="margin-bottom: 0.6rem;">
                    <span>📍 Local Weather</span>
                    <span style="font-size: 0.78rem; color: {T['secondary_text']};">{selected_farm['location']}</span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.8rem;">
                    <div>
                        <div style="font-size: 2rem; font-weight: 800; color: {T['main_text']}; line-height: 1;">{c_temp:.0f}°C</div>
                        <div style="font-size: 0.82rem; color: {T['secondary_text']}; font-weight: 600; margin-top: 0.2rem;">{'Rain Forecast' if c_rain > 8.0 else 'Partly Sunny'}</div>
                    </div>
                    <span style="font-size: 2.3rem;">{'🌧️' if c_rain > 8.0 else '⛅'}</span>
                </div>
                <div style="font-size: 0.8rem; color: {T['secondary_text']}; border-top: 1px solid {T['card_border']}; padding-top: 0.6rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                        <span>💧 Humidity</span>
                        <strong style="color: {T['main_text']};">{c_humid:.0f}%</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                        <span>💨 Wind</span>
                        <strong style="color: {T['main_text']};">8 km/h</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>🌧️ Precipitation</span>
                        <strong style="color: {T['main_text']};">{min(int(c_rain * 2), 85)}%</strong>
                    </div>
                </div>
                """
            )

        # Quick Actions
        with st.container(border=True):
            render_html(
                f"""
                <div class="widget-title" style="margin-bottom: 0.6rem;">
                    <span>⚡ Quick Actions</span>
                </div>
                """
            )
            if st.button("💧 Record Irrigation", use_container_width=True, type="primary"):
                st.session_state["active_page"] = "⏱️ Irrigation History"
                st.rerun()

            if st.button("📊 View Analytics", use_container_width=True):
                st.session_state["active_page"] = "📊 Water Analytics"
                st.rerun()

            if st.button("🗺️ Manage Farm Plots", use_container_width=True):
                st.session_state["active_page"] = "🌱 Farm Management"
                st.rerun()

            if st.button("🗄️ Run SQL Queries", use_container_width=True):
                st.session_state["active_page"] = "🗄️ DCDSL SQL Lab"
                st.rerun()

            if st.button("📡 Simulate New Reading", use_container_width=True):
                st.session_state["active_page"] = "📡 Telemetry Simulator"
                st.rerun()

        # Recent Irrigation Records Table
        with st.container(border=True):
            render_html(
                f"""
                <div class="widget-title" style="margin-bottom: 0.5rem;">
                    <span>⏱️ Recent Irrigation Records</span>
                    <span style="font-size: 0.74rem; color: {T['primary_green']}; font-weight: 700;">#{selected_farm['farm_id']} {selected_farm['name']}</span>
                </div>
                """
            )

            if not farm_history_df.empty:
                recent_rows = farm_history_df.head(5).copy()
                recent_display = pd.DataFrame({
                    "Date": pd.to_datetime(recent_rows["timestamp"]).dt.strftime("%d %b"),
                    "Water": recent_rows["water_volume_liters"].apply(lambda v: f"{v:,.0f} L"),
                    "Crop": recent_rows["crop_type"],
                    "Method": recent_rows["irrigation_method"]
                })
                st.dataframe(recent_display, use_container_width=True, hide_index=True)
            else:
                render_html(
                    f"""
                    <div style="text-align: center; color: {T['secondary_text']}; padding: 1rem 0.5rem; font-size: 0.8rem;">
                        No irrigation records found for this plot.<br>
                        <span style="font-size: 0.74rem; color: {T['primary_green']};">Use '💧 Record Irrigation' above to add an entry.</span>
                    </div>
                    """
                )


# =====================================================================
# VIEW 2: IRRIGATION ADVISOR (EXPLAINABILITY DEEP-DIVE)
# =====================================================================
elif nav_item == "💧 Irrigation Advisor":
    st.markdown("### 💧 Irrigation Advisor: Explainable Agronomic Logic")
    st.markdown(f"**Target Plot:** `#{selected_farm['farm_id']} - {selected_farm['name']} ({selected_farm['crop_type']})`")

    if not rec or not latest_reading:
        st.warning("No telemetry data found for this farm. Add readings in the Telemetry Simulator.")
    else:
        ad_col1, ad_col2 = st.columns([1.5, 1.0])
        with ad_col1:
            with st.container(border=True):
                render_html(
                    f"""
                    <div style="font-size: 1.15rem; font-weight: 800; color: {T['main_text']}; margin-bottom: 0.25rem;">
                        {rec.status_title}
                    </div>
                    <div style="font-size: 0.85rem; color: {T['secondary_text']}; margin-bottom: 0.6rem;">
                        Urgency Level: <strong style="color: {T['primary_green']};">{rec.urgency}</strong>
                    </div>
                    <div style="background: {T['rec_box_bg']}; border: 1px solid {T['rec_box_border']}; padding: 0.75rem 1rem; border-radius: 8px; margin: 0.6rem 0;">
                        <strong>Target Volume:</strong> {rec.recommended_liters:,.0f} Liters &nbsp;&bull;&nbsp;
                        <strong>Runtime:</strong> {rec.recommended_duration_min} minutes
                    </div>
                    <div style="font-size: 0.95rem; font-weight: 700; color: {T['main_text']}; margin: 0.8rem 0 0.4rem 0;">
                        Step-by-Step Reason Trace
                    </div>
                    """
                )
                for r in rec.reasons:
                    st.markdown(f"- {r}")

        with ad_col2:
            with st.container(border=True):
                st.markdown("#### Formal Rule Trace")
                st.json(rec.rules_fired)
                st.markdown("#### Sensor Telemetry Snapshot")
                st.json(rec.metrics_snapshot)


# =====================================================================
# VIEW 3: WATER ANALYTICS
# =====================================================================
elif nav_item == "📊 Water Analytics":
    st.markdown("### 📊 Comprehensive Water Analytics")
    if all_history_df.empty:
        st.info("No recorded irrigation events found.")
    else:
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Total Fleet Volume Dispensed", f"{all_history_df['water_volume_liters'].sum():,.0f} L")
        with k2:
            st.metric("Total Irrigation Events", f"{len(all_history_df)}")
        with k3:
            st.metric("Average Event Volume", f"{all_history_df['water_volume_liters'].mean():,.0f} L")

        st.markdown("---")
        st.markdown("#### Complete Irrigation History Log")
        st.dataframe(all_history_df, use_container_width=True, hide_index=True)


# =====================================================================
# VIEW 4: IRRIGATION HISTORY & LOG WATER DISPENSATION
# =====================================================================
elif nav_item == "⏱️ Irrigation History":
    st.markdown("### ⏱️ Irrigation History & Water Logging")

    with st.expander("➕ Log New Water Dispensation Event", expanded=True):
        with st.form("quick_record_form", clear_on_submit=True):
            f_log_id = st.selectbox(
                "Farm Plot:",
                options=[f["farm_id"] for f in farms],
                format_func=lambda x: next(f"{f['name']} ({f['crop_type']})" for f in farms if f["farm_id"] == x),
                index=[f["farm_id"] for f in farms].index(selected_farm["farm_id"]),
            )
            c_w1, c_w2 = st.columns(2)
            with c_w1:
                w_vol = st.number_input("Water Volume (Liters):", min_value=1.0, value=20000.0, step=500.0)
                w_method = st.selectbox("Method:", ["Drip", "Sprinkler", "Surface/Flood", "Subsurface"])
            with c_w2:
                w_dur = st.number_input("Duration (Minutes):", min_value=1, value=90)
                w_rec = st.checkbox("Conformed with system recommendation", value=True)

            w_notes = st.text_input("Notes:", placeholder="e.g. Regular scheduled cycle.")
            if st.form_submit_button("💾 Save Irrigation Record", use_container_width=True):
                try:
                    eid = db.record_irrigation_event(
                        farm_id=f_log_id,
                        water_volume_liters=w_vol,
                        irrigation_method=w_method,
                        duration_minutes=w_dur,
                        recommended_by_system=1 if w_rec else 0,
                        notes=w_notes,
                    )
                    st.cache_data.clear()
                    st.session_state["selected_farm_id"] = f_log_id
                    st.success(f"Irrigation Event #{eid} successfully logged!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

    st.markdown("#### Historical Records Table")
    st.dataframe(all_history_df, use_container_width=True, hide_index=True)


# =====================================================================
# VIEW 5: FARM MANAGEMENT
# =====================================================================
elif nav_item == "🌱 Farm Management":
    st.markdown("### 🌱 Farm Management")
    st.markdown("Register and inspect agricultural plots in the SQLite database.")

    with st.expander("➕ Register New Agricultural Plot", expanded=False):
        with st.form("new_farm_form", clear_on_submit=True):
            fn1, fn2 = st.columns(2)
            with fn1:
                n_name = st.text_input("Farm Name:", placeholder="e.g. Riverbend Agro")
                n_owner = st.text_input("Owner Name:", placeholder="e.g. Priya Sharma")
                n_loc = st.text_input("Location / Zone:", placeholder="e.g. Zone G - North Valley")
            with fn2:
                n_crop = st.selectbox("Primary Crop:", ["Tomato", "Rice", "Wheat", "Cotton", "Maize"])
                n_area = st.number_input("Cultivated Area (Acres):", min_value=0.1, value=3.0, step=0.5)
                n_soil = st.selectbox("Soil Type:", ["Loamy", "Clay", "Sandy", "Silt", "Peaty"])

            if st.form_submit_button("🌱 Register Farm Plot", use_container_width=True):
                try:
                    if not n_name or not n_owner:
                        st.error("Farm name and owner name are required.")
                    else:
                        new_id = db.add_farm(n_name, n_owner, n_loc, n_crop, n_area, n_soil)
                        # Add initial baseline simulated sensor reading for the new plot
                        crop_conf = CROP_THRESHOLDS.get(n_crop, {"min_moisture": 30.0, "optimal_moisture": 45.0})
                        db.add_sensor_reading(
                            farm_id=new_id,
                            soil_moisture_pct=crop_conf["optimal_moisture"],
                            soil_temperature_c=26.5,
                            ambient_humidity_pct=65.0,
                            rainfall_last_24h_mm=0.0,
                            rainfall_forecast_24h_mm=0.0,
                            is_simulated=1,
                        )
                        st.cache_data.clear()
                        st.session_state["selected_farm_id"] = new_id
                        st.success(f"Farm #{new_id} ({n_name}) registered successfully with baseline telemetry!")
                        st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

    st.dataframe(pd.DataFrame(farms), use_container_width=True, hide_index=True)


# =====================================================================
# VIEW 6: DCDSL DATABASE LABORATORY (SQL & MONGODB)
# =====================================================================
elif nav_item == "🗄️ DCDSL SQL Lab":
    st.markdown("### 🗄️ DCDSL Database Laboratory: Polyglot Query Studio")
    st.caption("Comprehensive hands-on database laboratory covering advanced SQL relational operations and MongoDB NoSQL aggregation pipelines.")

    lab_t1, lab_t2, lab_t3, lab_t4, lab_t5, lab_t6 = st.tabs([
        "🔗 1. SQL JOINs",
        "📊 2. GROUP BY & HAVING",
        "🎯 3. Subqueries",
        "📈 4. SQL Aggregates",
        "🍃 5. MongoDB CRUD",
        "⚡ 6. MongoDB Aggregations",
    ])

    # -------------------------------------------------------------
    # TAB 1: SQL JOIN QUERIES
    # -------------------------------------------------------------
    with lab_t1:
        st.markdown("#### 🔗 Relational SQL JOIN Queries")
        st.markdown("Demonstrates multi-table correlation between master farm records, sensor readings, and water dispensation history.")

        j_c1, j_c2 = st.columns([1.5, 1.5])
        with j_c1:
            join_type_choice = st.radio("Select JOIN Technique:", ["LEFT OUTER JOIN (Farms ➜ Irrigation History)", "INNER JOIN (Farms ➜ Telemetry Readings)"], horizontal=True)
        with j_c2:
            crop_filter_list = ["All Crops"] + sorted(list({f["crop_type"] for f in farms}))
            selected_crop_join = st.selectbox("Filter by Crop:", crop_filter_list, key="join_crop_sel")

        is_inner = "INNER" in join_type_choice
        sql_join_code, df_join = db.run_join_query_demo(
            join_type="INNER" if is_inner else "LEFT",
            crop_type=selected_crop_join if selected_crop_join != "All Crops" else None,
        )

        if is_inner:
            st.info("💡 **Concept:** `INNER JOIN` returns only records that have matching keys in **both** tables (`farms` and `sensor_readings`). Farms without telemetry readings are excluded.")
        else:
            st.info("💡 **Concept:** `LEFT OUTER JOIN` retains **all** records from the left table (`farms`), populating NULLs for farms that have not yet logged irrigation events in `irrigation_history`.")

        st.code(sql_join_code, language="sql")

        if st.button("▶️ Execute JOIN Query Live", key="btn_exec_join"):
            try:
                if not df_join.empty:
                    st.dataframe(df_join, use_container_width=True, hide_index=True)
                    st.caption(f"Retrieved {len(df_join)} row(s) from SQLite database.")
                else:
                    st.warning("No matching records found for the selected filter.")
            except Exception as e:
                st.error(f"Execution Error: {e}")

    # -------------------------------------------------------------
    # TAB 2: GROUP BY AND HAVING
    # -------------------------------------------------------------
    with lab_t2:
        st.markdown("#### 📊 GROUP BY and HAVING Clause Outlier Filtering")
        st.markdown("Demonstrates aggregating metrics across plots and applying post-aggregation filters using `HAVING`.")

        gh_c1, gh_c2 = st.columns([1.5, 1.5])
        with gh_c1:
            min_thresh_slider = st.slider("Minimum Total Water Consumed (Liters):", 5000.0, 40000.0, 15000.0, step=2500.0)
        with gh_c2:
            gh_crop_filter = st.selectbox("Crop Filter:", ["All Crops"] + sorted(list({f["crop_type"] for f in farms})), key="gh_crop_sel")

        sql_gh_code, df_gh = db.run_groupby_having_demo(
            min_water_liters=min_thresh_slider,
            crop_type=gh_crop_filter if gh_crop_filter != "All Crops" else None,
        )

        st.info("💡 **Concept:** `WHERE` filters rows **before** aggregation, whereas `HAVING` filters grouped summaries **after** aggregation. Here, `HAVING SUM(water_volume_liters) >= ?` isolates heavy-consumption outliers.")
        st.code(sql_gh_code, language="sql")

        if st.button("▶️ Execute GROUP BY & HAVING Query", key="btn_exec_gh"):
            try:
                if not df_gh.empty:
                    st.dataframe(df_gh, use_container_width=True, hide_index=True)
                    st.caption(f"Identified {len(df_gh)} outlier farm(s) consuming >= {min_thresh_slider:,.0f} L.")
                else:
                    st.warning(f"No farms found exceeding the threshold of {min_thresh_slider:,.0f} Liters.")
            except Exception as e:
                st.error(f"Execution Error: {e}")

    # -------------------------------------------------------------
    # TAB 3: SUBQUERIES
    # -------------------------------------------------------------
    with lab_t3:
        st.markdown("#### 🎯 Advanced Subqueries (Correlated, HAVING, & Derived Tables)")

        sub_choice = st.selectbox(
            "Select Subquery Architecture:",
            [
                ("correlated", "1. Correlated Subquery in SELECT (Latest Telemetry Snapshot)"),
                ("having_subquery", "2. Subquery in HAVING (Below Fleet-Average Moisture)"),
                ("nested_derived_table", "3. Nested Derived Table (Liters/Acre & Fleet Intensity Variance)"),
            ],
            format_func=lambda x: x[1],
        )

        sql_sub_code, df_sub = db.run_subquery_demo(subquery_type=sub_choice[0])

        if sub_choice[0] == "correlated":
            st.info("💡 **Concept:** The subquery in the `SELECT` clause executes once for each candidate farm row in the outer query (`WHERE s.farm_id = f.farm_id`), retrieving the latest sensor telemetry without requiring window functions.")
        elif sub_choice[0] == "having_subquery":
            st.info("💡 **Concept:** An aggregate subquery `(SELECT AVG(soil_moisture_pct) FROM sensor_readings)` dynamically calculates the fleet-wide moisture baseline, allowing the `HAVING` clause to filter for deficit plots.")
        else:
            st.info("💡 **Concept:** The inner derived table `farm_metrics` computes per-farm Liters/Acre intensity; the outer query evaluates each farm's deviation against the global average intensity.")

        st.code(sql_sub_code, language="sql")

        if st.button("▶️ Execute Subquery Demonstration", key="btn_exec_sub"):
            try:
                if not df_sub.empty:
                    st.dataframe(df_sub, use_container_width=True, hide_index=True)
                    st.caption(f"Returned {len(df_sub)} row(s) from SQLite subquery.")
                else:
                    st.warning("No records matched the subquery conditions.")
            except Exception as e:
                st.error(f"Subquery Execution Error: {e}")

    # -------------------------------------------------------------
    # TAB 4: SQL AGGREGATE FUNCTIONS
    # -------------------------------------------------------------
    with lab_t4:
        st.markdown("#### 📈 SQL Aggregate Functions (COUNT, SUM, AVG, MIN, MAX)")
        st.markdown("Computes statistical telemetry metrics across all sensors or isolated to a specific plot.")

        agg_farm_opts = {"All Fleet Sensors": None}
        for f in farms:
            agg_farm_opts[f"#{f['farm_id']} - {f['name']} ({f['crop_type']})"] = f["farm_id"]
        sel_agg_farm = st.selectbox("Scope of Aggregation:", options=list(agg_farm_opts.keys()), key="agg_farm_sel")

        sql_agg_code, df_agg = db.run_aggregates_demo(farm_id=agg_farm_opts[sel_agg_farm])

        st.info("💡 **Concept:** Demonstrates scalar aggregation returning aggregate statistics: `COUNT()` of telemetry pings, `AVG()` moisture and temperature, `MIN()`/`MAX()` moisture extremes, and `SUM()` recorded precipitation.")
        st.code(sql_agg_code, language="sql")

        if st.button("▶️ Execute Aggregate Query Live", key="btn_exec_agg"):
            try:
                if not df_agg.empty:
                    st.dataframe(df_agg, use_container_width=True, hide_index=True)
                else:
                    st.warning("No telemetry records found for aggregation.")
            except Exception as e:
                st.error(f"Execution Error: {e}")

    # -------------------------------------------------------------
    # TAB 5: MONGODB CRUD OPERATIONS
    # -------------------------------------------------------------
    with lab_t5:
        st.markdown("#### 🍃 MongoDB NoSQL CRUD Operations")
        if mongo_connected:
            st.success(f"✅ **MongoDB Active:** Connected to `{mongo_status_msg}`")
        else:
            st.warning(f"⚠️ **MongoDB Offline / Not Connected:** {mongo_status_msg}")
            st.caption("Configure `MONGODB_URI` in `.env` to execute live write/delete operations against MongoDB.")

        crud_tab_c, crud_tab_r, crud_tab_u, crud_tab_d = st.tabs(["➕ Create (Insert)", "📖 Read (Query)", "✏️ Update", "🗑️ Delete"])

        with crud_tab_c:
            st.markdown("##### ➕ Create: Insert Document into `sensor_readings`")
            st.code("""
# PyMongo Document Insertion:
doc = {
    "farm_id": int(farm_id),
    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "soil_moisture_pct": float(soil_moisture),
    "soil_temperature_c": float(soil_temperature),
    "humidity_pct": float(humidity),
    "rainfall_mm": float(rainfall_last_24h),
    "is_simulated": 1
}
result = db.sensor_readings.insert_one(doc)
            """, language="python")

            with st.form("crud_insert_form"):
                ins_f = st.selectbox("Target Plot:", options=[f["farm_id"] for f in farms], format_func=lambda x: next(f"#{f['farm_id']} - {f['name']}" for f in farms if f["farm_id"] == x))
                ci1, ci2 = st.columns(2)
                with ci1:
                    ins_sm = st.slider("Soil Moisture (%)", 0.0, 100.0, 38.0, 0.5, key="ci_sm")
                    ins_st = st.slider("Soil Temperature (°C)", 10.0, 50.0, 28.0, 0.5, key="ci_st")
                with ci2:
                    ins_sh = st.slider("Humidity (%)", 0.0, 100.0, 70.0, 1.0, key="ci_sh")
                    ins_rf = st.slider("Rainfall (mm)", 0.0, 50.0, 0.0, 0.5, key="ci_rf")

                if st.form_submit_button("▶️ Execute Insert Document", use_container_width=True, type="primary"):
                    if not mongo_connected:
                        st.error("Operation failed: MongoDB is offline. Configure MONGODB_URI in .env.")
                    else:
                        try:
                            doc_id = mongodb_manager.insert_sensor_reading(
                                farm_id=ins_f,
                                soil_moisture_pct=ins_sm,
                                soil_temperature_c=ins_st,
                                humidity_pct=ins_sh,
                                rainfall_mm=ins_rf,
                            )
                            st.success(f"Document successfully created! `_id`: `{doc_id}`")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Insert Error: {ex}")

        with crud_tab_r:
            st.markdown("##### 📖 Read: Query Documents by Farm & Date Range")
            st.code("""
# PyMongo Query with Filter:
query = {
    "farm_id": int(farm_id),
    "timestamp": {
        "$gte": "2026-10-01 00:00:00",
        "$lte": "2026-10-24 23:59:59"
    }
}
cursor = db.sensor_readings.find(query).sort("timestamp", -1).limit(50)
            """, language="python")

            r_f_opts = {"All Farms": None}
            for f in farms:
                r_f_opts[f"#{f['farm_id']} - {f['name']}"] = f["farm_id"]
            sel_r_farm = st.selectbox("Filter Plot:", options=list(r_f_opts.keys()), key="crud_r_farm")

            if st.button("▶️ Execute Read Query", key="btn_crud_read"):
                if mongo_connected:
                    docs = mongodb_manager.get_sensor_readings(farm_id=r_f_opts[sel_r_farm], limit=30)
                    if docs:
                        st.dataframe(pd.DataFrame(docs), use_container_width=True, hide_index=True)
                        st.caption(f"Retrieved {len(docs)} document(s) from MongoDB.")
                    else:
                        st.warning("No documents found in MongoDB for the selected farm.")
                else:
                    st.warning("MongoDB is offline. Please configure MONGODB_URI in .env.")

        with crud_tab_u:
            st.markdown("##### ✏️ Update: Modify Selected Telemetry Document")
            st.code("""
# PyMongo Update Operation:
filter_query = {"_id": ObjectId(reading_id)}
update_op = {"$set": {"soil_moisture_pct": new_moisture, "updated_at": datetime.utcnow()}}
result = db.sensor_readings.update_one(filter_query, update_op)
            """, language="python")

            m_docs = mongodb_manager.get_sensor_readings(limit=20) if mongo_connected else []
            if m_docs:
                u_opts = {f"{d['_id'][:8]}... | Farm #{d['farm_id']} | {d.get('timestamp','')} ({d['soil_moisture_pct']}%)": d["_id"] for d in m_docs}
                sel_u_label = st.selectbox("Select Target Document:", list(u_opts.keys()), key="crud_u_sel")
                sel_u_id = u_opts[sel_u_label]
                sel_u_doc = next(d for d in m_docs if d["_id"] == sel_u_id)

                with st.form("crud_update_form"):
                    nu_sm = st.number_input("New Moisture (%)", 0.0, 100.0, float(sel_u_doc["soil_moisture_pct"]), step=0.5)
                    nu_st = st.number_input("New Temperature (°C)", 0.0, 60.0, float(sel_u_doc["soil_temperature_c"]), step=0.5)

                    if st.form_submit_button("▶️ Execute Update Document", use_container_width=True):
                        try:
                            ok = mongodb_manager.update_sensor_reading(sel_u_id, {"soil_moisture_pct": nu_sm, "soil_temperature_c": nu_st})
                            if ok:
                                st.success(f"Document `{sel_u_id}` updated successfully!")
                                st.rerun()
                            else:
                                st.warning("Document was not modified.")
                        except Exception as e:
                            st.error(f"Update Error: {e}")
            else:
                st.info("No documents found to update. Connect MongoDB and insert readings first.")

        with crud_tab_d:
            st.markdown("##### 🗑️ Delete: Safely Remove Telemetry Document")
            st.code("""
# PyMongo Delete Operation:
filter_query = {"_id": ObjectId(reading_id)}
result = db.sensor_readings.delete_one(filter_query)
            """, language="python")

            if m_docs:
                d_opts = {f"{d['_id'][:8]}... | Farm #{d['farm_id']} | {d.get('timestamp','')}": d["_id"] for d in m_docs}
                sel_d_label = st.selectbox("Select Target Document to Delete:", list(d_opts.keys()), key="crud_d_sel")
                sel_d_id = d_opts[sel_d_label]

                if st.button("▶️ Execute Safe Delete", use_container_width=True):
                    try:
                        ok = mongodb_manager.delete_sensor_reading(sel_d_id)
                        if ok:
                            st.success(f"Document `{sel_d_id}` deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Delete operation failed.")
                    except Exception as e:
                        st.error(f"Delete Error: {e}")
            else:
                st.info("No documents available to delete.")

    # -------------------------------------------------------------
    # TAB 6: MONGODB AGGREGATION PIPELINES
    # -------------------------------------------------------------
    with lab_t6:
        st.markdown("#### ⚡ Real MongoDB Aggregation Pipelines")
        st.caption("Demonstrating multi-stage document processing pipelines built with Python dictionaries and executed against `sensor_readings`.")

        pipe_choice = st.selectbox(
            "Select Aggregation Pipeline:",
            [
                ("match_sort", "1. $MATCH & $SORT (Filter by Farm & Date Range)"),
                ("group_summary", "2. $GROUP (Fleet/Farm Moisture, Temp & Rain Statistics)"),
                ("sort_metric", "3. $SORT (Sort Telemetry by Moisture or Temperature Metric)"),
                ("project_calc", "4. $PROJECT (Compute Deficit & Categorical Status Field)"),
                ("daily_trend", "5. DAILY AGGREGATION (Group Readings by Calendar Day)"),
                ("categories", "6. MOISTURE CATEGORIES (Group into 5 Documented Soil Moisture Buckets)"),
                ("farm_comparison", "7. FARM COMPARISON (Cross-Farm Soil Moisture & Pings Benchmark)"),
                ("unwind_demo", "8. $UNWIND (Array Processing on Multi-Depth Probe Sensors)"),
            ],
            format_func=lambda x: x[1],
        )

        # Filters for pipelines
        pf1, pf2 = st.columns([1.5, 1.5])
        with pf1:
            p_farm_opts = {"All Farms": None}
            for f in farms:
                p_farm_opts[f"#{f['farm_id']} - {f['name']}"] = f["farm_id"]
            sel_p_farm = st.selectbox("Target Farm Filter:", list(p_farm_opts.keys()), key="pipe_farm_sel")
            target_pipe_fid = p_farm_opts[sel_p_farm]

        with pf2:
            if pipe_choice[0] == "sort_metric":
                p_sort_f = st.selectbox("Sort Field:", ["soil_moisture_pct", "soil_temperature_c", "rainfall_mm", "timestamp"])
                p_sort_asc = st.checkbox("Ascending Order", value=False)
            elif pipe_choice[0] == "project_calc":
                p_thresh = st.slider("Target Crop Moisture Threshold (%):", 20.0, 60.0, 35.0, 5.0)
            elif pipe_choice[0] == "daily_trend":
                p_days = st.slider("Limit Days:", 3, 30, 14)
            elif pipe_choice[0] == "unwind_demo":
                if st.button("🌱 Seed Sample Probe Array Telemetry", use_container_width=True):
                    ok = mongodb_manager.seed_sample_array_telemetry(farm_id=target_pipe_fid or 1)
                    if ok:
                        st.success("Sample telemetry with `probe_nodes` array seeded!")
                        st.rerun()

        # Build pipeline stages
        import json
        if pipe_choice[0] == "match_sort":
            pipeline_def = mongodb_manager.build_pipeline_match(farm_id=target_pipe_fid, limit=30)
            pipe_expl = "Filters documents matching `farm_id` and optional date bounds, sorting by `timestamp` descending."
        elif pipe_choice[0] == "group_summary":
            pipeline_def = mongodb_manager.build_pipeline_group(farm_id=target_pipe_fid)
            pipe_expl = "Executes `$group` accumulating average moisture, average temperature, max rainfall, and document counts."
        elif pipe_choice[0] == "sort_metric":
            pipeline_def = mongodb_manager.build_pipeline_sort(farm_id=target_pipe_fid, sort_field=p_sort_f, ascending=p_sort_asc, limit=30)
            pipe_expl = f"Applies `$sort` on `{p_sort_f}` in {'ascending' if p_sort_asc else 'descending'} order."
        elif pipe_choice[0] == "project_calc":
            pipeline_def = mongodb_manager.build_pipeline_project(farm_id=target_pipe_fid, target_threshold=p_thresh, limit=30)
            pipe_expl = f"Projects required fields and computes `moisture_deficit_pct` (relative to {p_thresh}%) and `status` (`ADEQUATE` vs `DEFICIT`)."
        elif pipe_choice[0] == "daily_trend":
            pipeline_def = mongodb_manager.build_pipeline_daily_aggregation(farm_id=target_pipe_fid, limit_days=p_days)
            pipe_expl = "Extracts `YYYY-MM-DD` substring from timestamp, groups readings by day, and calculates daily averages and rainfall totals."
        elif pipe_choice[0] == "categories":
            pipeline_def = mongodb_manager.build_pipeline_moisture_categories(farm_id=target_pipe_fid)
            pipe_expl = "Uses `$switch` conditional branching to classify readings into 5 documented categories: Drought (<20%), Needs Water (20-40%), Moderate (40-60%), Optimal (60-80%), and Saturated (>=80%). Note: Boundaries are academic demonstration thresholds."
        elif pipe_choice[0] == "farm_comparison":
            pipeline_def = mongodb_manager.build_pipeline_farm_comparison()
            pipe_expl = "Cross-farm benchmark grouping all sensor documents by `farm_id` and comparing average moisture, extremes, and reading volume."
        else:
            pipeline_def = mongodb_manager.build_pipeline_unwind(farm_id=target_pipe_fid)
            pipe_expl = "Deconstructs the nested `probe_nodes` array field using `$unwind` and calculates average moisture across each soil depth (15cm, 30cm, 60cm)."

        st.info(f"💡 **Pipeline Purpose:** {pipe_expl}")
        st.code(json.dumps(pipeline_def, indent=2), language="json")

        if st.button("▶️ Execute MongoDB Pipeline", key="btn_exec_pipe"):
            if not mongo_connected:
                st.warning("MongoDB is offline or MONGODB_URI is not set in `.env`. Connect MongoDB to execute this pipeline live.")
            else:
                try:
                    with st.spinner("Executing aggregation pipeline in MongoDB cluster..."):
                        res_pipe = mongodb_manager.execute_pipeline(pipeline_def)
                    if res_pipe:
                        st.dataframe(pd.DataFrame(res_pipe), use_container_width=True, hide_index=True)
                        st.caption(f"Pipeline executed successfully. Generated {len(res_pipe)} aggregated document(s).")
                    else:
                        st.warning("Pipeline returned 0 documents. Insert telemetry readings first.")
                except Exception as p_err:
                    st.error(f"MongoDB Pipeline Execution Error: {p_err}")

    # -------------------------------------------------------------
    # SECURE READ-ONLY SQL CONSOLE (READ-ONLY ENFORCED)
    # -------------------------------------------------------------
    st.markdown("---")
    with st.expander("🔍 Interactive SQL Console (Strictly Read-Only SELECT)", expanded=False):
        st.markdown("Execute custom analytical SELECT or WITH queries against `farms`, `sensor_readings`, and `irrigation_history`. Destructive keywords (`DROP`, `ALTER`, `DELETE`, `UPDATE`, `INSERT`) are prohibited by security policy.")
        custom_sql_query = st.text_area(
            "SQL Query:",
            value="SELECT f.name, f.crop_type, f.area_acres, COUNT(i.irrigation_id) AS events FROM farms f LEFT JOIN irrigation_history i ON f.farm_id = i.farm_id GROUP BY f.farm_id;",
            height=85,
            key="custom_sql_input",
        )
        if st.button("▶️ Run Read-Only Query", key="btn_run_custom_sql"):
            try:
                with st.spinner("Executing analytical query..."):
                    custom_df = db.execute_safe_readonly_sql(custom_sql_query)
                if not custom_df.empty:
                    st.dataframe(custom_df, use_container_width=True, hide_index=True)
                    st.caption(f"Query returned {len(custom_df)} row(s).")
                else:
                    st.warning("Query executed successfully but returned 0 rows.")
            except Exception as sec_ex:
                st.error(f"{sec_ex}")


# =====================================================================
# VIEW 7: TELEMETRY SIMULATOR & HYBRID NOSQL HUB
# =====================================================================
elif nav_item == "📡 Telemetry Simulator":
    st.markdown("### 📡 Telemetry Simulator & Hybrid NoSQL Hub")
    st.info("ℹ️ **Simulated Data Notice:** In accordance with academic guidelines for DCDSL, all telemetry values generated here are synthetic and stored with `is_simulated = 1`. No live IoT hardware or weather station APIs are claimed.")

    tab_sqlite, tab_mongo = st.tabs(["🗄️ Relational Test Bench (SQLite)", "🍃 MongoDB NoSQL Telemetry Hub"])

    with tab_sqlite:
        st.markdown("#### Scenario Presets")
        preset_cols = st.columns(4)
        with preset_cols[0]:
            if st.button("🏜️ Drought Deficit", use_container_width=True):
                st.session_state["sim_sm"] = 15.0
                st.session_state["sim_st"] = 35.0
                st.session_state["sim_sh"] = 38.0
                st.session_state["sim_rf"] = 0.0
                st.session_state["sim_rp"] = 0.0
        with preset_cols[1]:
            if st.button("🌧️ Heavy Rain Incoming", use_container_width=True):
                st.session_state["sim_sm"] = 28.0
                st.session_state["sim_st"] = 24.0
                st.session_state["sim_sh"] = 85.0
                st.session_state["sim_rf"] = 24.0
                st.session_state["sim_rp"] = 5.0
        with preset_cols[2]:
            if st.button("🌿 Optimal Level", use_container_width=True):
                st.session_state["sim_sm"] = 55.0
                st.session_state["sim_st"] = 27.0
                st.session_state["sim_sh"] = 65.0
                st.session_state["sim_rf"] = 0.0
                st.session_state["sim_rp"] = 0.0
        with preset_cols[3]:
            if st.button("🌊 Waterlog Risk", use_container_width=True):
                st.session_state["sim_sm"] = 84.0
                st.session_state["sim_st"] = 22.0
                st.session_state["sim_sh"] = 90.0
                st.session_state["sim_rf"] = 8.0
                st.session_state["sim_rp"] = 12.0

        with st.form("sim_bench_form"):
            sf_id = st.selectbox(
                "Target Farm Plot:",
                options=[f["farm_id"] for f in farms],
                format_func=lambda x: next(f"#{f['farm_id']} - {f['name']} ({f['crop_type']})" for f in farms if f["farm_id"] == x),
                index=[f["farm_id"] for f in farms].index(selected_farm["farm_id"]),
            )
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                sm_val = st.slider("Soil Moisture (%)", 0.0, 100.0, st.session_state.get("sim_sm", 25.0), 0.5)
                st_val = st.slider("Soil Temperature (°C)", 10.0, 50.0, st.session_state.get("sim_st", 28.5), 0.5)
                sh_val = st.slider("Humidity (%)", 0.0, 100.0, st.session_state.get("sim_sh", 65.0), 1.0)
            with c_s2:
                sr_val = st.slider("24h Rain Forecast (mm)", 0.0, 50.0, st.session_state.get("sim_rf", 2.0), 0.5)
                sp_val = st.slider("Past 24h Rain (mm)", 0.0, 50.0, st.session_state.get("sim_rp", 0.0), 0.5)

            if st.form_submit_button("🧪 Inject Simulated Telemetry Reading", use_container_width=True, type="primary"):
                try:
                    rid = db.add_sensor_reading(sf_id, sm_val, st_val, sh_val, sp_val, sr_val, 1)
                    mongo_doc_id = None
                    if mongo_connected:
                        try:
                            mongo_doc_id = mongodb_manager.insert_sensor_reading(
                                farm_id=sf_id,
                                soil_moisture_pct=sm_val,
                                soil_temperature_c=st_val,
                                humidity_pct=sh_val,
                                rainfall_mm=sp_val,
                                rainfall_forecast_24h_mm=sr_val,
                                is_simulated=1,
                            )
                        except Exception:
                            pass

                    st.cache_data.clear()
                    st.session_state["selected_farm_id"] = sf_id
                    if mongo_doc_id:
                        st.success(f"Simulated Reading #{rid} injected into SQLite AND synchronized to MongoDB (ID: `{mongo_doc_id}`)!")
                    else:
                        st.success(f"Simulated Reading #{rid} injected into SQLite! Switch to Dashboard to inspect the updated recommendation.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

        st.markdown("#### Recent Simulated Telemetry Log (SQLite)")
        st.dataframe(db.get_sensor_readings_history(limit=50), use_container_width=True, hide_index=True)

    with tab_mongo:
        st.markdown("#### 🍃 MongoDB NoSQL Telemetry Management")

        # Connection health banner
        if mongo_connected:
            st.success(f"✅ **MongoDB Connected:** {mongo_status_msg}")
            m_count = mongodb_manager.count_sensor_readings()
            st.caption(f"📁 Database: `{mongodb_manager.DEFAULT_DB_NAME}` | Collection: `{mongodb_manager.COLLECTION_SENSOR_READINGS}` | Total Documents: **{m_count}**")
        else:
            st.warning(f"⚠️ **MongoDB Offline / Not Connected:** {mongo_status_msg}")
            st.info("""
            **How to Connect MongoDB:**
            1. Copy `.env.example` to `.env`:
               ```bash
               cp .env.example .env
               ```
            2. Configure `MONGODB_URI` in `.env`:
               - **Local:** `MONGODB_URI=mongodb://localhost:27017/smart_irrigation_db`
               - **Atlas:** `MONGODB_URI=mongodb+srv://<user>:<password>@cluster0.abcde.mongodb.net/smart_irrigation_db?retryWrites=true&w=majority`
            3. Ensure `pymongo` is installed (`pip install pymongo python-dotenv`).
            4. The app will automatically connect and enable live NoSQL telemetry storage.
            """)

        st.markdown("---")

        # 4 CRUD Sections (Insert, Read, Update, Delete)
        crud_c1, crud_c2 = st.columns(2)

        with crud_c1:
            st.markdown("##### ➕ 1. Insert Sensor Reading (Create)")
            with st.form("mongo_insert_form"):
                m_farm_id = st.selectbox(
                    "Target Plot:",
                    options=[f["farm_id"] for f in farms],
                    format_func=lambda x: next(f"#{f['farm_id']} - {f['name']} ({f['crop_type']})" for f in farms if f["farm_id"] == x),
                    key="mongo_ins_farm",
                )
                m_sm = st.slider("Soil Moisture (%)", 0.0, 100.0, 42.0, 0.5, key="m_sm")
                m_st = st.slider("Soil Temperature (°C)", 10.0, 50.0, 27.5, 0.5, key="m_st")
                m_sh = st.slider("Humidity (%)", 0.0, 100.0, 68.0, 1.0, key="m_sh")
                m_rf = st.slider("Rainfall Last 24h (mm)", 0.0, 50.0, 0.0, 0.5, key="m_rf")
                m_fc = st.slider("Rainfall Forecast 24h (mm)", 0.0, 50.0, 5.0, 0.5, key="m_fc")
                m_sim = st.checkbox("Is Simulated Telemetry", value=True, key="m_sim")

                if st.form_submit_button("🍃 Insert Document to MongoDB", use_container_width=True, type="primary"):
                    if not mongo_connected:
                        st.error("Cannot insert document: MongoDB is not connected. Configure MONGODB_URI in .env.")
                    else:
                        try:
                            new_id = mongodb_manager.insert_sensor_reading(
                                farm_id=m_farm_id,
                                soil_moisture_pct=m_sm,
                                soil_temperature_c=m_st,
                                humidity_pct=m_sh,
                                rainfall_mm=m_rf,
                                rainfall_forecast_24h_mm=m_fc,
                                is_simulated=1 if m_sim else 0,
                            )
                            if new_id:
                                st.cache_data.clear()
                                st.success(f"Document successfully created in MongoDB! `_id`: `{new_id}`")
                                st.rerun()
                            else:
                                st.error("Failed to insert document into MongoDB.")
                        except Exception as e:
                            st.error(f"Validation/Insert Error: {e}")

        with crud_c2:
            st.markdown("##### ✏️ 2. Update Test Reading (Update)")
            m_recent = mongodb_manager.get_sensor_readings(limit=25) if mongo_connected else []
            if m_recent:
                m_id_options = {f"{r['_id'][:8]}... | Farm #{r['farm_id']} | {r.get('timestamp','')} ({r['soil_moisture_pct']}%)": r["_id"] for r in m_recent}
                selected_up_label = st.selectbox("Select Reading to Modify:", options=list(m_id_options.keys()))
                target_doc_id = m_id_options[selected_up_label]
                target_doc = next(r for r in m_recent if r["_id"] == target_doc_id)

                with st.form("mongo_update_form"):
                    u_sm = st.number_input("New Moisture (%)", min_value=0.0, max_value=100.0, value=float(target_doc["soil_moisture_pct"]), step=0.5)
                    u_st = st.number_input("New Temperature (°C)", min_value=0.0, max_value=60.0, value=float(target_doc["soil_temperature_c"]), step=0.5)
                    u_sh = st.number_input("New Humidity (%)", min_value=0.0, max_value=100.0, value=float(target_doc["humidity_pct"]), step=1.0)
                    u_rf = st.number_input("New Rainfall (mm)", min_value=0.0, max_value=100.0, value=float(target_doc["rainfall_mm"]), step=0.5)

                    if st.form_submit_button("💾 Save Changes to MongoDB", use_container_width=True):
                        try:
                            updated = mongodb_manager.update_sensor_reading(
                                target_doc_id,
                                {
                                    "soil_moisture_pct": u_sm,
                                    "soil_temperature_c": u_st,
                                    "humidity_pct": u_sh,
                                    "rainfall_mm": u_rf,
                                },
                            )
                            if updated:
                                st.cache_data.clear()
                                st.success(f"Document `{target_doc_id}` updated successfully!")
                                st.rerun()
                            else:
                                st.warning("Document not modified.")
                        except Exception as u_err:
                            st.error(f"Update Error: {u_err}")
            else:
                st.info("No MongoDB documents available to update. Connect MongoDB and insert readings first.")

            st.markdown("##### 🗑️ 3. Delete Test Reading Safely (Delete)")
            if m_recent:
                del_id_options = {f"{r['_id'][:8]}... | Farm #{r['farm_id']} | {r.get('timestamp','')}": r["_id"] for r in m_recent}
                selected_del_label = st.selectbox("Select Reading to Delete:", options=list(del_id_options.keys()), key="del_select")
                target_del_id = del_id_options[selected_del_label]

                if st.button("🗑️ Delete Selected Document", use_container_width=True):
                    try:
                        deleted = mongodb_manager.delete_sensor_reading(target_del_id)
                        if deleted:
                            st.cache_data.clear()
                            st.success(f"Document `{target_del_id}` permanently removed from MongoDB!")
                            st.rerun()
                        else:
                            st.error("Failed to delete document.")
                    except Exception as d_err:
                        st.error(f"Delete Error: {d_err}")
            else:
                st.info("No documents available to delete.")

        st.markdown("---")
        st.markdown("##### 📖 4. Read Readings by Farm & Date Range (Read)")
        rf_col1, rf_col2, rf_col3 = st.columns([1.5, 1.5, 1.0])
        with rf_col1:
            filter_farm_opts = {"All Farms": None}
            for f in farms:
                filter_farm_opts[f"#{f['farm_id']} - {f['name']} ({f['crop_type']})"] = f["farm_id"]
            selected_f_filter = st.selectbox("Filter by Farm:", options=list(filter_farm_opts.keys()))
            target_f_id = filter_farm_opts[selected_f_filter]
        with rf_col2:
            d_range = st.date_input("Date Range:", value=(datetime.date.today() - datetime.timedelta(days=30), datetime.date.today()))
            start_d = d_range[0] if isinstance(d_range, (list, tuple)) and len(d_range) > 0 else None
            end_d = d_range[1] if isinstance(d_range, (list, tuple)) and len(d_range) > 1 else start_d
        with rf_col3:
            limit_n = st.slider("Max Records:", 5, 100, 30)

        if mongo_connected:
            readings_data = mongodb_manager.get_sensor_readings(farm_id=target_f_id, start_date=start_d, end_date=end_d, limit=limit_n)
            if readings_data:
                df_mongo = pd.DataFrame(readings_data)
                display_cols = [c for c in ["_id", "farm_id", "timestamp", "soil_moisture_pct", "soil_temperature_c", "humidity_pct", "rainfall_mm", "rainfall_forecast_24h_mm", "is_simulated"] if c in df_mongo.columns]
                st.dataframe(df_mongo[display_cols], use_container_width=True, hide_index=True)
                st.caption(f"Retrieved {len(readings_data)} documents from MongoDB collection `sensor_readings`.")
            else:
                st.info("No sensor reading documents found matching the filter criteria in MongoDB.")
        else:
            st.warning("MongoDB is offline. Showing sample format expected in MongoDB `sensor_readings` collection:")
            sample_df = pd.DataFrame([
                {
                    "_id": "671a5c889312b9d038f12a01",
                    "farm_id": 1,
                    "timestamp": "2026-10-24 16:30:00",
                    "soil_moisture_pct": 28.5,
                    "soil_temperature_c": 29.0,
                    "humidity_pct": 65.0,
                    "rainfall_mm": 0.0,
                    "rainfall_forecast_24h_mm": 2.0,
                    "is_simulated": 1,
                }
            ])
            st.dataframe(sample_df, use_container_width=True, hide_index=True)
