import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO, StringIO
import json

st.set_page_config(page_title="Pile Soil Spring Calculator", layout="wide", page_icon="P")


# --- UI STYLE: stronger, larger navigation tabs (display only; no calculation impact) ---
st.markdown(
    """
    <style>
    /* Make top tab navigation larger and easier to read */
    div[data-testid="stTabs"] > div[role="tablist"] {
        gap: 8px;
        border-bottom: 2px solid #d6dde8;
        padding: 0.25rem 0 0.15rem 0;
        margin-bottom: 1.25rem;
        overflow-x: auto;
    }

    div[data-testid="stTabs"] button[role="tab"] {
        min-height: 48px;
        padding: 12px 18px;
        border-radius: 10px 10px 0 0;
        border: 1px solid #d6dde8;
        border-bottom: 0;
        background: #f3f6fb;
        color: #263445;
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.01em;
        box-shadow: 0 1px 2px rgba(20, 40, 70, 0.06);
        transition: all 0.12s ease-in-out;
    }

    div[data-testid="stTabs"] button[role="tab"]:hover {
        background: #e7eef9;
        color: #0f3f7a;
        border-color: #b9c9df;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: linear-gradient(180deg, #ff4b4b 0%, #d92f2f 100%);
        color: #ffffff;
        border-color: #c92a2a;
        box-shadow: 0 3px 8px rgba(217, 47, 47, 0.28);
        transform: translateY(1px);
    }

    div[data-testid="stTabs"] button[role="tab"] p {
        font-size: 17px;
        font-weight: 700;
        margin: 0;
        white-space: nowrap;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
        color: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

VERSION = 29  # D.1: add displacement diagrams along pile in Pile Design

#  CONSTANTS
WIDGET_KEYS = [
    "project_no", "project_title", "structure_name", "designer", "checker", "revision", "project_notes",
    "stage", "method", "pile_type",
    "D", "B", "H", "L", "fc", "dl", "nu",
    "wt", "scour", "use_group", "sD", "nx", "ny", "spring_output",
]

def _apply_pending_load():
    """Apply pending JSON project values before Streamlit widgets are created."""
    if "_pending_load" in st.session_state:
        pending = st.session_state.pop("_pending_load")
        for w in ("soil_editor", "_soil_edited", "_prev_type_cons", "_prev_N"):
            if w in st.session_state:
                del st.session_state[w]
        for k, v in pending.items():
            st.session_state[k] = v
        st.session_state["_just_loaded_msg"] = pending.get("__msg__", "")

def _apply_pending_profile():
    """Apply a predefined soil profile before Streamlit widgets are created."""
    if "_pending_profile" in st.session_state:
        name = st.session_state.pop("_pending_profile")
        if name in SOIL_PROFILES:
            st.session_state.soil_layers = SOIL_PROFILES[name].copy()
            for w in ("soil_editor", "_soil_edited", "_prev_type_cons", "_prev_N"):
                if w in st.session_state:
                    del st.session_state[w]
            st.session_state["_just_profile_msg"] = f"Loaded predefined profile: {name}"

#  SAVE / LOAD PROJECT FUNCTIONS
def save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, s_D, nx, ny, spring_output,
    soil_layers, app_version, project_meta=None
):
    """Create a dictionary with all project parameters for saving"""
    return {
        "app_version": app_version,
        "project_meta": project_meta or {},
        "design_stage": design_stage,
        "method": method,
        "pile_type": pile_type,
        "D": float(D),
        "B": float(B),
        "H": float(H),
        "L": float(L),
        "fc": float(fc),
        "node_spacing": float(node_spacing),
        "nu": float(nu),
        "water_table": float(water_table),
        "scour_depth": float(scour_depth),
        "use_group": bool(use_group),
        "s_D": float(s_D),
        "nx": int(nx),
        "ny": int(ny),
        "spring_output": spring_output,
        "soil_layers": soil_layers.to_dict(orient="records"),
        "saved_timestamp": pd.Timestamp.now().isoformat(),
    }

def load_project_from_dict(data):
    """Load project parameters from dictionary and return session_state updates"""
    updates = {}
    if isinstance(data.get("project_meta"), dict):
        for _k, _v in data["project_meta"].items():
            if _k in ("project_no", "project_title", "structure_name", "designer", "checker", "revision", "project_notes"):
                updates[_k] = str(_v)
    key_map = {
        "design_stage": "stage",
        "method": "method",
        "pile_type": "pile_type",
        "D": "D", "B": "B", "H": "H", "L": "L", "fc": "fc",
        "node_spacing": "dl",
        "nu": "nu",
        "water_table": "wt",
        "scour_depth": "scour",
        "use_group": "use_group",
        "s_D": "sD",
        "nx": "nx", "ny": "ny",
        "spring_output": "spring_output",
    }
    for json_key, st_key in key_map.items():
        if json_key in data:
            v = data[json_key]
            if st_key in ("nx", "ny"):
                v = int(v)
            elif st_key in ("D", "B", "H", "L", "fc", "dl", "nu", "wt", "scour", "sD"):
                v = float(v)
            elif st_key == "use_group":
                v = bool(v)
            updates[st_key] = v

    # Rebuild soil layers DataFrame
    if "soil_layers" in data and len(data["soil_layers"]) > 0:
        df = pd.DataFrame(data["soil_layers"])
        for col in ["Depth_From", "Depth_To", "SPT_N", "Es", "cu", "phi", "Gamma"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        updates["soil_layers"] = df

    return updates

#  REFERENCE DATABASE
SOIL_DB = {
    "Clay": {
        # N ranges & Suc per Table 6.3.2-1 (DRT/DOH standard)
        "Very Soft":       {"N": 1,  "cu":   7, "Es":  1500, "Gamma": 15, "alpha": 12,  "desc": "N<2,   Suc<15 kPa"},
        "Soft":            {"N": 3,  "cu":  20, "Es":  3000, "Gamma": 16, "alpha": 24,  "desc": "N=2-4, Suc=15-25 kPa"},
        "Medium Stiff":    {"N": 6,  "cu":  38, "Es":  8000, "Gamma": 17, "alpha": 48,  "desc": "N=4-8, Suc=25-50 kPa"},
        "Stiff":           {"N": 12, "cu":  75, "Es": 18000, "Gamma": 18, "alpha": 96,  "desc": "N=8-15, Suc=50-100 kPa"},
        "Very Stiff":      {"N": 22, "cu": 150, "Es": 40000, "Gamma": 19, "alpha": 150, "desc": "N=15-30, Suc=100-200 kPa"},
        "Hard":            {"N": 40, "cu": 250, "Es": 75000, "Gamma": 20, "alpha": 200, "desc": "N>30,  Suc>200 kPa"},
    },
    "Sand": {
        # phi ranges per Table 6.3.2-1 (DRT/DOH standard); phi = midpoint of range
        "Very Loose":   {"N": 2,  "phi": 26, "Es":  8000, "Gamma": 15, "nh_dry":  2200, "nh_wet":  1300, "desc": "N=0-4,   phi<28°"},
        "Loose":        {"N": 7,  "phi": 29, "Es": 20000, "Gamma": 17, "nh_dry":  6600, "nh_wet":  4000, "desc": "N=4-10,  phi=28-30°"},
        "Medium Dense": {"N": 20, "phi": 33, "Es": 45000, "Gamma": 18, "nh_dry": 17600, "nh_wet": 10500, "desc": "N=10-30, phi=30-36°"},
        "Dense":        {"N": 40, "phi": 39, "Es": 80000, "Gamma": 19, "nh_dry": 35000, "nh_wet": 21000, "desc": "N=30-50, phi=36-41°"},
        "Very Dense":   {"N": 55, "phi": 43, "Es":120000, "Gamma": 20, "nh_dry": 56000, "nh_wet": 34000, "desc": "N>50,    phi>41°"},
    }
}

SOIL_PROFILES = {
    "Bangkok - General Profile": pd.DataFrame([
        {"Depth_From": 0.0,  "Depth_To": 2.0,  "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N": 3,  "Es":  3000, "cu": 15,  "phi": 0, "Gamma": 16.0},
        {"Depth_From": 2.0,  "Depth_To": 8.0,  "Soil_Type": "Clay", "Consistency": "Very Soft",    "SPT_N": 2,  "Es":  1500, "cu": 10,  "phi": 0, "Gamma": 15.0},
        {"Depth_From": 8.0,  "Depth_To": 12.0, "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N": 5,  "Es":  6000, "cu": 30,  "phi": 0, "Gamma": 16.0},
        {"Depth_From": 12.0, "Depth_To": 16.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 9,  "Es": 12000, "cu": 55,  "phi": 0, "Gamma": 17.0},
        {"Depth_From": 16.0, "Depth_To": 20.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 15, "Es": 25000, "cu": 90,  "phi": 0, "Gamma": 18.0},
        {"Depth_From": 20.0, "Depth_To": 24.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 20, "Es": 45000, "cu": 0,   "phi": 32, "Gamma": 19.0},
        {"Depth_From": 24.0, "Depth_To": 28.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 80000, "cu": 0,   "phi": 35, "Gamma": 20.0},
        {"Depth_From": 28.0, "Depth_To": 32.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 18, "Es": 30000, "cu": 110, "phi": 0, "Gamma": 18.5},
        {"Depth_From": 32.0, "Depth_To": 40.0, "Soil_Type": "Sand", "Consistency": "Very Dense",   "SPT_N": 45, "Es":120000, "cu": 0,   "phi": 38, "Gamma": 20.5},
    ]),
    "Bangkok - Sukhumvit/Ratchada (Thick Soft Clay)": pd.DataFrame([
        {"Depth_From": 0.0,  "Depth_To": 3.0,  "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N": 2,  "Es":  2000, "cu": 12,  "phi": 0, "Gamma": 15.5},
        {"Depth_From": 3.0,  "Depth_To": 12.0, "Soil_Type": "Clay", "Consistency": "Very Soft",    "SPT_N": 1,  "Es":  1200, "cu": 8,   "phi": 0, "Gamma": 14.5},
        {"Depth_From": 12.0, "Depth_To": 18.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 8,  "Es": 10000, "cu": 45,  "phi": 0, "Gamma": 16.5},
        {"Depth_From": 18.0, "Depth_To": 24.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 25, "Es": 55000, "cu": 0,   "phi": 33, "Gamma": 19.0},
        {"Depth_From": 24.0, "Depth_To": 30.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 40, "Es": 90000, "cu": 0,   "phi": 36, "Gamma": 20.0},
    ]),
    "Bangkok - Thonburi/Pinklao (Shallow Stiff Clay)": pd.DataFrame([
        {"Depth_From": 0.0,  "Depth_To": 4.0,  "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 8,  "Es": 12000, "cu": 50,  "phi": 0, "Gamma": 17.5},
        {"Depth_From": 4.0,  "Depth_To": 10.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 14, "Es": 22000, "cu": 85,  "phi": 0, "Gamma": 18.5},
        {"Depth_From": 10.0, "Depth_To": 15.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 22, "Es": 35000, "cu": 130, "phi": 0, "Gamma": 19.0},
        {"Depth_From": 15.0, "Depth_To": 20.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 80000, "cu": 0,   "phi": 36, "Gamma": 20.0},
    ]),
    "Thailand Central Plain - Alluvial Clay/Sand (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  2.0, "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N":  4, "Es":  5000, "cu":  25, "phi": 0,  "Gamma": 17.0},
        {"Depth_From":  2.0, "Depth_To":  8.0, "Soil_Type": "Clay", "Consistency": "Very Soft",    "SPT_N":  2, "Es":  1500, "cu":  10, "phi": 0,  "Gamma": 15.5},
        {"Depth_From":  8.0, "Depth_To": 15.0, "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N":  5, "Es":  6000, "cu":  30, "phi": 0,  "Gamma": 16.5},
        {"Depth_From": 15.0, "Depth_To": 22.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 20, "Es": 45000, "cu":   0, "phi": 32, "Gamma": 18.5},
        {"Depth_From": 22.0, "Depth_To": 30.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 16, "Es": 26000, "cu":  96, "phi": 0,  "Gamma": 18.5},
    ]),
    "Thailand East - Residual/Lateritic Soil (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  2.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N":  8, "Es": 12000, "cu":  50, "phi": 0,  "Gamma": 18.0},
        {"Depth_From":  2.0, "Depth_To":  6.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 15, "Es": 25000, "cu":  90, "phi": 0,  "Gamma": 18.5},
        {"Depth_From":  6.0, "Depth_To": 12.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 25, "Es": 55000, "cu":   0, "phi": 33, "Gamma": 19.0},
        {"Depth_From": 12.0, "Depth_To": 20.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 25, "Es": 40000, "cu": 150, "phi": 0,  "Gamma": 19.0},
        {"Depth_From": 20.0, "Depth_To": 30.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 40, "Es": 80000, "cu":   0, "phi": 36, "Gamma": 20.0},
    ]),
    "Thailand Northeast - Lateritic/Residual Soil (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  2.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 12, "Es": 18000, "cu":  72, "phi": 0,  "Gamma": 18.5},
        {"Depth_From":  2.0, "Depth_To":  6.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 18, "Es": 40000, "cu":   0, "phi": 32, "Gamma": 18.5},
        {"Depth_From":  6.0, "Depth_To": 12.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 25, "Es": 40000, "cu": 150, "phi": 0,  "Gamma": 19.0},
        {"Depth_From": 12.0, "Depth_To": 20.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 75000, "cu":   0, "phi": 35, "Gamma": 19.5},
        {"Depth_From": 20.0, "Depth_To": 30.0, "Soil_Type": "Clay", "Consistency": "Hard",         "SPT_N": 40, "Es": 75000, "cu": 250, "phi": 0,  "Gamma": 20.0},
    ]),
    "Thailand North - Residual/Colluvial Soil (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  2.0, "Soil_Type": "Sand", "Consistency": "Loose",        "SPT_N":  8, "Es": 20000, "cu":   0, "phi": 30, "Gamma": 17.5},
        {"Depth_From":  2.0, "Depth_To":  6.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 10, "Es": 15000, "cu":  60, "phi": 0,  "Gamma": 18.0},
        {"Depth_From":  6.0, "Depth_To": 12.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 25, "Es": 55000, "cu":   0, "phi": 34, "Gamma": 19.0},
        {"Depth_From": 12.0, "Depth_To": 20.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 40, "Es": 80000, "cu":   0, "phi": 37, "Gamma": 20.0},
        {"Depth_From": 20.0, "Depth_To": 30.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 30, "Es": 50000, "cu": 180, "phi": 0,  "Gamma": 19.5},
    ]),
    "Thailand South Gulf - Marine Clay/Sand (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  2.0, "Soil_Type": "Sand", "Consistency": "Loose",        "SPT_N":  6, "Es": 18000, "cu":   0, "phi": 29, "Gamma": 17.0},
        {"Depth_From":  2.0, "Depth_To":  8.0, "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N":  3, "Es":  3000, "cu":  18, "phi": 0,  "Gamma": 16.0},
        {"Depth_From":  8.0, "Depth_To": 15.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N":  8, "Es": 10000, "cu":  45, "phi": 0,  "Gamma": 17.0},
        {"Depth_From": 15.0, "Depth_To": 22.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 22, "Es": 45000, "cu":   0, "phi": 32, "Gamma": 19.0},
        {"Depth_From": 22.0, "Depth_To": 30.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 80000, "cu":   0, "phi": 35, "Gamma": 20.0},
    ]),
    "Thailand South Andaman - Sand/Residual Soil (Preliminary Only)": pd.DataFrame([
        {"Depth_From":  0.0, "Depth_To":  3.0, "Soil_Type": "Sand", "Consistency": "Loose",        "SPT_N":  8, "Es": 20000, "cu":   0, "phi": 30, "Gamma": 17.5},
        {"Depth_From":  3.0, "Depth_To":  8.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 18, "Es": 40000, "cu":   0, "phi": 32, "Gamma": 18.5},
        {"Depth_From":  8.0, "Depth_To": 14.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 15, "Es": 25000, "cu":  90, "phi": 0,  "Gamma": 18.5},
        {"Depth_From": 14.0, "Depth_To": 22.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 80000, "cu":   0, "phi": 36, "Gamma": 20.0},
        {"Depth_From": 22.0, "Depth_To": 30.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 28, "Es": 45000, "cu": 170, "phi": 0,  "Gamma": 19.5},
    ])
}

PMULT_TABLE = {
    "Lead Row": {3.0: 0.80, 4.0: 0.90, 5.0: 1.00, 6.0: 1.00},
    "2nd Row":  {3.0: 0.40, 4.0: 0.625, 5.0: 0.85, 6.0: 1.00},
    "3rd Row+": {3.0: 0.30, 4.0: 0.50,  5.0: 0.70, 6.0: 1.00},
}

REBAR_DB = {
    "DB12": {"dia_mm": 12, "fy_mpa": 390},
    "DB16": {"dia_mm": 16, "fy_mpa": 390},
    "DB20": {"dia_mm": 20, "fy_mpa": 390},
    "DB25": {"dia_mm": 25, "fy_mpa": 390},
    "DB28": {"dia_mm": 28, "fy_mpa": 390},
    "DB32": {"dia_mm": 32, "fy_mpa": 490},
}

ACI_MIN_LONG_RATIO = 0.01
ACI_MAX_LONG_RATIO = 0.08

#  SESSION STATE INIT  (must run BEFORE handlers below)
if 'version' not in st.session_state or st.session_state.version < VERSION:
    st.session_state.clear()
    st.session_state.version = VERSION

_apply_pending_load()
_apply_pending_profile()

if 'soil_layers' not in st.session_state:
    st.session_state.soil_layers = SOIL_PROFILES["Bangkok - General Profile"].copy()

if "_prev_type_cons" not in st.session_state:
    _init = st.session_state.soil_layers
    st.session_state["_prev_type_cons"] = {
        i: (str(r.get("Soil_Type", "")), str(r.get("Consistency", "")))
        for i, r in _init.iterrows()
    }
if "_prev_N" not in st.session_state:
    _init = st.session_state.soil_layers
    st.session_state["_prev_N"] = {
        i: (float(r.get("SPT_N", 0)) if (r.get("SPT_N") is not None
             and str(r.get("SPT_N", "")) not in ("nan", "None", "")) else 0.0)
        for i, r in _init.iterrows()
    }

#  ENGINEERING FUNCTIONS
def get_alpha_clay(N):
    """Bowles 1997 alpha factor for clay based on N-SPT"""
    if N <= 1:    return 12
    elif N <= 4:  return 24
    elif N <= 8:  return 48
    elif N <= 15: return 96
    elif N <= 30: return 150
    else:         return 200

# ── Interpolation: N-SPT → phi (Sand) and cu (Clay) ─────────────────
# Breakpoints from Table 6.3.2-1 (DRT/DOH standard)
_SAND_N_NODES   = [  0,   4,  10,  30,  50,  60,  100]
_SAND_PHI_NODES = [ 24,  28,  30,  36,  41,  43,   45]   # °, linear interp; >50 extrapolated

_CLAY_N_NODES   = [  0,   2,   4,   8,  15,  30,   60]
_CLAY_CU_NODES  = [  0,  15,  25,  50, 100, 200,  400]  # kPa, linear interp

def interp_phi_from_N(N):
    """Linear interpolation of phi [deg] from SPT-N for Sand.
    Based on Table 6.3.2-1 breakpoints. Capped at 45° for N>100.
    """
    N = max(0.0, float(N))
    if N >= _SAND_N_NODES[-1]:
        return float(_SAND_PHI_NODES[-1])
    for i in range(len(_SAND_N_NODES) - 1):
        n0, n1 = _SAND_N_NODES[i], _SAND_N_NODES[i + 1]
        if n0 <= N <= n1:
            t = (N - n0) / (n1 - n0)
            return round(_SAND_PHI_NODES[i] + t * (_SAND_PHI_NODES[i + 1] - _SAND_PHI_NODES[i]), 1)
    return float(_SAND_PHI_NODES[-1])

def interp_cu_from_N(N):
    """Linear interpolation of cu [kPa] from SPT-N for Clay.
    Based on Table 6.3.2-1 breakpoints (Suc = cu). Extrapolates beyond N=60.
    """
    N = max(0.0, float(N))
    if N >= _CLAY_N_NODES[-1]:
        return round(_CLAY_CU_NODES[-1] + (N - _CLAY_N_NODES[-1]) * (_CLAY_CU_NODES[-1] - _CLAY_CU_NODES[-2]) / (_CLAY_N_NODES[-1] - _CLAY_N_NODES[-2]), 1)
    for i in range(len(_CLAY_N_NODES) - 1):
        n0, n1 = _CLAY_N_NODES[i], _CLAY_N_NODES[i + 1]
        if n0 <= N <= n1:
            t = (N - n0) / (n1 - n0)
            return round(_CLAY_CU_NODES[i] + t * (_CLAY_CU_NODES[i + 1] - _CLAY_CU_NODES[i]), 1)
    return float(_CLAY_CU_NODES[-1])

def consistency_from_N(soil_type, N):
    """Return Consistency label matching the N-SPT range per Table 6.3.2-1."""
    N = float(N)
    if soil_type == "Sand":
        if N < 4:   return "Very Loose"
        if N < 10:  return "Loose"
        if N < 30:  return "Medium Dense"
        if N <= 50: return "Dense"
        return "Very Dense"
    else:  # Clay
        if N < 2:   return "Very Soft"
        if N < 4:   return "Soft"
        if N < 8:   return "Medium Stiff"
        if N < 15:  return "Stiff"
        if N <= 30: return "Very Stiff"
        return "Hard"

def calc_kh_jra(N, D, design_stage, soil_type, below_water):
    """JRA lateral subgrade modulus; sand below water table uses E0 x 0.6."""
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N
    if soil_type == "Sand" and below_water:
        E0 *= 0.6
    kh = (E0 / B0) * (D / B0) ** (-0.75)
    return kh, E0

def get_nh_terzaghi(N, below_water):
    """Rounded Bowles/Terzaghi sand nh design values in kN/m3/m."""
    if N <= 10:   return 4000  if below_water else 7000
    elif N <= 30: return 12000 if below_water else 21000
    elif N <= 50: return 21000 if below_water else 35000
    else:         return 34000 if below_water else 56000

def calc_kh_terzaghi(N, soil_type, D, z_mid, below_water, cu=None):
    """Terzaghi/Bowles lateral subgrade modulus for sand and clay."""
    if soil_type == "Sand":
        nh = get_nh_terzaghi(N, below_water)
        z_use = max(z_mid, 0.1)
        kh = nh * z_use / D
    else:
        if cu is None or pd.isna(cu) or float(cu) <= 0:
            cu = 6.25 * N
        else:
            cu = float(cu)
        alpha = get_alpha_clay(N)
        kh = alpha * cu / D
    return kh

def calc_kh_vesic(Es_kPa, D, Ep, Ip, nu=0.35):
    """Vesic (1961) Beam on Elastic Foundation"""
    Es = float(Es_kPa)
    if Ep * Ip <= 0 or Es <= 0 or D <= 0:
        return 0.0
    return 0.65 * (Es * D**4 / (Ep * Ip))**(1/12) * Es / (D * (1 - nu**2))

def calc_kh_broms(soil_type, N, z, D, gamma_eff=8, phi=None, cu=None):
    """Broms (1964) ultimate lateral resistance -> secant kh at y=0.01D"""
    y_ref = 0.01 * D
    z_use = max(z, 0.1)
    if soil_type == "Sand":
        if phi is None: phi = 28 + 0.3 * N
        phi_r = np.radians(phi)
        Kp = (1 + np.sin(phi_r)) / (1 - np.sin(phi_r))
        pu = 3 * Kp * gamma_eff * z_use * D
    else:
        if cu is None: cu = 6.25 * N
        pu = 9 * cu * D
    kh = pu / (y_ref * D)
    return kh, pu

def calc_pmultiplier(s_D_ratio, row_pos):
    """AASHTO LRFD Table 10.7.2.4-1 p-multiplier (linear interpolation)"""
    t = PMULT_TABLE[row_pos]
    keys = sorted(t.keys())
    if s_D_ratio <= keys[0]:  return t[keys[0]]
    if s_D_ratio >= keys[-1]: return t[keys[-1]]
    return float(np.interp(s_D_ratio, keys, [t[k] for k in keys]))

def group_row_position(row_index):
    """Row label used for p-multiplier lookup."""
    return "Lead Row" if row_index == 0 else ("2nd Row" if row_index == 1 else "3rd Row+")

def get_rebar_area_mm2(bar_name):
    dia_mm = float(REBAR_DB[bar_name]["dia_mm"])
    return np.pi * dia_mm**2 / 4.0

def get_rebar_fy_mpa(bar_name):
    return float(REBAR_DB[bar_name]["fy_mpa"])

def calc_pile_props(pile_type, D, B, H, fc):
    """Concrete pile properties. Ep = 4700sqrtfc (MPa) -> kN/m2"""
    Ep = 4700 * np.sqrt(fc) * 1000
    if pile_type == "Round":
        Ap = np.pi * D**2 / 4
        Ipx = np.pi * D**4 / 64
        Ipy = Ipx
        Deq_x = D
        Deq_y = D
    else:
        Ap = B * H
        Ipx = B * H**3 / 12   # Bending about X-axis (Y-loading)
        Ipy = H * B**3 / 12   # Bending about Y-axis (X-loading)
        Deq_x = B
        Deq_y = H
    return Ap, Ipx, Ipy, Ep, Deq_x, Deq_y

def solve_pile_lateral_response(
    depths, spring_k, EI, head_shear=0.0, head_moment=0.0,
    head_condition="Free Head", rotational_stiffness=0.0
):
    """Solve a Winkler beam with selectable pile-head rotational restraint.

    Parameters
    ----------
    head_condition : str
        - "Free Head / Shear Only": pile-head rotation is free; applied head_moment is used directly.
        - "Fixed Head (theta = 0)": pile-head rotation is restrained; the head moment is solved as a reaction.
        - "Rotational Spring": a rotational spring Ktheta [kN-m/rad] is added at the pile head.

    Returns
    -------
    y, theta, reactions, shear, moment, head_restraint_moment
        head_restraint_moment is the moment generated by the head restraint/spring.
        For a free head it is 0.0; for a fixed head it is the solved reaction moment.
    """
    depths = np.asarray(depths, dtype=float)
    spring_k = np.asarray(spring_k, dtype=float)
    n = len(depths)
    if n == 0:
        empty = np.array([])
        return empty, empty, empty, empty, empty, 0.0
    if n == 1 or (abs(head_shear) < 1e-12 and abs(head_moment) < 1e-12):
        zeros = np.zeros(n, dtype=float)
        return zeros, zeros, zeros, zeros, zeros, 0.0
    if EI <= 0 or np.all(np.abs(spring_k) < 1e-12):
        raise ValueError("Pile lateral response cannot be solved because EI or spring stiffness is zero.")

    ndof = 2 * n
    K = np.zeros((ndof, ndof), dtype=float)
    F = np.zeros(ndof, dtype=float)
    F[0] = float(head_shear)
    F[1] = float(head_moment)

    for i in range(n - 1):
        le = float(depths[i + 1] - depths[i])
        if le <= 0:
            raise ValueError("Depth nodes must be strictly increasing for pile response analysis.")
        ke = EI / le**3 * np.array([
            [12.0, 6.0 * le, -12.0, 6.0 * le],
            [6.0 * le, 4.0 * le**2, -6.0 * le, 2.0 * le**2],
            [-12.0, -6.0 * le, 12.0, -6.0 * le],
            [6.0 * le, 2.0 * le**2, -6.0 * le, 4.0 * le**2],
        ], dtype=float)
        idx = [2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3]
        K[np.ix_(idx, idx)] += ke

    for i, k_val in enumerate(spring_k):
        K[2 * i, 2 * i] += max(float(k_val), 0.0)

    head_condition_text = str(head_condition or "Free Head")
    ktheta = max(float(rotational_stiffness or 0.0), 0.0)
    use_rot_spring = head_condition_text.startswith("Rotational") and ktheta > 0.0
    if use_rot_spring:
        K[1, 1] += ktheta

    constrained_dofs = []
    if head_condition_text.startswith("Fixed"):
        constrained_dofs = [1]  # theta at pile head = 0

    if constrained_dofs:
        all_dofs = np.arange(ndof)
        free_dofs = np.setdiff1d(all_dofs, np.asarray(constrained_dofs, dtype=int))
        u = np.zeros(ndof, dtype=float)
        Kff = K[np.ix_(free_dofs, free_dofs)]
        Ff = F[free_dofs]
        u[free_dofs] = np.linalg.solve(Kff, Ff)
        residual = K @ u - F
        head_restraint_moment = float(residual[1])
    else:
        u = np.linalg.solve(K, F)
        if use_rot_spring:
            # Moment applied by the rotational spring to the pile head.
            head_restraint_moment = -ktheta * float(u[1])
        else:
            head_restraint_moment = 0.0

    y = u[0::2]
    theta = u[1::2]
    reactions = spring_k * y

    shear = np.zeros(n, dtype=float)
    moment = np.zeros(n, dtype=float)
    effective_head_moment = float(head_moment) + float(head_restraint_moment)
    for i, z in enumerate(depths):
        shear[i] = head_shear - reactions[:i + 1].sum()
        arm = z - depths[:i + 1]
        moment[i] = effective_head_moment + head_shear * z - np.sum(reactions[:i + 1] * arm)

    return y, theta, reactions, shear, moment, head_restraint_moment

def calc_kv_tip(N_tip, D, Ap, design_stage):
    """Vertical tip spring (JRA) Kv_tip = (E0/B0)(D/B0)^(-3/4)/3 x Ap"""
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N_tip
    kv = (E0 / B0) * (D / B0)**(-0.75) / 3.0
    Kv_tip = kv * Ap
    return Kv_tip, kv

def equivalent_circular_diameter_from_area(Ap):
    """Equivalent circular diameter for non-round pile area used in JRA-style size effects."""
    if Ap <= 0:
        return 0.0
    return float(np.sqrt(4.0 * Ap / np.pi))

def calc_tributary_lengths(depths, L):
    """Tributary pile length represented by each lateral spring node."""
    depths = np.asarray(depths, dtype=float)
    if len(depths) == 0:
        return np.array([], dtype=float)
    if len(depths) == 1:
        return np.array([float(L)], dtype=float)

    tribs = []
    for i, z in enumerate(depths):
        left = 0.0 if i == 0 else (depths[i - 1] + z) / 2.0
        right = float(L) if i == len(depths) - 1 else (z + depths[i + 1]) / 2.0
        tribs.append(max(right - left, 0.0))
    return np.asarray(tribs, dtype=float)

def draw_spring(x0, x1, y, n_coils=7):
    """Zigzag spring symbol between x0 and x1 at depth y.

    The x-coordinate progression follows the sign of (x1 - x0), so the
    spring is drawn correctly for both left-to-right and right-to-left calls.
    """
    length = abs(x1 - x0)
    if length <= 0 or n_coils <= 0:
        return [x0, x1], [y, y]
    direction = 1 if x1 >= x0 else -1
    dx = length / (n_coils * 4)
    xs = [x0]
    ys = [y]
    for i in range(n_coils):
        xs += [
            x0 + direction * dx * (4*i + 1),
            x0 + direction * dx * (4*i + 2),
            x0 + direction * dx * (4*i + 3),
            x0 + direction * dx * (4*i + 4),
        ]
        ys += [y + dx, y - dx, y + dx, y]
    return xs, ys


def _parse_load_case_bool(value):
    """Parse checkbox-like values pasted from Excel."""
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    if txt in ("", "nan", "none", "<na>"):
        return True
    if txt in ("true", "t", "yes", "y", "1", "use", "ใช่"):
        return True
    if txt in ("false", "f", "no", "n", "0", "ไม่", "ไม่ใช้"):
        return False
    return True


def _clean_load_case_number(value):
    """Convert pasted load values to float while tolerating commas and unit text."""
    txt = str(value).strip()
    if txt.lower() in ("", "nan", "none", "<na>"):
        return np.nan
    txt = (
        txt.replace(",", "")
           .replace("kN", "")
           .replace("KN", "")
           .replace("kn", "")
           .strip()
    )
    return pd.to_numeric(txt, errors="coerce")


def clean_pile_load_cases(load_case_input, drop_blank=True):
    """Return a calculation-ready load case table with stable column names and types."""
    if load_case_input is None or len(load_case_input) == 0:
        return pd.DataFrame(columns=["Use", "Load Case", "Pu [kN]", "Hx [kN]", "Hy [kN]"])

    load_cases = load_case_input.copy()
    required_cols = ["Use", "Load Case", "Pu [kN]", "Hx [kN]", "Hy [kN]"]
    for col in required_cols:
        if col not in load_cases.columns:
            load_cases[col] = True if col == "Use" else ("" if col == "Load Case" else np.nan)

    load_cases = load_cases[required_cols].copy()
    load_cases["Load Case"] = (
        load_cases["Load Case"]
        .fillna("")
        .astype(str)
        .replace({"nan": "", "None": "", "<NA>": ""})
        .str.strip()
    )
    load_cases["Use"] = load_cases["Use"].apply(_parse_load_case_bool).astype(bool)

    for col in ["Pu [kN]", "Hx [kN]", "Hy [kN]"]:
        load_cases[col] = load_cases[col].apply(_clean_load_case_number)

    numeric_blank = load_cases[["Pu [kN]", "Hx [kN]", "Hy [kN]"]].isna().all(axis=1)
    name_blank = load_cases["Load Case"].eq("")
    if drop_blank:
        load_cases = load_cases.loc[~(name_blank & numeric_blank)].copy()

    for col in ["Pu [kN]", "Hx [kN]", "Hy [kN]"]:
        load_cases[col] = load_cases[col].fillna(0.0).astype(float)

    for i, idx in enumerate(load_cases.index, start=1):
        if load_cases.at[idx, "Load Case"] == "":
            load_cases.at[idx, "Load Case"] = f"LC{i}"

    return load_cases.reset_index(drop=True)


def parse_pasted_load_cases(paste_text):
    """Parse a formatted Excel copy/paste table into the app load-case schema.

    Accepted formats:
    1) Use | Load Case | Pu [kN] | Hx [kN] | Hy [kN]
    2) Load Case | Pu [kN] | Hx [kN] | Hy [kN]
    3) Pu [kN] | Hx [kN] | Hy [kN]
    Header row is recommended but not mandatory.
    """
    text = str(paste_text or "").strip()
    if not text:
        raise ValueError("No pasted load-case data found.")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("No pasted load-case data found.")

    delimiter = "\t" if any("\t" in ln for ln in lines) else ","
    rows = [[cell.strip() for cell in ln.split(delimiter)] for ln in lines]
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]

    def norm_header(h):
        h = str(h).strip().lower()
        h = h.replace(" ", "").replace("_", "").replace("-", "")
        h = h.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
        return h

    header_norm = [norm_header(c) for c in rows[0]]
    header_alias = {
        "use": "Use",
        "loadcase": "Load Case",
        "case": "Load Case",
        "lc": "Load Case",
        "pukn": "Pu [kN]",
        "pu": "Pu [kN]",
        "axial": "Pu [kN]",
        "axialload": "Pu [kN]",
        "hxkn": "Hx [kN]",
        "hx": "Hx [kN]",
        "hykn": "Hy [kN]",
        "hy": "Hy [kN]",
    }
    mapped = [header_alias.get(h, "") for h in header_norm]
    has_header = any(mapped)

    records = []
    if has_header:
        body = rows[1:]
        col_map = {canonical: i for i, canonical in enumerate(mapped) if canonical}
        missing = [c for c in ["Pu [kN]", "Hx [kN]", "Hy [kN]"] if c not in col_map]
        if missing:
            raise ValueError("Header was detected, but these columns are missing: " + ", ".join(missing))
        for r in body:
            records.append({
                "Use": r[col_map["Use"]] if "Use" in col_map else True,
                "Load Case": r[col_map["Load Case"]] if "Load Case" in col_map else "",
                "Pu [kN]": r[col_map["Pu [kN]"]],
                "Hx [kN]": r[col_map["Hx [kN]"]],
                "Hy [kN]": r[col_map["Hy [kN]"]],
            })
    else:
        body = rows
        ncols = max_cols
        if ncols >= 5:
            for r in body:
                records.append({"Use": r[0], "Load Case": r[1], "Pu [kN]": r[2], "Hx [kN]": r[3], "Hy [kN]": r[4]})
        elif ncols == 4:
            for r in body:
                records.append({"Use": True, "Load Case": r[0], "Pu [kN]": r[1], "Hx [kN]": r[2], "Hy [kN]": r[3]})
        elif ncols == 3:
            for r in body:
                records.append({"Use": True, "Load Case": "", "Pu [kN]": r[0], "Hx [kN]": r[1], "Hy [kN]": r[2]})
        else:
            raise ValueError("Paste at least Pu [kN], Hx [kN], and Hy [kN] columns.")

    parsed = clean_pile_load_cases(pd.DataFrame(records), drop_blank=True)
    if parsed.empty:
        raise ValueError("The pasted table did not contain any usable load cases.")
    return parsed


def parse_uploaded_load_case_file(uploaded_file):
    """Parse .tsv/.csv/.xlsx load cases exported from Pile Cap STM or Excel.

    Expected engineering transfer schema is:
        Use | Load Case | Pu [kN] | Hx [kN] | Hy [kN]

    The parser also accepts the shorter formats supported by
    parse_pasted_load_cases(). Returned data are calculation-ready and use the
    Soil Spring app's stable load-case column names.
    """
    if uploaded_file is None:
        raise ValueError("No file was uploaded.")

    name = str(getattr(uploaded_file, "name", "") or "").lower()
    raw = uploaded_file.getvalue()

    if name.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(BytesIO(raw))
        except Exception as exc:
            raise ValueError(f"Cannot read Excel workbook: {exc}")
        if df.empty:
            raise ValueError("The uploaded workbook is empty.")
        return clean_pile_load_cases(df, drop_blank=True)

    # Text-based transfer files: TSV, CSV, TXT. Use UTF-8 first, then a common
    # Windows fallback so files opened/saved through Excel remain usable.
    for enc in ("utf-8-sig", "utf-8", "cp874", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        raise ValueError("Cannot decode uploaded text file. Please save as UTF-8 TSV/CSV.")

    return parse_pasted_load_cases(text)


def validate_soil_profile(df):
    """Validate gaps, overlaps, and depth order in the soil profile."""
    msgs = []
    if df is None or len(df) == 0:
        return ["No soil layer data found."]
    df_valid = df.dropna(subset=["Depth_From", "Depth_To"]).copy()
    if len(df_valid) == 0:
        return []
    df_sorted = df_valid.sort_values("Depth_From").reset_index(drop=True)
    for i in range(len(df_sorted)):
        if df_sorted.loc[i, "Depth_To"] <= df_sorted.loc[i, "Depth_From"]:
            msgs.append(
                f"Row {i+1}: Depth_To ({df_sorted.loc[i,'Depth_To']:.1f}) must be greater than Depth_From ({df_sorted.loc[i,'Depth_From']:.1f})."
            )
        if i > 0:
            prev_to = df_sorted.loc[i-1, "Depth_To"]
            curr_from = df_sorted.loc[i, "Depth_From"]
            if abs(prev_to - curr_from) > 1e-6:
                if curr_from > prev_to:
                    msgs.append(f"Gap between rows {i} and {i+1}: {prev_to:.1f} to {curr_from:.1f} m.")
                else:
                    msgs.append(f"Overlap between rows {i} and {i+1}: {curr_from:.1f} < {prev_to:.1f} m.")

    # Validate Soil_Type and Consistency pairing. This prevents using a Clay row
    # with a Sand consistency, or vice versa, which can leave stale cu/phi/Es
    # values in the calculation table.
    for enum_i, (_, row) in enumerate(df_valid.iterrows(), start=1):
        stype = str(row.get("Soil_Type", "") or "").strip()
        cons = str(row.get("Consistency", "") or "").strip()
        if stype and cons:
            valid_cons = SOIL_DB.get(stype, {})
            if stype not in SOIL_DB:
                msgs.append(f"Row {enum_i}: Soil_Type '{stype}' is not supported. Use Clay or Sand.")
            elif cons not in valid_cons:
                opts = ", ".join(valid_cons.keys())
                msgs.append(
                    f"Row {enum_i}: Consistency '{cons}' is not valid for {stype}. "
                    f"Valid options: {opts}."
                )
    return msgs


def autofill_soil_row(row_dict):
    """Fill a soil row from SOIL_DB when Soil_Type and Consistency change.
    Sets N-SPT = representative value from SOIL_DB, then derives phi/cu
    via interpolation (Table 6.3.2-1) for consistency with N-edit workflow.
    """
    stype = str(row_dict.get("Soil_Type", "") or "")
    cons  = str(row_dict.get("Consistency", "") or "")
    if stype in SOIL_DB and cons in SOIL_DB[stype]:
        db    = SOIL_DB[stype][cons]
        filled = dict(row_dict)
        N_rep  = float(db["N"])
        filled["SPT_N"] = N_rep
        filled["Es"]    = float(db["Es"])
        filled["Gamma"] = float(db["Gamma"])
        if stype == "Clay":
            filled["cu"]  = interp_cu_from_N(N_rep)
            filled["phi"] = 0.0
        else:
            filled["cu"]  = 0.0
            filled["phi"] = interp_phi_from_N(N_rep)
        return filled, True
    return row_dict, False

def autofill_from_N_change(row_dict):
    """Re-derive phi/cu from updated N-SPT without touching other fields.
    Also updates Consistency label to match the new N-SPT range.
    Called when user manually edits N-SPT.
    """
    stype = str(row_dict.get("Soil_Type", "") or "")
    N     = float(row_dict.get("SPT_N", 0) or 0)
    if not stype or N <= 0:
        return row_dict, False
    filled = dict(row_dict)
    filled["Consistency"] = consistency_from_N(stype, N)
    if stype == "Clay":
        filled["cu"]  = interp_cu_from_N(N)
        filled["phi"] = 0.0
    else:
        filled["cu"]  = 0.0
        filled["phi"] = interp_phi_from_N(N)
    return filled, True


def pile_section_figure(pile_type, D, B, H, Ap, Ipx, Ipy, Ep, compact=False):
    """Pile cross-section figure with dimension annotations and axis labels"""
    fig = go.Figure()
    pad = max(D, B, H) * 0.7
    dim_offset = max(D, B, H) * 0.35
    axis_len = max(D, B, H) * 0.55

    if pile_type == "Round":
        theta = np.linspace(0, 2*np.pi, 200)
        r = D / 2
        cx = np.cos(theta) * r
        cy = np.sin(theta) * r
        fig.add_trace(go.Scatter(x=cx, y=cy, fill='toself', fillcolor='rgba(100,160,220,0.35)',
                                 line=dict(color='#1a4f8a', width=2.5), showlegend=False, hoverinfo='skip'))
        ay = -r - dim_offset
        fig.add_annotation(ax=-r, ay=ay, x=r,  y=ay, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(ax=r,  ay=ay, x=-r, y=ay, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(x=0, y=ay, text=f"<b>D = {D:.2f} m</b>", showarrow=False, yshift=-16,
                           font=dict(size=13, color='#1a4f8a'))
        lim = r + pad
        title_text = f"Round Pile  D = {D:.2f} m"
    else:
        x0, x1 = -B/2, B/2
        y0, y1 = -H/2, H/2
        fig.add_trace(go.Scatter(x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0],
                                 fill='toself', fillcolor='rgba(100,160,220,0.35)',
                                 line=dict(color='#1a4f8a', width=2.5), showlegend=False, hoverinfo='skip'))
        ay_b = y0 - dim_offset
        fig.add_annotation(ax=x0, ay=ay_b, x=x1, y=ay_b, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(ax=x1, ay=ay_b, x=x0, y=ay_b, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(x=0, y=ay_b, text=f"<b>B = {B:.2f} m</b>", showarrow=False, yshift=-16,
                           font=dict(size=13, color='#1a4f8a'))
        ax_h = x1 + dim_offset
        fig.add_annotation(ax=ax_h, ay=y0, x=ax_h, y=y1, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#c0392b')
        fig.add_annotation(ax=ax_h, ay=y1, x=ax_h, y=y0, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=3, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#c0392b')
        fig.add_annotation(x=ax_h, y=0, text=f"<b>H = {H:.2f} m</b>", showarrow=False, xshift=22,
                           font=dict(size=13, color='#c0392b'))
        lim = max(B, H) / 2 + pad
        title_text = f"Square/Rect Pile BxH = {B:.2f}x{H:.2f} m"

    fig.add_annotation(ax=0, ay=0, x=axis_len, y=0, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    fig.add_annotation(x=axis_len * 1.06, y=0, text="<b>X</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')
    fig.add_annotation(ax=0, ay=0, x=0, y=axis_len, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    fig.add_annotation(x=0, y=axis_len * 1.08, text="<b>Y</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')

    fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers',
                             marker=dict(color='red', size=12, symbol='x'),
                             showlegend=False, name='CG', hoverinfo='skip'))
    fig.add_annotation(x=axis_len * 0.18, y=-axis_len * 0.18, text="<b>CG</b>", showarrow=False,
                       font=dict(size=11, color='red'), xref='x', yref='y')

    props_text = (f"Ap = {Ap:.4f} m2<br>Ix = {Ipx:.5f} m4<br>Iy = {Ipy:.5f} m4<br>Ep = {Ep/1000:.0f} MPa")
    fig.add_annotation(x=lim * 0.98, y=lim * 0.78, xref='x', yref='y', text=props_text, showarrow=False,
                       align='left', bgcolor='rgba(255,255,255,0.85)', bordercolor='#aaa',
                       borderwidth=1, borderpad=6, font=dict(size=11, family='monospace'))
    h = 380 if compact else 460
    fig.update_layout(title=dict(text=title_text, font=dict(size=14, color='#1a4f8a')),
                      xaxis=dict(scaleanchor='y', scaleratio=1, range=[-lim, lim],
                                 zeroline=False, showgrid=True, gridcolor='rgba(180,180,180,0.3)'),
                      yaxis=dict(range=[-lim, lim], zeroline=False, showgrid=True,
                                 gridcolor='rgba(180,180,180,0.3)'),
                      height=h, margin=dict(l=10, r=10, t=40, b=10),
                      plot_bgcolor='rgba(245,248,255,0.8)')
    return fig

def pile_group_plan_figure(pile_type, D, B, H, s_D, nx, ny, use_group):
    """Plan view of pile group layout with global X/Y axes."""
    fig = go.Figure()
    nx_plot = int(nx) if use_group else 1
    ny_plot = int(ny) if use_group else 1
    nx_plot = max(nx_plot, 1)
    ny_plot = max(ny_plot, 1)

    spacing = max(float(s_D), 1.0) * float(D)
    xs = (np.arange(nx_plot) - (nx_plot - 1) / 2.0) * spacing
    ys = (np.arange(ny_plot) - (ny_plot - 1) / 2.0) * spacing

    pile_w = float(D) if pile_type == "Round" else float(B)
    pile_h = float(D) if pile_type == "Round" else float(H)
    pile_radius = max(pile_w, pile_h) / 2.0

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            label = f"P{iy + 1}-{ix + 1}"
            if pile_type == "Round":
                fig.add_shape(
                    type="circle",
                    x0=x - pile_w / 2, x1=x + pile_w / 2,
                    y0=y - pile_h / 2, y1=y + pile_h / 2,
                    line=dict(color="#1a4f8a", width=2),
                    fillcolor="rgba(100,160,220,0.38)",
                    layer="above",
                )
            else:
                fig.add_shape(
                    type="rect",
                    x0=x - pile_w / 2, x1=x + pile_w / 2,
                    y0=y - pile_h / 2, y1=y + pile_h / 2,
                    line=dict(color="#1a4f8a", width=2),
                    fillcolor="rgba(100,160,220,0.38)",
                    layer="above",
                )
            fig.add_annotation(
                x=x, y=y, text=f"<b>{label}</b>", showarrow=False,
                font=dict(size=10, color="#1a4f8a"),
            )

    x_extent = (xs[-1] - xs[0]) / 2.0 + pile_radius
    y_extent = (ys[-1] - ys[0]) / 2.0 + pile_radius
    lim = max(x_extent, y_extent, spacing, D) * 1.45
    axis_len = lim * 0.72

    fig.add_annotation(
        ax=0, ay=0, x=axis_len, y=0,
        xref="x", yref="y", axref="x", ayref="y",
        arrowhead=3, arrowsize=1.2, arrowwidth=2.5,
        arrowcolor="#222222", showarrow=True,
    )
    fig.add_annotation(
        x=axis_len * 1.06, y=0, text="<b>X</b>", showarrow=False,
        font=dict(size=15, color="#222222", family="Arial Black"),
    )
    fig.add_annotation(
        ax=0, ay=0, x=0, y=axis_len,
        xref="x", yref="y", axref="x", ayref="y",
        arrowhead=3, arrowsize=1.2, arrowwidth=2.5,
        arrowcolor="#222222", showarrow=True,
    )
    fig.add_annotation(
        x=0, y=axis_len * 1.08, text="<b>Y</b>", showarrow=False,
        font=dict(size=15, color="#222222", family="Arial Black"),
    )
    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers",
        marker=dict(color="red", size=10, symbol="x"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        x=lim * 0.95, y=lim * 0.90,
        text=(
            f"<b>{nx_plot} x {ny_plot} piles</b><br>"
            f"s/D = {float(s_D):.2f}<br>"
            f"spacing = {spacing:.2f} m"
        ),
        showarrow=False, align="left",
        bgcolor="rgba(255,255,255,0.88)",
        bordercolor="#aaa", borderwidth=1, borderpad=6,
        font=dict(size=11),
    )

    if nx_plot > 1:
        y_dim = ys[0] - pile_h / 2 - 0.22 * lim
        fig.add_annotation(
            ax=xs[0], ay=y_dim, x=xs[1], y=y_dim,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowsize=1.0, arrowwidth=1.4,
            arrowcolor="#1a4f8a", showarrow=True,
        )
        fig.add_annotation(
            ax=xs[1], ay=y_dim, x=xs[0], y=y_dim,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowsize=1.0, arrowwidth=1.4,
            arrowcolor="#1a4f8a", showarrow=True,
        )
        fig.add_annotation(
            x=(xs[0] + xs[1]) / 2, y=y_dim,
            text=f"<b>{spacing:.2f} m</b>", showarrow=False,
            yshift=-14, font=dict(size=10, color="#1a4f8a"),
        )

    if ny_plot > 1:
        x_dim = xs[-1] + pile_w / 2 + 0.22 * lim
        fig.add_annotation(
            ax=x_dim, ay=ys[0], x=x_dim, y=ys[1],
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowsize=1.0, arrowwidth=1.4,
            arrowcolor="#c0392b", showarrow=True,
        )
        fig.add_annotation(
            ax=x_dim, ay=ys[1], x=x_dim, y=ys[0],
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowsize=1.0, arrowwidth=1.4,
            arrowcolor="#c0392b", showarrow=True,
        )
        fig.add_annotation(
            x=x_dim, y=(ys[0] + ys[1]) / 2,
            text=f"<b>{spacing:.2f} m</b>", showarrow=False,
            xshift=28, font=dict(size=10, color="#c0392b"),
        )

    fig.update_layout(
        title=dict(text="Pile Group Plan View", font=dict(size=14, color="#1a4f8a")),
        xaxis=dict(
            title="X [m]", scaleanchor="y", scaleratio=1, range=[-lim, lim],
            zeroline=True, zerolinecolor="rgba(80,80,80,0.45)",
            showgrid=True, gridcolor="rgba(180,180,180,0.28)",
        ),
        yaxis=dict(
            title="Y [m]", range=[-lim, lim],
            zeroline=True, zerolinecolor="rgba(80,80,80,0.45)",
            showgrid=True, gridcolor="rgba(180,180,180,0.28)",
        ),
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="rgba(245,248,255,0.8)",
    )
    return fig

def pile_rebar_section_figure(
    pile_type, D, B, H, clear_cover_mm, tie_bar, main_bar,
    n_round_bars=None, n_b_face=None, n_h_face=None
):
    """Section figure with perimeter reinforcement arrangement."""
    fig = go.Figure()
    main_dia_mm = float(REBAR_DB[main_bar]["dia_mm"])
    tie_dia_mm = float(REBAR_DB[tie_bar]["dia_mm"])
    cover_m = clear_cover_mm / 1000.0
    tie_dia_m = tie_dia_mm / 1000.0
    main_dia_m = main_dia_mm / 1000.0
    bar_coords = []

    if pile_type == "Round":
        radius = D / 2.0
        r_bar = max(radius - cover_m - tie_dia_m - main_dia_m / 2.0, main_dia_m)
        theta = np.linspace(0, 2 * np.pi, 200)
        fig.add_trace(go.Scatter(
            x=np.cos(theta) * radius,
            y=np.sin(theta) * radius,
            fill="toself",
            fillcolor="rgba(100,160,220,0.20)",
            line=dict(color="#1a4f8a", width=2.5),
            showlegend=False,
            hoverinfo="skip"
        ))
        fig.add_trace(go.Scatter(
            x=np.cos(theta) * (radius - cover_m - tie_dia_m / 2),
            y=np.sin(theta) * (radius - cover_m - tie_dia_m / 2),
            mode="lines",
            line=dict(color="#555", width=1.6, dash="dash"),
            showlegend=False,
            hoverinfo="skip"
        ))
        n_bars = max(int(n_round_bars or 6), 4)
        for ang in np.linspace(0, 2 * np.pi, n_bars, endpoint=False):
            bar_coords.append((r_bar * np.cos(ang), r_bar * np.sin(ang)))
        title = f"Pile Design Section - Round ({n_bars} {main_bar})"
        lim = radius * 1.55
    else:
        x0, x1 = -B / 2.0, B / 2.0
        y0, y1 = -H / 2.0, H / 2.0
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0],
            y=[y0, y0, y1, y1, y0],
            fill="toself",
            fillcolor="rgba(100,160,220,0.20)",
            line=dict(color="#1a4f8a", width=2.5),
            showlegend=False,
            hoverinfo="skip"
        ))
        x_t0 = x0 + cover_m + tie_dia_m / 2
        x_t1 = x1 - cover_m - tie_dia_m / 2
        y_t0 = y0 + cover_m + tie_dia_m / 2
        y_t1 = y1 - cover_m - tie_dia_m / 2
        fig.add_trace(go.Scatter(
            x=[x_t0, x_t1, x_t1, x_t0, x_t0],
            y=[y_t0, y_t0, y_t1, y_t1, y_t0],
            mode="lines",
            line=dict(color="#555", width=1.6, dash="dash"),
            showlegend=False,
            hoverinfo="skip"
        ))

        nb = max(int(n_b_face or 3), 2)
        nh = max(int(n_h_face or 3), 2)
        x_bar = np.linspace(
            x0 + cover_m + tie_dia_m + main_dia_m / 2,
            x1 - cover_m - tie_dia_m - main_dia_m / 2,
            nb
        )
        y_bar = np.linspace(
            y0 + cover_m + tie_dia_m + main_dia_m / 2,
            y1 - cover_m - tie_dia_m - main_dia_m / 2,
            nh
        )
        for x in x_bar:
            bar_coords.append((x, y_bar[0]))
            bar_coords.append((x, y_bar[-1]))
        for y in y_bar[1:-1]:
            bar_coords.append((x_bar[0], y))
            bar_coords.append((x_bar[-1], y))
        title = f"Pile Design Section - Rectangular ({2 * (nb + nh) - 4} {main_bar})"
        lim = max(B, H) * 0.95

    # Draw reinforcing bars using actual engineering size in plot coordinates.
    # Previous versions used Plotly marker.size (pixels), which made DB bars look
    # visually oversized when the section was zoomed.  Shapes below are defined
    # in metres, so DB28 is plotted as a 0.028 m diameter circle, independent of
    # screen resolution.  This is a display-only change; structural calculations
    # still use get_rebar_layout() and REBAR_DB areas.
    if bar_coords:
        bar_radius_m = main_dia_m / 2.0
        for bx, by in bar_coords:
            fig.add_shape(
                type="circle",
                x0=bx - bar_radius_m,
                x1=bx + bar_radius_m,
                y0=by - bar_radius_m,
                y1=by + bar_radius_m,
                line=dict(color="#8f2f1f", width=1.2),
                fillcolor="#c0392b",
                layer="above",
            )
        # Tiny centre points keep hover/cursor behaviour stable without
        # controlling the displayed bar diameter.
        bx_vals, by_vals = zip(*bar_coords)
        fig.add_trace(go.Scatter(
            x=bx_vals,
            y=by_vals,
            mode="markers",
            marker=dict(size=2, color="#c0392b", opacity=0.0),
            showlegend=False,
            hoverinfo="skip"
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#1a4f8a")),
        xaxis=dict(
            scaleanchor="y",
            scaleratio=1,
            range=[-lim, lim],
            showgrid=True,
            gridcolor="rgba(180,180,180,0.25)"
        ),
        yaxis=dict(
            range=[-lim, lim],
            showgrid=True,
            gridcolor="rgba(180,180,180,0.25)"
        ),
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="rgba(245,248,255,0.85)"
    )
    return fig

def get_rebar_layout(
    pile_type, D, B, H, clear_cover_mm, tie_bar, main_bar,
    n_round_bars=None, n_b_face=None, n_h_face=None
):
    """Return perimeter reinforcement coordinates in mm about the section centroid."""
    main_dia_mm = float(REBAR_DB[main_bar]["dia_mm"])
    tie_dia_mm = float(REBAR_DB[tie_bar]["dia_mm"])
    cover_mm = float(clear_cover_mm)
    as_bar_mm2 = get_rebar_area_mm2(main_bar)
    fy_mpa = get_rebar_fy_mpa(main_bar)
    coords = []

    if pile_type == "Round":
        radius_mm = D * 1000.0 / 2.0
        r_bar = max(radius_mm - cover_mm - tie_dia_mm - main_dia_mm / 2.0, main_dia_mm)
        n_bars = max(int(n_round_bars or 6), 4)
        for ang in np.linspace(0, 2 * np.pi, n_bars, endpoint=False):
            coords.append((r_bar * np.cos(ang), r_bar * np.sin(ang)))
    else:
        x0, x1 = -B * 1000.0 / 2.0, B * 1000.0 / 2.0
        y0, y1 = -H * 1000.0 / 2.0, H * 1000.0 / 2.0
        nb = max(int(n_b_face or 3), 2)
        nh = max(int(n_h_face or 3), 2)
        x_bar = np.linspace(
            x0 + cover_mm + tie_dia_mm + main_dia_mm / 2.0,
            x1 - cover_mm - tie_dia_mm - main_dia_mm / 2.0,
            nb
        )
        y_bar = np.linspace(
            y0 + cover_mm + tie_dia_mm + main_dia_mm / 2.0,
            y1 - cover_mm - tie_dia_mm - main_dia_mm / 2.0,
            nh
        )
        for x in x_bar:
            coords.append((x, y_bar[0]))
            coords.append((x, y_bar[-1]))
        for y in y_bar[1:-1]:
            coords.append((x_bar[0], y))
            coords.append((x_bar[-1], y))

    return pd.DataFrame({
        "x_mm": [pt[0] for pt in coords],
        "y_mm": [pt[1] for pt in coords],
        "As_mm2": as_bar_mm2,
        "fy_mpa": fy_mpa,
    })

def make_concrete_fibers(pile_type, D, B, H, grid_n=44):
    """Create a concrete fiber mesh scaled to the exact section area."""
    if pile_type == "Round":
        radius_mm = D * 1000.0 / 2.0
        cell = 2.0 * radius_mm / grid_n
        coords = np.linspace(-radius_mm + cell / 2.0, radius_mm - cell / 2.0, grid_n)
        xs, ys = np.meshgrid(coords, coords)
        mask = xs**2 + ys**2 <= radius_mm**2
        x = xs[mask].ravel()
        y = ys[mask].ravel()
        area = np.full_like(x, cell * cell, dtype=float)
        exact_area = np.pi * radius_mm**2
    else:
        b_mm = B * 1000.0
        h_mm = H * 1000.0
        nx = grid_n
        ny = max(12, int(round(grid_n * h_mm / max(b_mm, 1e-6))))
        x_coords = np.linspace(-b_mm / 2.0 + b_mm / (2 * nx), b_mm / 2.0 - b_mm / (2 * nx), nx)
        y_coords = np.linspace(-h_mm / 2.0 + h_mm / (2 * ny), h_mm / 2.0 - h_mm / (2 * ny), ny)
        xs, ys = np.meshgrid(x_coords, y_coords)
        x = xs.ravel()
        y = ys.ravel()
        area = np.full_like(x, b_mm * h_mm / (nx * ny), dtype=float)
        exact_area = b_mm * h_mm

    if area.sum() > 0:
        area *= exact_area / area.sum()
    return x, y, area, exact_area

def aci_beta1(fc_mpa):
    """ACI equivalent stress block beta1 for normal-strength concrete in MPa units."""
    return max(0.85 - max(float(fc_mpa) - 28.0, 0.0) * 0.05 / 7.0, 0.65)

def aci_phi_from_tension_strain(eps_t, fy_mpa, transverse_system="Tied"):
    """ACI-style phi factor from extreme tensile steel strain."""
    eps_y = float(fy_mpa) / 200000.0
    phi_min = 0.75 if transverse_system == "Spiral" else 0.65
    if eps_t <= eps_y:
        return phi_min
    if eps_t >= 0.005:
        return 0.90
    return phi_min + (0.90 - phi_min) * (eps_t - eps_y) / max(0.005 - eps_y, 1e-9)

def aci_section_strength_at_angle(
    fiber_x, fiber_y, fiber_area, bar_df, fc_mpa, theta_rad, c_mm,
    exact_area_mm2, transverse_system="Tied"
):
    """Nominal and factored section strength for one neutral-axis angle and depth."""
    beta1 = aci_beta1(fc_mpa)
    normal_x = np.cos(theta_rad)
    normal_y = np.sin(theta_rad)
    fiber_t = fiber_x * normal_x + fiber_y * normal_y
    bar_t = bar_df["x_mm"].to_numpy(dtype=float) * normal_x + bar_df["y_mm"].to_numpy(dtype=float) * normal_y
    t_max = float(np.max(fiber_t))
    t_na = t_max - float(c_mm)
    t_block_min = t_max - beta1 * float(c_mm)

    concrete_mask = fiber_t >= t_block_min
    concrete_force = 0.85 * fc_mpa * fiber_area[concrete_mask]
    concrete_x = fiber_x[concrete_mask]
    concrete_y = fiber_y[concrete_mask]

    eps_s = 0.003 * (bar_t - t_na) / max(float(c_mm), 1e-9)
    as_bars = bar_df["As_mm2"].to_numpy(dtype=float)
    fy_bars = bar_df["fy_mpa"].to_numpy(dtype=float)
    fs = np.minimum(np.maximum(200000.0 * eps_s, -fy_bars), fy_bars)
    steel_force = fs * as_bars
    steel_force = steel_force - np.where(bar_t >= t_block_min, 0.85 * fc_mpa * as_bars, 0.0)

    forces = np.concatenate([concrete_force, steel_force])
    xs = np.concatenate([concrete_x, bar_df["x_mm"].to_numpy(dtype=float)])
    ys = np.concatenate([concrete_y, bar_df["y_mm"].to_numpy(dtype=float)])

    pn_n = float(np.sum(forces))
    mx_nmm = float(np.sum(forces * ys))
    my_nmm = float(np.sum(forces * xs))

    eps_t = max(0.0, -float(np.min(eps_s))) if len(eps_s) else 0.0
    fy_ref = float(np.max(fy_bars)) if len(fy_bars) else 390.0
    phi = aci_phi_from_tension_strain(eps_t, fy_ref, transverse_system)

    ast = float(np.sum(as_bars))
    po_n = 0.85 * fc_mpa * max(exact_area_mm2 - ast, 0.0) + fy_ref * ast
    axial_cap_factor = 0.85 if transverse_system == "Spiral" else 0.80
    phi_pn_max_kN = axial_cap_factor * (0.75 if transverse_system == "Spiral" else 0.65) * po_n / 1000.0

    phi_pn_kN = phi * pn_n / 1000.0
    if phi_pn_kN > phi_pn_max_kN:
        phi_pn_kN = phi_pn_max_kN

    return {
        "Pn [kN]": pn_n / 1000.0,
        "Mx [kN-m]": mx_nmm / 1e6,
        "My [kN-m]": my_nmm / 1e6,
        "phi": phi,
        "phiPn [kN]": phi_pn_kN,
        "phiMnx [kN-m]": phi * mx_nmm / 1e6,
        "phiMny [kN-m]": phi * my_nmm / 1e6,
        "eps_t": eps_t,
        "phiPnMax [kN]": phi_pn_max_kN,
    }

@st.cache_data(show_spinner=False)
def build_aci_pmm_interaction(
    pile_type, D, B, H, fc_mpa, cover_mm, tie_bar, main_bar,
    n_main_bars=None, n_b_face=None, n_h_face=None, transverse_system="Tied",
    grid_n=28
):
    """Build a preliminary ACI 318-style PMM interaction point cloud."""
    bars = get_rebar_layout(
        pile_type, D, B, H, cover_mm, tie_bar, main_bar,
        n_round_bars=n_main_bars, n_b_face=n_b_face, n_h_face=n_h_face
    )
    fiber_x, fiber_y, fiber_area, exact_area = make_concrete_fibers(pile_type, D, B, H, grid_n=grid_n)
    max_dim_mm = max(D, B, H) * 1000.0
    c_values = np.unique(np.concatenate([
        np.linspace(0.05 * max_dim_mm, 1.50 * max_dim_mm, 26),
        np.linspace(1.75 * max_dim_mm, 7.00 * max_dim_mm, 14),
    ]))
    angles = np.unique(np.concatenate([
        np.linspace(0.0, 360.0, 17, endpoint=False),
        np.array([0.0, 90.0, 180.0, 270.0]),
    ]))

    rows = []
    for angle_deg in angles:
        theta = np.radians(angle_deg)
        for c_mm in c_values:
            strength = aci_section_strength_at_angle(
                fiber_x, fiber_y, fiber_area, bars, fc_mpa, theta, c_mm,
                exact_area, transverse_system
            )
            rows.append({
                "Angle [deg]": angle_deg,
                "c [mm]": c_mm,
                **strength,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        ast = float(bars["As_mm2"].sum())
        fy_ref = float(bars["fy_mpa"].max())
        phi_tension = 0.90
        phi_compression = 0.75 if transverse_system == "Spiral" else 0.65
        axial_cap_factor = 0.85 if transverse_system == "Spiral" else 0.80
        po_n = 0.85 * fc_mpa * max(exact_area - ast, 0.0) + fy_ref * ast
        phi_pn_max_kN = axial_cap_factor * phi_compression * po_n / 1000.0
        df = pd.concat([
            df,
            pd.DataFrame([{
                "Angle [deg]": np.nan,
                "c [mm]": np.inf,
                "Pn [kN]": po_n / 1000.0,
                "Mx [kN-m]": 0.0,
                "My [kN-m]": 0.0,
                "phi": phi_compression,
                "phiPn [kN]": phi_pn_max_kN,
                "phiMnx [kN-m]": 0.0,
                "phiMny [kN-m]": 0.0,
                "eps_t": 0.0,
                "phiPnMax [kN]": phi_pn_max_kN,
            }, {
                "Angle [deg]": np.nan,
                "c [mm]": 0.0,
                "Pn [kN]": -fy_ref * ast / 1000.0,
                "Mx [kN-m]": 0.0,
                "My [kN-m]": 0.0,
                "phi": phi_tension,
                "phiPn [kN]": -phi_tension * fy_ref * ast / 1000.0,
                "phiMnx [kN-m]": 0.0,
                "phiMny [kN-m]": 0.0,
                "eps_t": 0.005,
                "phiPnMax [kN]": phi_pn_max_kN,
            }])
        ], ignore_index=True)
    return df, bars

def uniaxial_interaction_curve(pmm_df, axis):
    """Extract an approximate uniaxial P-M envelope from the PMM point cloud."""
    if pmm_df.empty:
        return pd.DataFrame(columns=["phiPn [kN]", "phiM [kN-m]"])
    available_angles = pmm_df["Angle [deg]"].dropna().to_numpy(dtype=float)
    if len(available_angles) == 0:
        selected = pmm_df.copy()
    else:
        def _nearest_angle(target):
            diff = np.abs(((available_angles - target + 180.0) % 360.0) - 180.0)
            return float(available_angles[int(np.argmin(diff))])

        targets = [90.0, 270.0] if axis == "Mx" else [0.0, 180.0]
        selected_angles = {_nearest_angle(t) for t in targets}
        selected = pmm_df[pmm_df["Angle [deg]"].isin(selected_angles)].copy()
    if axis == "Mx":
        m_col = "phiMnx [kN-m]"
    else:
        m_col = "phiMny [kN-m]"
    if selected.empty:
        selected = pmm_df.copy()
        m_col = "phiMnx [kN-m]" if axis == "Mx" else "phiMny [kN-m]"

    axial_anchor = pmm_df[
        pmm_df["Angle [deg]"].isna()
        & np.isclose(pmm_df["phiMnx [kN-m]"], 0.0)
        & np.isclose(pmm_df["phiMny [kN-m]"], 0.0)
    ].copy()
    if not axial_anchor.empty:
        selected = pd.concat([selected, axial_anchor], ignore_index=True)

    return pd.DataFrame({
        "phiPn [kN]": selected["phiPn [kN]"],
        "phiM [kN-m]": selected[m_col].abs(),
    }).dropna()

def moment_capacity_at_p(curve_df, pu_kN, clamp_tol_ratio=0.002):
    """Interpolate factored uniaxial moment capacity at a factored axial demand.

    Small round-off excursions are clamped to the curve limits. A demand that
    is materially outside the P range returns zero capacity so the design is
    flagged as not adequate instead of being silently extrapolated.
    """
    if curve_df.empty:
        return 0.0
    curve = curve_df.copy()
    curve = curve[np.isfinite(curve["phiPn [kN]"]) & np.isfinite(curve["phiM [kN-m]"])]
    if curve.empty:
        return 0.0
    grouped = curve.groupby(curve["phiPn [kN]"].round(1))["phiM [kN-m]"].max().reset_index()
    grouped = grouped.sort_values("phiPn [kN]")
    p_vals = grouped["phiPn [kN]"].to_numpy(dtype=float)
    m_vals = grouped["phiM [kN-m]"].to_numpy(dtype=float)
    p_min = float(p_vals.min())
    p_max = float(p_vals.max())
    tol = max((p_max - p_min) * float(clamp_tol_ratio), 1e-6)
    if pu_kN < p_min:
        if pu_kN >= p_min - tol:
            pu_kN = p_min
        else:
            return 0.0
    elif pu_kN > p_max:
        if pu_kN <= p_max + tol:
            pu_kN = p_max
        else:
            return 0.0
    if pu_kN < p_min or pu_kN > p_max:
        return 0.0
    return float(np.interp(pu_kN, p_vals, m_vals))

def interaction_curve_envelope(curve_df):
    """Prepare a clean P-M envelope line from uniaxial interaction points."""
    if curve_df.empty:
        return pd.DataFrame(columns=["phiPn [kN]", "phiM [kN-m]"])
    curve = curve_df.copy()
    curve = curve[np.isfinite(curve["phiPn [kN]"]) & np.isfinite(curve["phiM [kN-m]"])]
    if curve.empty:
        return pd.DataFrame(columns=["phiPn [kN]", "phiM [kN-m]"])

    body = curve.groupby(curve["phiPn [kN]"].round(1), as_index=False)["phiM [kN-m]"].max()
    body = body.rename(columns={"index": "phiPn [kN]"}) if "index" in body.columns else body

    axial_points = curve[np.isclose(curve["phiM [kN-m]"], 0.0)].copy()
    if not axial_points.empty:
        axial_points = pd.DataFrame([
            axial_points.loc[axial_points["phiPn [kN]"].idxmin()],
            axial_points.loc[axial_points["phiPn [kN]"].idxmax()],
        ])
        axial_points["phiPn [kN]"] = axial_points["phiPn [kN]"].round(1)
        curve = pd.concat([body, axial_points[["phiPn [kN]", "phiM [kN-m]"]]], ignore_index=True)
    else:
        curve = body

    p_min = float(curve["phiPn [kN]"].min())
    p_max = float(curve["phiPn [kN]"].max())
    curve["p_key"] = curve["phiPn [kN]"].round(1)
    curve["m_sort"] = curve["phiM [kN-m]"]
    curve.loc[np.isclose(curve["phiPn [kN]"], p_max), "m_sort"] = -curve["phiM [kN-m]"]
    curve.loc[np.isclose(curve["phiPn [kN]"], p_min), "m_sort"] = curve["phiM [kN-m]"]

    return (
        curve.sort_values(["phiPn [kN]", "m_sort"])
        .drop(columns=["p_key", "m_sort"])
        .reset_index(drop=True)
    )


def expand_pmm_axial_anchors_for_slices(pmm_df):
    """Duplicate pure axial PMM anchor points to every finite angle.

    The PMM generator stores pure compression and pure tension anchor points
    with Angle = NaN. Those anchors are essential for a closed 3D surface,
    especially on the uplift/tension side. This helper makes the anchors
    available to each angle group without changing the original calculation
    results.
    """
    if pmm_df is None or pmm_df.empty:
        return pd.DataFrame()

    df = pmm_df.copy()
    finite_angles = (
        df["Angle [deg]"]
        .dropna()
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .unique()
    )
    if len(finite_angles) == 0:
        return df

    axial_anchors = df[
        df["Angle [deg]"].isna()
        & np.isclose(pd.to_numeric(df["phiMnx [kN-m]"], errors="coerce"), 0.0)
        & np.isclose(pd.to_numeric(df["phiMny [kN-m]"], errors="coerce"), 0.0)
        & np.isfinite(pd.to_numeric(df["phiPn [kN]"], errors="coerce"))
    ].copy()
    if axial_anchors.empty:
        return df

    replicated = []
    for _, anchor in axial_anchors.iterrows():
        for angle in finite_angles:
            row = anchor.copy()
            row["Angle [deg]"] = float(angle)
            replicated.append(row)

    if replicated:
        df = pd.concat([df, pd.DataFrame(replicated)], ignore_index=True)
    return df


def calc_phi_tension_capacity_from_bars(bar_df):
    """Return factored pure tensile capacity φTn of longitudinal steel [kN]."""
    if bar_df is None or bar_df.empty:
        return 0.0
    as_mm2 = pd.to_numeric(bar_df.get("As_mm2", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    fy_mpa = pd.to_numeric(bar_df.get("fy_mpa", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    return float(0.90 * np.sum(as_mm2 * fy_mpa) / 1000.0)


def tension_utilization_for_pu(pu_kN, phi_tn_kN):
    """Pure uplift/tension steel check. Compression cases return zero utilization."""
    pu = float(pu_kN)
    if pu >= 0.0:
        return 0.0, "N/A"
    if phi_tn_kN <= 1e-9:
        return np.inf, "No tension steel capacity"
    util = abs(pu) / float(phi_tn_kN)
    return float(util), "OK" if util <= 1.0 else "NG"

def pmm_slice_at_p(pmm_df, pu_kN):
    """Interpolate an Mx-My capacity slice at a constant factored axial load.

    Pure axial compression/tension anchors are expanded to every finite angle
    so the constant-Pu slice remains available down to the pure uplift cap.
    """
    if pmm_df is None or pmm_df.empty:
        return pd.DataFrame(columns=["phiMnx [kN-m]", "phiMny [kN-m]", "phiPn [kN]", "Angle [deg]"])

    pmm_work = expand_pmm_axial_anchors_for_slices(pmm_df)
    rows = []
    for angle, grp in pmm_work.dropna(subset=["Angle [deg]"]).groupby("Angle [deg]"):
        grp = grp[np.isfinite(grp["phiPn [kN]"])].copy()
        if len(grp) < 2:
            continue
        grp = grp.sort_values("phiPn [kN]")
        grouped = grp.groupby(grp["phiPn [kN]"].round(1), as_index=False).agg({
            "phiMnx [kN-m]": "mean",
            "phiMny [kN-m]": "mean",
            "phiPn [kN]": "mean",
        }).sort_values("phiPn [kN]")
        p_vals = grouped["phiPn [kN]"].to_numpy(dtype=float)
        if pu_kN < p_vals.min() or pu_kN > p_vals.max():
            # Do not silently substitute a nearest point outside the available
            # axial range. A constant-Pu slice must be interpolated only from
            # angles that actually bracket the requested Pu.
            continue
        mx = float(np.interp(pu_kN, p_vals, grouped["phiMnx [kN-m]"].to_numpy(dtype=float)))
        my = float(np.interp(pu_kN, p_vals, grouped["phiMny [kN-m]"].to_numpy(dtype=float)))
        p_use = float(pu_kN)
        rows.append({
            "Angle [deg]": float(angle),
            "phiMnx [kN-m]": mx,
            "phiMny [kN-m]": my,
            "phiPn [kN]": p_use,
        })

    slice_df = pd.DataFrame(rows).sort_values("Angle [deg]").reset_index(drop=True)
    if not slice_df.empty:
        slice_df = pd.concat([slice_df, slice_df.iloc[[0]]], ignore_index=True)
    return slice_df

def pmm_slice_radial_capacity(slice_df, theta_rad):
    """Return radial M capacity on a constant-Pu Mx-My slice at a demand angle."""
    if slice_df is None or slice_df.empty:
        return 0.0

    x_vals = slice_df["phiMnx [kN-m]"].to_numpy(dtype=float)
    y_vals = slice_df["phiMny [kN-m]"].to_numpy(dtype=float)
    radii = np.hypot(x_vals, y_vals)
    angles = np.mod(np.arctan2(y_vals, x_vals), 2.0 * np.pi)
    valid = np.isfinite(radii) & np.isfinite(angles) & (radii > 1e-9)
    if valid.sum() < 4:
        return 0.0

    polar = pd.DataFrame({
        "angle": angles[valid],
        "radius": radii[valid],
    })
    polar["angle_key"] = polar["angle"].round(6)
    polar = (
        polar.groupby("angle_key", as_index=False)
        .agg({"angle": "mean", "radius": "max"})
        .sort_values("angle")
    )
    if len(polar) < 4:
        return 0.0

    angle_vals = polar["angle"].to_numpy(dtype=float)
    radius_vals = polar["radius"].to_numpy(dtype=float)
    angle_ext = np.concatenate([angle_vals[-1:] - 2.0 * np.pi, angle_vals, angle_vals[:1] + 2.0 * np.pi])
    radius_ext = np.concatenate([radius_vals[-1:], radius_vals, radius_vals[:1]])
    theta = float(np.mod(theta_rad, 2.0 * np.pi))
    return float(np.interp(theta, angle_ext, radius_ext))

def prepare_pmm_surface_for_checks(pmm_df, clamp_tol_ratio=0.002):
    """Pre-filter a PMM surface once so many demand points can be checked faster."""
    if pmm_df is None or pmm_df.empty:
        return pd.DataFrame(), 0.0, 0.0, 0.0
    finite = expand_pmm_axial_anchors_for_slices(pmm_df).dropna(subset=["Angle [deg]"]).copy()
    finite = finite[
        np.isfinite(finite["phiMnx [kN-m]"])
        & np.isfinite(finite["phiMny [kN-m]"])
        & np.isfinite(finite["phiPn [kN]"])
    ]
    if finite.empty:
        return finite, 0.0, 0.0, 0.0
    p_min = float(finite["phiPn [kN]"].min())
    p_max = float(finite["phiPn [kN]"].max())
    tol = max((p_max - p_min) * float(clamp_tol_ratio), 1e-6)
    return finite, p_min, p_max, tol


def clamp_pu_to_pmm_range(pu_kN, p_min, p_max, tol):
    """Clamp tiny axial-load round-off excursions; flag real out-of-range demands."""
    pu_use = float(pu_kN)
    if pu_use < p_min:
        if pu_use >= p_min - tol:
            return float(p_min), None
        return pu_use, "Pu below PMM range"
    if pu_use > p_max:
        if pu_use <= p_max + tol:
            return float(p_max), None
        return pu_use, "Pu above PMM range"
    return pu_use, None


def pmm_utilization_from_slice(slice_df, pu_use, mux_kNm, muy_kNm, out_of_range_status=None):
    """Check one biaxial demand using a precomputed constant-Pu PMM slice."""
    if out_of_range_status:
        return {
            "utilization": np.inf,
            "capacity_m": 0.0,
            "capacity_mux": 0.0,
            "capacity_muy": 0.0,
            "pu_used": float(pu_use),
            "status": out_of_range_status,
        }
    demand_m = float(np.hypot(mux_kNm, muy_kNm))
    theta = float(np.arctan2(muy_kNm, mux_kNm)) if demand_m > 1e-9 else 0.0
    capacity_m = pmm_slice_radial_capacity(slice_df, theta)
    if demand_m <= 1e-9:
        utilization = 0.0
    elif capacity_m <= 1e-9:
        utilization = np.inf
    else:
        utilization = demand_m / capacity_m
    return {
        "utilization": float(utilization),
        "capacity_m": float(capacity_m),
        "capacity_mux": float(capacity_m * np.cos(theta)),
        "capacity_muy": float(capacity_m * np.sin(theta)),
        "pu_used": float(pu_use),
        "status": "OK" if utilization <= 1.0 else "NG",
    }


def pmm_surface_radial_utilization(pmm_df, pu_kN, mux_kNm, muy_kNm, clamp_tol_ratio=0.002):
    """Check biaxial PMM demand by radial interpolation on the 3D PMM surface."""
    finite, p_min, p_max, tol = prepare_pmm_surface_for_checks(pmm_df, clamp_tol_ratio)
    if finite.empty:
        return {
            "utilization": np.inf,
            "capacity_m": 0.0,
            "capacity_mux": 0.0,
            "capacity_muy": 0.0,
            "pu_used": float(pu_kN),
            "status": "No PMM surface",
        }
    pu_use, out_of_range_status = clamp_pu_to_pmm_range(pu_kN, p_min, p_max, tol)
    slice_df = pd.DataFrame() if out_of_range_status else pmm_slice_at_p(finite, pu_use)
    return pmm_utilization_from_slice(slice_df, pu_use, mux_kNm, muy_kNm, out_of_range_status)

def pmm_surface_grid(pmm_df, n_levels=28):
    """Build PMM surface matrices by stacking constant-Pu interaction slices."""
    finite = expand_pmm_axial_anchors_for_slices(pmm_df).dropna(subset=["Angle [deg]"]).copy()
    finite = finite[np.isfinite(finite["Angle [deg]"])]
    finite = finite[
        np.isfinite(finite["phiMnx [kN-m]"])
        & np.isfinite(finite["phiMny [kN-m]"])
        & np.isfinite(finite["phiPn [kN]"])
    ]
    if finite.empty:
        return None

    p_min = float(finite["phiPn [kN]"].min())
    p_max = float(finite["phiPn [kN]"].max())
    if p_max <= p_min:
        return None

    p_levels = np.linspace(p_min, p_max, int(n_levels))
    slices = [pmm_slice_at_p(finite, p_level) for p_level in p_levels]
    slices = [sl for sl in slices if sl is not None and not sl.empty]
    if len(slices) < 2:
        return None

    min_len = min(len(sl) for sl in slices)
    if min_len < 4:
        return None

    mx_rows, my_rows, p_rows = [], [], []
    for sl in slices:
        sl = sl.sort_values("Angle [deg]").iloc[:min_len].copy()
        mx_rows.append(sl["phiMnx [kN-m]"].to_numpy(dtype=float))
        my_rows.append(sl["phiMny [kN-m]"].to_numpy(dtype=float))
        p_rows.append(np.full(min_len, float(sl["phiPn [kN]"].mean())))

    mx = np.asarray(mx_rows)
    my = np.asarray(my_rows)
    p = np.asarray(p_rows)
    return mx, my, p

def pmm_polar_surface_grid(pmm_df, n_levels=30, n_angles=73):
    """Build a closed PMM surface by stacking polar Mx-My capacity slices, including Pu < 0."""
    finite = expand_pmm_axial_anchors_for_slices(pmm_df).dropna(subset=["Angle [deg]"]).copy()
    finite = finite[
        np.isfinite(finite["phiMnx [kN-m]"])
        & np.isfinite(finite["phiMny [kN-m]"])
        & np.isfinite(finite["phiPn [kN]"])
    ]
    if finite.empty:
        return None

    p_min = float(finite["phiPn [kN]"].min())
    p_max = float(finite["phiPn [kN]"].max())
    if p_max <= p_min:
        return None

    theta = np.linspace(0.0, 2.0 * np.pi, int(n_angles))
    p_levels = np.linspace(p_min, p_max, int(n_levels))
    mx_rows, my_rows, p_rows = [], [], []

    for p_level in p_levels:
        sl = pmm_slice_at_p(finite, p_level)
        if sl is None or sl.empty:
            continue

        x_vals = sl["phiMnx [kN-m]"].to_numpy(dtype=float)
        y_vals = sl["phiMny [kN-m]"].to_numpy(dtype=float)
        radii = np.hypot(x_vals, y_vals)
        angles = np.mod(np.arctan2(y_vals, x_vals), 2.0 * np.pi)
        valid = np.isfinite(radii) & np.isfinite(angles) & (radii > 1e-9)
        if valid.sum() < 4:
            continue

        polar = pd.DataFrame({
            "angle": angles[valid],
            "radius": radii[valid],
        })
        polar["angle_key"] = polar["angle"].round(6)
        polar = (
            polar.groupby("angle_key", as_index=False)
            .agg({"angle": "mean", "radius": "max"})
            .sort_values("angle")
        )
        if len(polar) < 4:
            continue

        angle_vals = polar["angle"].to_numpy(dtype=float)
        radius_vals = polar["radius"].to_numpy(dtype=float)
        angle_ext = np.concatenate([angle_vals[-1:] - 2.0 * np.pi, angle_vals, angle_vals[:1] + 2.0 * np.pi])
        radius_ext = np.concatenate([radius_vals[-1:], radius_vals, radius_vals[:1]])
        radius_grid = np.interp(theta, angle_ext, radius_ext)

        mx_rows.append(radius_grid * np.cos(theta))
        my_rows.append(radius_grid * np.sin(theta))
        p_rows.append(np.full_like(theta, float(p_level)))

    if len(mx_rows) < 2:
        return None

    return np.asarray(mx_rows), np.asarray(my_rows), np.asarray(p_rows)

def calculate_rebar_params(df_results, Ap):
    """Calculate rebar design parameters"""
    kh_valid = pd.to_numeric(df_results["kh_x [kN/m3]"], errors="coerce").replace(0, np.nan).dropna()
    kh_max_surface = float(kh_valid.iloc[0]) if not kh_valid.empty else 0.0
    kh_min_deep = float(kh_valid.iloc[-1]) if not kh_valid.empty else 0.0
    if kh_max_surface <= 5000:
        heuristic_ratio = 0.015
    elif kh_max_surface <= 15000:
        heuristic_ratio = 0.010
    else:
        heuristic_ratio = 0.008
    as_ratio_rec = max(heuristic_ratio, ACI_MIN_LONG_RATIO)
    As_min = Ap * as_ratio_rec
    return kh_max_surface, kh_min_deep, as_ratio_rec, As_min

def calc_pile_design_summary(
    pile_type, D, B, H, fc, cover_mm, main_bar, tie_bar,
    direction, Pu_kN, shear_kN, moment_kNm, n_main_bars,
    n_b_face, n_h_face, n_tie_legs, as_ratio_rec
):
    """Preliminary RC pile design summary based on axial, moment, and shear demand."""
    main_dia_mm = float(REBAR_DB[main_bar]["dia_mm"])
    tie_dia_mm = float(REBAR_DB[tie_bar]["dia_mm"])
    fy_main = get_rebar_fy_mpa(main_bar)
    fy_tie = get_rebar_fy_mpa(tie_bar)
    ag_mm2 = calc_pile_props("Round" if pile_type == "Round" else "Square", D, B, H, fc)[0] * 1e6

    if pile_type == "Round":
        total_main_bars = max(int(n_main_bars or 6), 4)
        section_depth_mm = D * 1000.0
        bw_mm = D * 1000.0
    else:
        total_main_bars = max(2 * (int(n_b_face or 3) + int(n_h_face or 3)) - 4, 4)
        if direction == "X":
            section_depth_mm = B * 1000.0
            bw_mm = H * 1000.0
        else:
            section_depth_mm = H * 1000.0
            bw_mm = B * 1000.0

    d_eff_mm = max(section_depth_mm - cover_mm - tie_dia_mm - main_dia_mm / 2.0, section_depth_mm * 0.65)
    as_bar_mm2 = get_rebar_area_mm2(main_bar)
    as_provided_mm2 = total_main_bars * as_bar_mm2
    as_min_mm2 = max(as_ratio_rec * ag_mm2, ACI_MIN_LONG_RATIO * ag_mm2)

    phi_axial = 0.65
    pu_n = max(float(Pu_kN), 0.0) * 1000.0
    axial_rhs = pu_n / phi_axial - 0.85 * fc * ag_mm2
    axial_den = max(fy_main - 0.85 * fc, 1e-6)
    as_req_axial_mm2 = max(axial_rhs / axial_den, 0.0)

    phi_flex = 0.90
    lever_arm_mm = max(0.85 * d_eff_mm, 1e-6)
    mu_nmm = abs(float(moment_kNm)) * 1e6
    as_req_flex_mm2 = mu_nmm / max(phi_flex * fy_main * lever_arm_mm, 1e-6)
    as_req_total_mm2 = max(as_min_mm2, as_req_axial_mm2 + as_req_flex_mm2)

    av_mm2 = max(int(n_tie_legs), 2) * get_rebar_area_mm2(tie_bar)
    phi_shear = 0.75
    vu_n = abs(float(shear_kN)) * 1000.0
    vc_n = 0.17 * np.sqrt(fc) * bw_mm * d_eff_mm
    if vu_n <= phi_shear * vc_n:
        s_req_mm = min(d_eff_mm / 2.0, 300.0)
        shear_status = "Concrete shear capacity is adequate; provide minimum confinement ties."
    else:
        vs_req_n = vu_n / phi_shear - vc_n
        s_req_mm = av_mm2 * fy_tie * d_eff_mm / max(vs_req_n, 1e-6)
        shear_status = "Transverse reinforcement is required from the preliminary shear check."
    s_code_max_mm = min(d_eff_mm / 2.0, 300.0)
    s_rec_mm = max(min(s_req_mm, s_code_max_mm), 75.0)

    return {
        "total_main_bars": total_main_bars,
        "d_eff_mm": d_eff_mm,
        "bw_mm": bw_mm,
        "fy_main": fy_main,
        "fy_tie": fy_tie,
        "as_bar_mm2": as_bar_mm2,
        "as_provided_mm2": as_provided_mm2,
        "as_min_mm2": as_min_mm2,
        "as_req_axial_mm2": as_req_axial_mm2,
        "as_req_flex_mm2": as_req_flex_mm2,
        "as_req_total_mm2": as_req_total_mm2,
        "main_ok": as_provided_mm2 >= as_req_total_mm2,
        "av_mm2": av_mm2,
        "vc_n": vc_n,
        "s_req_mm": s_req_mm,
        "s_rec_mm": s_rec_mm,
        "shear_status": shear_status,
    }

def build_excel(df_results, df_row_results, df_soil, N_tip, Kv_tip, kv_tip, D_tip_eq, Ap, Ep, Ipx, Ipy, B, H, L, fc,
                node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta, beta_x, beta_y,
                kh_max_surface, kh_min_deep, as_ratio_rec, As_min, use_group, spring_output):
    """Build Excel file with all calculation results."""
    try:
        import xlsxwriter  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Excel export dependency: XlsxWriter. "
            "Install project requirements with: pip install -r requirements.txt"
        ) from exc

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        wb = writer.book
        fmt_title = wb.add_format({'bold': True, 'font_size': 12, 'bg_color': '#1a4f8a', 'font_color': 'white', 'border': 1})
        fmt_header = wb.add_format({'bold': True, 'bg_color': '#BDD7EE', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        fmt_num = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        fmt_bold = wb.add_format({'bold': True, 'border': 1})
        fmt_info = wb.add_format({'italic': True, 'font_color': '#555555'})

        ws1 = wb.add_worksheet("Lateral Springs")
        ws1.write(0, 0, f"Lateral Soil Spring Stiffness - Method: {method}", fmt_title)
        ws1.write(1, 0, f"Pile: B={B:.2f}m H={H:.2f}m L={L:.1f}m fc={fc:.0f}MPa dL={node_spacing:.2f}m p-mult={Pmult:.3f}", fmt_info)
        headers = list(df_results.columns)
        for ci, h in enumerate(headers):
            ws1.write(3, ci, h, fmt_header)
        for ri, row in df_results.iterrows():
            for ci, val in enumerate(row):
                if isinstance(val, float) and not np.isnan(val):
                    ws1.write(4 + ri, ci, val, fmt_num)
                else:
                    ws1.write(4 + ri, ci, val if not (isinstance(val, float) and np.isnan(val)) else '', fmt_num)
        ws1.set_column(0, len(headers)-1, 15)

        ws1b = wb.add_worksheet("Lateral Springs Row")
        ws1b.write(0, 0, f"Lateral Soil Spring Stiffness - Row-based - Method: {method}", fmt_title)
        ws1b.write(1, 0, "One row per depth, loading direction, and pile row. Kspring = kh x Deq x tributary length x fm(row).", fmt_info)
        if use_group and df_row_results is not None and not df_row_results.empty:
            row_headers = list(df_row_results.columns)
            for ci, h in enumerate(row_headers):
                ws1b.write(3, ci, h, fmt_header)
            for ri, row in df_row_results.iterrows():
                for ci, val in enumerate(row):
                    if isinstance(val, float) and not np.isnan(val):
                        ws1b.write(4 + ri, ci, val, fmt_num)
                    else:
                        ws1b.write(4 + ri, ci, val if not (isinstance(val, float) and np.isnan(val)) else '', fmt_num)
            ws1b.set_column(0, len(row_headers)-1, 15)
            ws1b.set_column(5, 5, 16)
            ws1b.set_column(11, 11, 18)
        else:
            ws1b.write(3, 0, "Row-based table is available when Apply Group Effect is enabled.", fmt_info)
            ws1b.set_column(0, 0, 70)

        ws2 = wb.add_worksheet("Vertical Tip Spring")
        ws2.write(0, 0, "Vertical Tip Spring Stiffness", fmt_title)
        tip_data = [
            ("Parameter", "Value", "Unit"),
            ("N-SPT at pile tip", N_tip, "blow/30cm"),
            ("E0 at tip", (2800 if design_stage == "Normal" else 5600) * N_tip, "kN/m2"),
            ("Equivalent circular D for JRA size effect", D_tip_eq, "m"),
            ("Pile tip area Ap", Ap, "m2"),
            ("kv_tip unit tip modulus", round(kv_tip, 1), "kN/m3"),
            ("Kv_tip vertical spring", round(Kv_tip, 1), "kN/m"),
            ("Design Stage", design_stage, "-"),
        ]
        for ri, row in enumerate(tip_data):
            for ci, val in enumerate(row):
                ws2.write(2 + ri, ci, val, fmt_bold if ci == 0 else (fmt_num if isinstance(val, (int, float)) else fmt_bold))
        ws2.set_column(0, 0, 28); ws2.set_column(1, 1, 18); ws2.set_column(2, 2, 12)

        ws3 = wb.add_worksheet("Summary")
        ws3.write(0, 0, "Project Summary & Pile Properties", fmt_title)
        summary = [
            ("Pile Width B [m]", B, "m"),
            ("Pile Height H [m]", H, "m"),
            ("Pile Length L [m]", L, "m"),
            ("fc [MPa]", fc, "MPa"),
            ("Ep [kN/m2]", round(Ep, 0), "kN/m2"),
            ("Ap [m2]", round(Ap, 5), "m2"),
            ("Ix bending about X [m4]", round(Ipx, 6), "m4"),
            ("Iy bending about Y [m4]", round(Ipy, 6), "m4"),
            ("Node Spacing dL [m]", node_spacing, "m"),
            ("kh Method", method, "-"),
            ("Design Stage", design_stage, "-"),
            ("Water Table [m]", water_table, "m"),
            ("Scour Depth [m]", scour_depth, "m"),
            ("p-multiplier", Pmult, "-"),
            ("Spring Output", spring_output, "-"),
            ("Excel Export", "Global average + row-based sheets", "-"),
            ("Beta X characteristic value [1/m]", round(beta_x, 4), "1/m"),
            ("Beta Y characteristic value [1/m]", round(beta_y, 4), "1/m"),
            ("kv_tip [kN/m3]", round(kv_tip, 1), "kN/m3"),
            ("Kv_tip [kN/m]", round(Kv_tip, 1), "kN/m"),
        ]
        for ri, (k, v, u) in enumerate(summary):
            ws3.write(2 + ri, 0, k, fmt_bold)
            ws3.write(2 + ri, 1, v, fmt_num if isinstance(v, float) else fmt_bold)
            ws3.write(2 + ri, 2, u, fmt_bold)
        ws3.set_column(0, 0, 34); ws3.set_column(1, 1, 18); ws3.set_column(2, 2, 10)

        df_soil.to_excel(writer, sheet_name="Soil Profile", index=False)
        ws4 = writer.sheets["Soil Profile"]
        ws4.set_column(0, len(df_soil.columns)-1, 15)

        ws5 = wb.add_worksheet("Rebar Design Guide")
        ws5.write(0, 0, "Pile Reinforcement Design Guide (Based on Spring Results)", fmt_title)
        rebar_data = [
            ("Parameter", "Value", "Remark / Reference"),
            ("Surface kh_x [kN/m3]", round(kh_max_surface, 1), "Used to evaluate soil stiffness condition"),
            ("Deep kh_x [kN/m3]", round(kh_min_deep, 1), "Stiffness at pile tip layer"),
            ("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%", "Preliminary heuristic, not less than ACI 318 10.6.1.1 minimum"),
            ("Minimum As [m2]", round(As_min, 4), "As = Ap x Ratio"),
            ("ACI longitudinal steel limits", "1.0% to 8.0% Ag", "ACI 318-19 10.6.1.1 for nonprestressed columns"),
        ]
        for ri, row in enumerate(rebar_data):
            for ci, val in enumerate(row):
                fmt_use = fmt_bold if ci == 0 else fmt_num if isinstance(val, (int, float)) else fmt_info
                ws5.write(2 + ri, ci, val, fmt_use)
        ws5.set_column(0, 0, 32); ws5.set_column(1, 1, 20); ws5.set_column(2, 2, 50)

    buf.seek(0)
    return buf.read()


def _df_to_markdown_table(df, max_rows=40):
    """Small dependency-free markdown table formatter for report export."""
    if df is None or len(df) == 0:
        return "_No data available._"
    view = df.copy()
    truncated = len(view) > max_rows
    if truncated:
        view = view.head(max_rows).copy()
    view = view.fillna("")
    cols = [str(c) for c in view.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        vals = []
        for val in row.tolist():
            if isinstance(val, (float, np.floating)):
                vals.append(f"{float(val):,.3f}".rstrip("0").rstrip("."))
            else:
                vals.append(str(val).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    if truncated:
        lines.append(f"\n_Note: table truncated to first {max_rows} rows in markdown preview._")
    return "\n".join(lines)



def build_pile_design_qa_checklist(report):
    """Return a compact QA checklist for the latest pile design report."""
    if not report:
        return pd.DataFrame([{"Status": "NG", "Check": "Calculation run", "Finding": "No latest pile design calculation found.", "Action": "Run / Update Pile Design."}])
    rows = []
    meta = report.get("meta", {})
    project = report.get("project", {})
    inputs = report.get("inputs", {})
    summary = report.get("summary", {})
    load_cases = report.get("load_cases", pd.DataFrame())
    demand_df = report.get("demand_df", pd.DataFrame())
    sensitivity_df = report.get("sensitivity_df", pd.DataFrame())

    def add(status, check, finding, action=""):
        rows.append({"Status": status, "Check": check, "Finding": finding, "Action": action})

    if str(project.get("project_title", "")).strip():
        add("OK", "Project title", project.get("project_title", "-"), "")
    else:
        add("WARN", "Project title", "Project title is blank.", "Fill project metadata before issuing report.")

    if str(meta.get("load_case_source", "")).strip() and meta.get("load_case_source") != "Manual / in-app table":
        add("OK", "Load-case source", str(meta.get("load_case_source")), "")
    else:
        add("WARN", "Load-case source", "Load cases are manual or source was not identified.", "Attach STM transfer file or document source in notes.")

    if load_cases is not None and len(load_cases) > 0:
        add("OK", "Active load cases", f"{len(load_cases)} active case(s) checked.", "")
    else:
        add("NG", "Active load cases", "No active load cases found in report.", "Check load-case table and rerun.")

    head = str(inputs.get("head_condition", ""))
    if head.startswith("Fixed"):
        add("OK", "Pile-head boundary", "Fixed head selected; head reaction moment solved internally.", "Compare with Free/Rotational sensitivity for design confidence.")
    elif head.startswith("Rotational"):
        add("WARN", "Pile-head boundary", f"Rotational spring selected, Kθ = {float(inputs.get('ktheta_head', 0.0)):,.0f} kN-m/rad.", "Use sensitivity or calibration to justify Kθ.")
    else:
        add("WARN", "Pile-head boundary", "Free-head / shear-only model selected.", "Confirm this reflects pile-cap restraint, or compare fixed-head case.")

    if sensitivity_df is not None and len(sensitivity_df) > 0:
        add("OK", "Head-boundary sensitivity", f"{len(sensitivity_df)} sensitivity result row(s) included.", "")
    else:
        add("WARN", "Head-boundary sensitivity", "Sensitivity was not run.", "Run head-condition sensitivity before finalizing design assumptions.")

    basis = str(inputs.get("design_demand_basis", summary.get("design_demand_basis", "")))
    if basis.startswith("Case-by-case"):
        add("OK", "Design demand basis", basis, "")
    else:
        add("WARN", "Design demand basis", basis or "Not recorded.", "Case-by-case governing is recommended for final checks.")

    max_util = float(summary.get("max_util", 0.0) or 0.0)
    if max_util <= 1.0:
        add("OK", "Overall utilization", f"Overall utilization = {max_util:.3f}", "")
    else:
        add("NG", "Overall utilization", f"Overall utilization = {max_util:.3f} > 1.0", "Revise section/reinforcement or assumptions.")

    if bool(summary.get("provided_tie_spacing_ok", True)):
        add("OK", "Tie spacing", "Provided tie spacing is not greater than preliminary recommended spacing.", "")
    else:
        add("WARN", "Tie spacing", "Provided tie spacing exceeds preliminary recommended spacing.", "Review shear/confinement detailing.")

    if demand_df is not None and len(demand_df) > 0 and "Min Pu [kN]" in demand_df.columns:
        min_pu = float(pd.to_numeric(demand_df["Min Pu [kN]"], errors="coerce").min())
        if min_pu < 0.0:
            add("WARN", "Uplift/tension", f"Minimum Pu = {min_pu:,.1f} kN (tension/uplift).", "Check pile uplift capacity, anchorage, and pile-cap transfer.")
        else:
            add("OK", "Uplift/tension", f"Minimum Pu = {min_pu:,.1f} kN.", "")

    method = str(inputs.get("kh_method", ""))
    if method == "Broms 1964":
        add("WARN", "kh method", "Broms method selected; this is capacity-oriented.", "Treat elastic spring values as preliminary and cross-check with another method.")
    elif method:
        add("OK", "kh method", method, "")

    return pd.DataFrame(rows)


def build_final_report_review_checklist(report):
    """Return final report review / punch-list checklist before issuing a report.

    This is a reporting QA layer only. It does not change calculation results.
    The checklist focuses on whether the exported report is complete, traceable,
    and safe to issue for engineering review.
    """
    if not report:
        return pd.DataFrame([{
            "Group": "Run state", "Status": "NG", "Review item": "Latest calculation",
            "Finding": "No latest pile design calculation is stored.",
            "Action before issue": "Run / Update Pile Design before exporting the report."
        }])

    rows = []
    meta = report.get("meta", {}) or {}
    project = report.get("project", {}) or {}
    inputs = report.get("inputs", {}) or {}
    summary = report.get("summary", {}) or {}
    load_cases = report.get("load_cases", pd.DataFrame())
    demand_df = report.get("demand_df", pd.DataFrame())
    profile_df = report.get("profile_df", pd.DataFrame())
    sensitivity_df = report.get("sensitivity_df", pd.DataFrame())
    bar_df = report.get("bar_df", pd.DataFrame())
    pmm_df = report.get("pmm_df", pd.DataFrame())
    mx_curve = report.get("mx_curve", pd.DataFrame())
    my_curve = report.get("my_curve", pd.DataFrame())
    qa_checklist = report.get("qa_checklist", build_pile_design_qa_checklist(report))

    def add(group, status, item, finding, action=""):
        rows.append({
            "Group": group,
            "Status": status,
            "Review item": item,
            "Finding": finding,
            "Action before issue": action,
        })

    # A. Visual / report completeness
    required_project = ["project_title", "structure_name", "designer", "checker", "revision"]
    missing_project = [k for k in required_project if not str(project.get(k, "")).strip()]
    if missing_project:
        add("A. Report completeness", "WARN", "Project metadata",
            "Missing fields: " + ", ".join(missing_project),
            "Fill project metadata in the sidebar before final issue.")
    else:
        add("A. Report completeness", "OK", "Project metadata",
            "Project title, structure/location, designer, checker, and revision are recorded.")

    if load_cases is not None and len(load_cases) > 0:
        add("A. Report completeness", "OK", "Load case table",
            f"{len(load_cases)} active load case(s) will be included in the report.")
    else:
        add("A. Report completeness", "NG", "Load case table",
            "No active load cases are available.", "Import or enter load cases and rerun design.")

    if demand_df is not None and len(demand_df) > 0:
        add("A. Report completeness", "OK", "Load case result table",
            f"{len(demand_df)} checked demand row(s) are available.")
    else:
        add("A. Report completeness", "NG", "Load case result table",
            "No design-demand table is available.", "Rerun pile design and confirm results appear in Pile Design.")

    if profile_df is not None and len(profile_df) > 0:
        profile_cols = set(profile_df.columns)
        force_cols = {"Pu [kN]", "Mux [kN-m]", "Muy [kN-m]", "V resultant [kN]"}
        disp_cols = {"Disp X [mm]", "Disp Y [mm]", "Disp resultant [mm]"}
        if force_cols.issubset(profile_cols) and disp_cols.issubset(profile_cols):
            add("A. Report completeness", "OK", "Force/displacement diagrams",
                "Profile data includes force and displacement diagram columns.")
        else:
            add("A. Report completeness", "WARN", "Force/displacement diagrams",
                "Profile data exists but some diagram columns are missing.",
                "Review the exported Word report figures and QA workbook Force_Profile sheet.")
    else:
        add("A. Report completeness", "NG", "Force/displacement diagrams",
            "No pile-depth profile data is available for report figures.", "Rerun pile design.")

    if bar_df is not None and len(bar_df) > 0:
        add("A. Report completeness", "OK", "Section reinforcement figure",
            f"{len(bar_df)} longitudinal bar point(s) are available for section/rebar figure.")
    else:
        add("A. Report completeness", "NG", "Section reinforcement figure",
            "Reinforcement layout data is missing.", "Check reinforcement inputs and rerun design.")

    if pmm_df is not None and len(pmm_df) > 0 and mx_curve is not None and len(mx_curve) > 0 and my_curve is not None and len(my_curve) > 0:
        add("A. Report completeness", "OK", "PMM figures",
            "PMM point cloud and uniaxial curves are available for report figures.")
    else:
        add("A. Report completeness", "WARN", "PMM figures",
            "Some PMM figure data is missing.",
            "Open exported Word report and confirm PMM figures are embedded; otherwise rerun PMM design.")

    # B. Numeric / traceability consistency
    if str(meta.get("load_case_source", "")).strip():
        add("B. Numeric traceability", "OK", "Load-case source",
            str(meta.get("load_case_source")))
    else:
        add("B. Numeric traceability", "WARN", "Load-case source",
            "Load-case source was not recorded.", "Record whether loads came from STM transfer, Excel, or manual input.")

    gov = str(summary.get("governing_case", "") or "").strip()
    if gov and demand_df is not None and len(demand_df) > 0 and "Load Case" in demand_df.columns:
        if gov in demand_df["Load Case"].astype(str).tolist():
            add("B. Numeric traceability", "OK", "Governing case consistency",
                f"Governing case '{gov}' exists in the result table.")
        else:
            add("B. Numeric traceability", "WARN", "Governing case consistency",
                f"Governing case '{gov}' was not found in the result table.",
                "Rerun design and check latest calculation state.")
    else:
        add("B. Numeric traceability", "WARN", "Governing case consistency",
            "Governing case or result table is not available.", "Rerun design.")

    max_util = float(summary.get("max_util", 0.0) or 0.0)
    if max_util <= 1.0:
        add("B. Numeric traceability", "OK", "Overall utilization",
            f"Overall utilization = {max_util:.3f}.")
    else:
        add("B. Numeric traceability", "NG", "Overall utilization",
            f"Overall utilization = {max_util:.3f} > 1.0.",
            "Revise section/reinforcement or design assumptions before issuing as passing design.")

    pmm_util = float(summary.get("max_pmm_util", 0.0) or 0.0)
    tension_util = float(summary.get("max_tension_util", 0.0) or 0.0)
    if pmm_util <= 1.0 and tension_util <= 1.0:
        add("B. Numeric traceability", "OK", "PMM / tension status",
            f"PMM U = {pmm_util:.3f}, tension U = {tension_util:.3f}.")
    else:
        add("B. Numeric traceability", "NG", "PMM / tension status",
            f"PMM U = {pmm_util:.3f}, tension U = {tension_util:.3f}.",
            "Do not issue as passing design without redesign or justification.")

    if bool(summary.get("provided_tie_spacing_ok", True)):
        add("B. Numeric traceability", "OK", "Tie spacing status",
            "Provided tie spacing satisfies the preliminary recommended spacing check.")
    else:
        add("B. Numeric traceability", "WARN", "Tie spacing status",
            "Provided tie spacing exceeds preliminary recommendation.",
            "Review shear/confinement detailing before final issue.")

    # C. Engineering acceptance / assumption check
    basis = str(inputs.get("design_demand_basis", summary.get("design_demand_basis", "")))
    if basis.startswith("Case-by-case"):
        add("C. Engineering acceptance", "OK", "Design demand basis",
            basis)
    else:
        add("C. Engineering acceptance", "WARN", "Design demand basis",
            basis or "Not recorded.",
            "Use case-by-case governing for final design; envelope mode is screening/legacy.")

    head = str(inputs.get("head_condition", ""))
    if head.startswith("Fixed"):
        add("C. Engineering acceptance", "OK", "Pile-head condition",
            "Fixed head selected; head reaction moment is solved internally.")
    elif head.startswith("Rotational"):
        add("C. Engineering acceptance", "WARN", "Pile-head condition",
            f"Rotational spring selected, Kθ = {float(inputs.get('ktheta_head', 0.0)):,.0f} kN-m/rad.",
            "Justify Kθ by sensitivity, calibration, or project assumption note.")
    else:
        add("C. Engineering acceptance", "WARN", "Pile-head condition",
            "Free-head / shear-only selected.",
            "Confirm this matches pile-cap restraint or include fixed-head comparison.")

    if sensitivity_df is not None and len(sensitivity_df) > 0:
        add("C. Engineering acceptance", "OK", "Head-boundary sensitivity",
            f"{len(sensitivity_df)} sensitivity result row(s) included.")
    else:
        add("C. Engineering acceptance", "WARN", "Head-boundary sensitivity",
            "Sensitivity results are not included.",
            "Run head-condition sensitivity before final review.")

    method = str(inputs.get("kh_method", ""))
    if method:
        finding = f"kh method = {method}."
        status = "WARN" if method == "Broms 1964" else "OK"
        action = "Cross-check elastic response with another kh method if Broms is used." if status == "WARN" else ""
        add("C. Engineering acceptance", status, "Soil spring method", finding, action)
    else:
        add("C. Engineering acceptance", "WARN", "Soil spring method", "kh method is not recorded.", "Rerun and check report state.")

    # D. Issue-control items
    qa_statuses = qa_checklist["Status"].astype(str).str.upper().tolist() if qa_checklist is not None and len(qa_checklist) > 0 and "Status" in qa_checklist.columns else []
    if "NG" in qa_statuses:
        add("D. Issue control", "NG", "QA checklist status",
            "QA checklist contains NG item(s).", "Resolve NG items before issuing report.")
    elif "WARN" in qa_statuses:
        add("D. Issue control", "WARN", "QA checklist status",
            "QA checklist contains warning item(s).", "Review warning items and document acceptance if kept.")
    else:
        add("D. Issue control", "OK", "QA checklist status",
            "No NG/WARN item found in QA checklist.")

    notes = str(project.get("project_notes", "") or "").strip()
    if notes:
        add("D. Issue control", "OK", "Reviewer notes",
            "Calculation notes are recorded in project metadata.")
    else:
        add("D. Issue control", "WARN", "Reviewer notes",
            "Calculation notes are blank.",
            "Add design assumptions, source files, and reviewer comments before formal issue.")

    return pd.DataFrame(rows)

def build_pile_design_markdown_report(report):
    """Build a clean markdown QA/design summary from the latest pile-design run."""
    if not report:
        return "No pile design report is available. Run pile design first."
    meta = report.get("meta", {})
    inputs = report.get("inputs", {})
    summary = report.get("summary", {})
    demand_df = report.get("demand_df", pd.DataFrame())
    load_cases = report.get("load_cases", pd.DataFrame())
    sensitivity_df = report.get("sensitivity_df", pd.DataFrame())
    project = report.get("project", {})
    qa_checklist = report.get("qa_checklist", build_pile_design_qa_checklist(report))
    final_review = report.get("final_review_checklist", build_final_report_review_checklist(report))

    lines = []
    lines.append("# Pile Lateral Soil Spring Design Report")
    lines.append("")
    lines.append(f"**Generated:** {meta.get('timestamp', '-')}  ")
    lines.append(f"**App Version:** {meta.get('app_version', '-')}  ")
    lines.append(f"**Load-case source:** {meta.get('load_case_source', 'Manual / in-app table')}  ")
    lines.append("")
    lines.append("## 1. Project / Calculation Header")
    lines.append(f"- Project No.: **{project.get('project_no', '-')}**")
    lines.append(f"- Project Title: **{project.get('project_title', '-')}**")
    lines.append(f"- Structure / Location: **{project.get('structure_name', '-')}**")
    lines.append(f"- Designer: **{project.get('designer', '-')}**")
    lines.append(f"- Checker: **{project.get('checker', '-')}**")
    lines.append(f"- Revision: **{project.get('revision', '-')}**")
    notes = str(project.get('project_notes', '') or '').strip()
    if notes:
        lines.append(f"- Notes: {notes}")
    lines.append("")
    lines.append("## 2. Engineering Assumptions")
    lines.append(f"- kh method: **{inputs.get('kh_method', '-')}**")
    lines.append(f"- Design stage: **{inputs.get('design_stage', '-')}**")
    lines.append(f"- Spring source: **{inputs.get('spring_source', '-')}**")
    lines.append(f"- Head condition: **{inputs.get('head_condition', '-')}**")
    lines.append(f"- Ktheta head: **{inputs.get('ktheta_head', 0.0):,.0f} kN-m/rad**")
    lines.append(f"- Preliminary shear/tie design basis: **{inputs.get('design_demand_basis', summary.get('design_demand_basis', '-'))}**")
    lines.append(f"- Water table: **{inputs.get('water_table', 0.0):.2f} m**; scour depth: **{inputs.get('scour_depth', 0.0):.2f} m**")
    lines.append("- PMM check: preliminary ACI-style strain-compatible phi-PMM surface with uplift/tension steel check.")
    lines.append("- Fixed Head solves the head reaction moment internally; do not double-count external pile-head moment from another model.")
    lines.append("")
    lines.append("## 3. Pile and Reinforcement")
    lines.append(f"- Pile type: **{inputs.get('pile_type', '-')}**")
    lines.append(f"- D/B/H/L: **D={inputs.get('D', 0.0):.2f} m, B={inputs.get('B', 0.0):.2f} m, H={inputs.get('H', 0.0):.2f} m, L={inputs.get('L', 0.0):.2f} m**")
    lines.append(f"- fc: **{inputs.get('fc', 0.0):.1f} MPa**")
    lines.append(f"- Main reinforcement: **{inputs.get('main_bar', '-')}**, provided As = **{summary.get('as_provided_mm2', 0.0):,.0f} mm2**")
    lines.append(f"- Transverse reinforcement: **{inputs.get('tie_bar', '-')} @ {inputs.get('tie_spacing_mm', 0.0):.0f} mm**, system = **{inputs.get('transverse_system', '-')}**")
    lines.append("")
    lines.append("## 4. Load Cases Used")
    lines.append(_df_to_markdown_table(load_cases, max_rows=60))
    lines.append("")
    lines.append("## 5. Governing Design Summary")
    lines.append(f"- Governing load case: **{summary.get('governing_case', '-')}**")
    lines.append(f"- Max Pu: **{summary.get('overall_pu_max', 0.0):,.1f} kN**")
    lines.append(f"- Min Pu: **{summary.get('overall_pu_min', 0.0):,.1f} kN**")
    lines.append(f"- Max |Mux|: **{summary.get('overall_mx', 0.0):,.1f} kN-m**")
    lines.append(f"- Max |Muy|: **{summary.get('overall_my', 0.0):,.1f} kN-m**")
    lines.append(f"- Max |V|: **{summary.get('overall_v', 0.0):,.1f} kN**")
    lines.append(f"- Shear/tie demand source: **{summary.get('shear_design_case', '-')}**")
    lines.append(f"- Shear/tie design demand: **Pu={summary.get('shear_design_pu_kN', 0.0):,.1f} kN, V={summary.get('shear_design_v_kN', 0.0):,.1f} kN, M={summary.get('shear_design_m_kN_m', 0.0):,.1f} kN-m**")
    lines.append(f"- PMM utilization: **{summary.get('max_pmm_util', 0.0):.3f}**")
    lines.append(f"- Tension utilization: **{summary.get('max_tension_util', 0.0):.3f}**")
    lines.append(f"- Overall utilization: **{summary.get('max_util', 0.0):.3f}**")
    lines.append(f"- Overall status: **{summary.get('overall_status', '-')}**")
    lines.append("")
    lines.append("## 6. Load Case Result Table")
    lines.append(_df_to_markdown_table(demand_df.drop(columns=["Case Plot Label"], errors="ignore"), max_rows=80))
    lines.append("")
    lines.append("## 7. Head Boundary Sensitivity")
    if sensitivity_df is not None and len(sensitivity_df) > 0:
        lines.append("The table below brackets pile-head restraint uncertainty. Use it to judge whether free-head displacement or fixed/semi-fixed bending governs.")
        lines.append(_df_to_markdown_table(sensitivity_df, max_rows=80))
    else:
        lines.append("_Sensitivity was not run for the latest design calculation._")
    lines.append("")
    lines.append("## 8. QA Checklist")
    lines.append(_df_to_markdown_table(qa_checklist, max_rows=80))
    lines.append("")
    lines.append("## 9. Final Report Review / Punch List")
    lines.append(_df_to_markdown_table(final_review, max_rows=100))
    lines.append("")
    lines.append("## 10. Limitations / QA Notes")
    lines.append("- This report is generated from the latest in-app calculation state. Re-run pile design after changing input data.")
    lines.append("- Pile structural design is preliminary and must be reviewed against the governing project code, detailing, anchorage, constructability, geotechnical axial capacity, and uplift requirements.")
    lines.append("- Soil spring stiffness is only as reliable as the input soil profile and selected kh method.")
    lines.append("- Case-by-case design basis is recommended. Non-concurrent envelope demand may combine maxima from different load cases and should be treated as a screening check.")
    lines.append("- For final work, keep this report with the exported spring workbook and the source pile-cap STM transfer file.")
    return "\n".join(lines)


def build_pile_design_report_xlsx(report):
    """Build an Excel QA workbook for the latest pile design run."""
    try:
        import xlsxwriter  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing Excel export dependency: XlsxWriter. Install project requirements first.") from exc
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        fmt_title = wb.add_format({'bold': True, 'font_size': 13, 'bg_color': '#1a4f8a', 'font_color': 'white', 'border': 1})
        fmt_header = wb.add_format({'bold': True, 'bg_color': '#BDD7EE', 'border': 1, 'align': 'center'})
        fmt_note = wb.add_format({'italic': True, 'font_color': '#555555'})
        meta = report.get("meta", {}) if report else {}
        inputs = report.get("inputs", {}) if report else {}
        summary = report.get("summary", {}) if report else {}
        project = report.get("project", {}) if report else {}
        qa_checklist = report.get("qa_checklist", build_pile_design_qa_checklist(report)) if report else pd.DataFrame()
        final_review = report.get("final_review_checklist", build_final_report_review_checklist(report)) if report else pd.DataFrame()
        summary_rows = []
        for k, v in project.items():
            summary_rows.append({"Group": "Project", "Item": k, "Value": v})
        for k, v in meta.items():
            summary_rows.append({"Group": "Meta", "Item": k, "Value": v})
        for k, v in inputs.items():
            summary_rows.append({"Group": "Input", "Item": k, "Value": v})
        for k, v in summary.items():
            summary_rows.append({"Group": "Summary", "Item": k, "Value": v})
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="QA_Summary", index=False, startrow=3)
        ws = writer.sheets["QA_Summary"]
        ws.write(0, 0, "Pile Soil Spring Design QA Report", fmt_title)
        ws.write(1, 0, "Generated from latest in-app pile design run. Re-run calculation after input changes.", fmt_note)
        for ci, col in enumerate(["Group", "Item", "Value"]):
            ws.write(3, ci, col, fmt_header)
        ws.set_column(0, 0, 16); ws.set_column(1, 1, 34); ws.set_column(2, 2, 42)
        sheet_map = {
            "QA_Checklist": qa_checklist,
            "Final_Report_Review": final_review,
            "Load_Cases": report.get("load_cases", pd.DataFrame()) if report else pd.DataFrame(),
            "Design_Demands": report.get("demand_df", pd.DataFrame()) if report else pd.DataFrame(),
            "Force_Profile": report.get("profile_df", pd.DataFrame()) if report else pd.DataFrame(),
            "Head_Sensitivity": report.get("sensitivity_df", pd.DataFrame()) if report else pd.DataFrame(),
        }
        for sheet, df in sheet_map.items():
            safe_df = df.copy() if df is not None else pd.DataFrame()
            if safe_df.empty:
                safe_df = pd.DataFrame([{"Note": "No data available for this sheet."}])
            safe_df.to_excel(writer, sheet_name=sheet[:31], index=False, startrow=1)
            ws = writer.sheets[sheet[:31]]
            ws.write(0, 0, sheet.replace("_", " "), fmt_title)
            for ci, col in enumerate(safe_df.columns):
                ws.write(1, ci, col, fmt_header)
                ws.set_column(ci, ci, max(14, min(30, len(str(col)) + 4)))
    buf.seek(0)
    return buf.getvalue()



def _docx_safe_text(value):
    """Return a compact text value safe for DOCX table cells."""
    if value is None:
        return "-"
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return "-"
        return f"{float(value):,.3f}".rstrip("0").rstrip(".")
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    txt = str(value)
    if txt.lower() in ("nan", "none", "<na>"):
        return "-"
    return txt


def _docx_set_cell_shading(cell, fill):
    """Apply simple cell background shading."""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = tc_pr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd")
            tc_pr.append(shd)
        shd.set(qn("w:fill"), fill)
    except Exception:
        pass


def _docx_add_kv_table(doc, title, rows):
    """Add a two-column key/value table to a Word document."""
    if title:
        doc.add_heading(title, level=2)
    clean_rows = [(str(k), _docx_safe_text(v)) for k, v in rows if str(k).strip()]
    if not clean_rows:
        doc.add_paragraph("No data available.")
        return
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Item"
    table.rows[0].cells[1].text = "Value"
    for cell in table.rows[0].cells:
        _docx_set_cell_shading(cell, "BDD7EE")
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for k, v in clean_rows:
        cells = table.add_row().cells
        cells[0].text = k
        cells[1].text = v


def _docx_add_dataframe(doc, title, df, max_rows=25, max_cols=8):
    """Add a compact DataFrame table to DOCX, truncating for report readability."""
    if title:
        doc.add_heading(title, level=2)
    if df is None or len(df) == 0:
        doc.add_paragraph("No data available.")
        return
    view = df.copy()
    if "Case Plot Label" in view.columns:
        view = view.drop(columns=["Case Plot Label"], errors="ignore")
    if len(view.columns) > max_cols:
        view = view.iloc[:, :max_cols].copy()
        doc.add_paragraph(f"Note: table limited to first {max_cols} columns for report readability.")
    truncated = len(view) > max_rows
    if truncated:
        view = view.head(max_rows).copy()
    view = view.fillna("")
    table = doc.add_table(rows=1, cols=len(view.columns))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for j, col in enumerate(view.columns):
        hdr[j].text = str(col)
        _docx_set_cell_shading(hdr[j], "BDD7EE")
        for p in hdr[j].paragraphs:
            for r in p.runs:
                r.bold = True
    for _, row in view.iterrows():
        cells = table.add_row().cells
        for j, val in enumerate(row.tolist()):
            cells[j].text = _docx_safe_text(val)
    if truncated:
        doc.add_paragraph(f"Note: table truncated to first {max_rows} rows. See QA workbook for complete data.")


def _docx_profile_plot_image(profile_df, case_label, columns, title):
    """Create an in-memory PNG plot for DOCX report from pile profile data."""
    if profile_df is None or len(profile_df) == 0:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return None
    df = profile_df.copy()
    if case_label and "Case Plot Label" in df.columns:
        subset = df[df["Case Plot Label"].astype(str) == str(case_label)].copy()
        if not subset.empty:
            df = subset
    if "Depth [m]" not in df.columns:
        return None
    df = df.sort_values("Depth [m]").copy()
    # Create resultant displacement if requested and not already present.
    if "Disp resultant [mm]" in columns and "Disp resultant [mm]" not in df.columns:
        if "Disp X [mm]" in df.columns and "Disp Y [mm]" in df.columns:
            df["Disp resultant [mm]"] = np.sqrt(
                pd.to_numeric(df["Disp X [mm]"], errors="coerce").fillna(0.0) ** 2
                + pd.to_numeric(df["Disp Y [mm]"], errors="coerce").fillna(0.0) ** 2
            )
    available = [c for c in columns if c in df.columns]
    if not available:
        return None
    fig, ax = plt.subplots(figsize=(6.6, 4.0), dpi=150)
    for col in available:
        x = pd.to_numeric(df[col], errors="coerce")
        y = pd.to_numeric(df["Depth [m]"], errors="coerce")
        ax.plot(x, y, marker="o", markersize=2.8, linewidth=1.4, label=col)
    ax.invert_yaxis()
    ax.grid(True, alpha=0.30)
    ax.set_title(title)
    ax.set_xlabel("Value")
    ax.set_ylabel("Depth [m]")
    ax.legend(fontsize=7)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf



def _docx_section_rebar_image(inputs, bar_df):
    """Create a pile section/reinforcement sketch for the DOCX report."""
    if bar_df is None or len(bar_df) == 0:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, Rectangle
    except ModuleNotFoundError:
        return None
    pile_type = str(inputs.get("pile_type", "Round"))
    D = float(inputs.get("D", 1.0))
    B = float(inputs.get("B", D))
    H = float(inputs.get("H", D))
    cover_mm = float(inputs.get("cover_mm", 75.0))
    main_bar = str(inputs.get("main_bar", "Main bar"))
    tie_bar = str(inputs.get("tie_bar", "Tie"))
    x = pd.to_numeric(bar_df.get("x_mm", pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(bar_df.get("y_mm", pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
    if len(x) == 0 or len(y) == 0:
        return None
    fig, ax = plt.subplots(figsize=(4.8, 4.8), dpi=170)
    if pile_type == "Round":
        radius = D * 1000.0 / 2.0
        ax.add_patch(Circle((0.0, 0.0), radius, fill=False, linewidth=2.0))
        ax.add_patch(Circle((0.0, 0.0), max(radius - cover_mm, 0.0), fill=False, linestyle="--", linewidth=1.0))
        lim = radius * 1.35
        title = f"Round pile D = {D:.2f} m"
    else:
        b_mm = B * 1000.0
        h_mm = H * 1000.0
        ax.add_patch(Rectangle((-b_mm/2.0, -h_mm/2.0), b_mm, h_mm, fill=False, linewidth=2.0))
        ax.add_patch(Rectangle((-b_mm/2.0 + cover_mm, -h_mm/2.0 + cover_mm),
                               max(b_mm - 2*cover_mm, 0.0), max(h_mm - 2*cover_mm, 0.0),
                               fill=False, linestyle="--", linewidth=1.0))
        lim = max(b_mm, h_mm) * 0.70
        title = f"Rectangular pile B x H = {B:.2f} x {H:.2f} m"
    ax.scatter(x, y, s=42, marker="o", zorder=3)
    ax.axhline(0.0, linewidth=0.8, alpha=0.45)
    ax.axvline(0.0, linewidth=0.8, alpha=0.45)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.grid(True, alpha=0.20)
    ax.set_title(title)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.text(0.02, 0.98,
            f"{len(bar_df)}-{main_bar}\n{tie_bar} ties\ncover = {cover_mm:.0f} mm",
            transform=ax.transAxes, va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7", alpha=0.9),
            fontsize=8)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _docx_pmm_uniaxial_image(mx_curve, my_curve, demand_df):
    """Create uniaxial PMM interaction curves for the DOCX report."""
    if mx_curve is None or my_curve is None or len(mx_curve) == 0 or len(my_curve) == 0:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return None
    try:
        mx_env = interaction_curve_envelope(mx_curve)
        my_env = interaction_curve_envelope(my_curve)
    except Exception:
        mx_env = mx_curve.copy()
        my_env = my_curve.copy()
    fig, ax = plt.subplots(figsize=(6.8, 4.4), dpi=160)
    if "phiM [kN-m]" in mx_env.columns and "phiPn [kN]" in mx_env.columns:
        ax.plot(mx_env["phiM [kN-m]"], mx_env["phiPn [kN]"], linewidth=2.0, label="about X")
    if "phiM [kN-m]" in my_env.columns and "phiPn [kN]" in my_env.columns:
        ax.plot(my_env["phiM [kN-m]"], my_env["phiPn [kN]"], linewidth=2.0, linestyle="--", label="about Y")
    if demand_df is not None and len(demand_df) > 0:
        if "Max |Mux| [kN-m]" in demand_df.columns and "Max Pu [kN]" in demand_df.columns:
            ax.scatter(demand_df["Max |Mux| [kN-m]"], demand_df["Max Pu [kN]"], marker="x", s=38, label="Pu-Mux demand")
        if "Max |Muy| [kN-m]" in demand_df.columns and "Max Pu [kN]" in demand_df.columns:
            ax.scatter(demand_df["Max |Muy| [kN-m]"], demand_df["Max Pu [kN]"], marker="+", s=42, label="Pu-Muy demand")
    ax.axhline(0.0, linewidth=0.8, alpha=0.45)
    ax.axvline(0.0, linewidth=0.8, alpha=0.45)
    ax.grid(True, alpha=0.25)
    ax.set_title("Uniaxial φPMM Design Strength Curves")
    ax.set_xlabel("φMn [kN-m]")
    ax.set_ylabel("φPn / Pu [kN]")
    ax.legend(fontsize=7)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _docx_pmm_slice_image(pmm_df, demand_df, summary):
    """Create the governing constant-Pu Mx-My PMM slice for the DOCX report."""
    if pmm_df is None or len(pmm_df) == 0 or demand_df is None or len(demand_df) == 0:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return None
    try:
        gov_case = str(summary.get("governing_case", ""))
        row_df = demand_df[demand_df["Load Case"].astype(str) == gov_case] if "Load Case" in demand_df.columns else pd.DataFrame()
        row = row_df.iloc[0] if not row_df.empty else demand_df.sort_values("Overall Util.", ascending=False).iloc[0]
        pu = float(row.get("Max Pu [kN]", row.get("Pu [kN]", 0.0)))
        mx = float(row.get("PMM Mux [kN-m]", row.get("Max |Mux| [kN-m]", 0.0)))
        my = float(row.get("PMM Muy [kN-m]", row.get("Max |Muy| [kN-m]", 0.0)))
        sl = pmm_slice_at_p(pmm_df, pu)
        if sl is None or len(sl) == 0:
            return None
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(5.6, 5.2), dpi=160)
    ax.plot(sl["phiMnx [kN-m]"], sl["phiMny [kN-m]"], linewidth=2.0, label="φPMM design slice")
    ax.fill(sl["phiMnx [kN-m]"], sl["phiMny [kN-m]"], alpha=0.10)
    ax.plot([0.0, mx], [0.0, my], linewidth=1.6, label="demand vector")
    ax.scatter([mx], [my], marker="x", s=70, label=str(row.get("Load Case", "demand")))
    ax.axhline(0.0, linewidth=0.8, alpha=0.45)
    ax.axvline(0.0, linewidth=0.8, alpha=0.45)
    ax.grid(True, alpha=0.25)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title(f"Governing φPMM Slice at Pu = {pu:,.0f} kN")
    ax.set_xlabel("φMnx [kN-m]")
    ax.set_ylabel("φMny [kN-m]")
    ax.legend(fontsize=7)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _docx_pmm_3d_image(pmm_df, demand_df, summary):
    """Create a static 3D PMM surface figure for the DOCX report."""
    if pmm_df is None or len(pmm_df) == 0:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except ModuleNotFoundError:
        return None
    try:
        grid = pmm_polar_surface_grid(pmm_df, n_levels=18, n_angles=49)
        if grid is None:
            return None
        sx, sy, sz = grid
    except Exception:
        return None
    fig = plt.figure(figsize=(6.8, 5.2), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    try:
        ax.plot_surface(sx, sy, sz, alpha=0.33, linewidth=0.2, antialiased=True)
    except Exception:
        return None
    if demand_df is not None and len(demand_df) > 0:
        xcol = "PMM Mux [kN-m]" if "PMM Mux [kN-m]" in demand_df.columns else "Max |Mux| [kN-m]"
        ycol = "PMM Muy [kN-m]" if "PMM Muy [kN-m]" in demand_df.columns else "Max |Muy| [kN-m]"
        zcol = "Max Pu [kN]" if "Max Pu [kN]" in demand_df.columns else None
        if xcol in demand_df.columns and ycol in demand_df.columns and zcol in demand_df.columns:
            ax.scatter(demand_df[xcol], demand_df[ycol], demand_df[zcol], s=24, marker="o", label="load points")
            try:
                gov_case = str(summary.get("governing_case", ""))
                row_df = demand_df[demand_df["Load Case"].astype(str) == gov_case]
                if not row_df.empty:
                    r = row_df.iloc[0]
                    ax.scatter([r[xcol]], [r[ycol]], [r[zcol]], s=58, marker="x", label="governing")
            except Exception:
                pass
    ax.set_title("3D φPMM Design Strength Surface")
    ax.set_xlabel("φMnx [kN-m]")
    ax.set_ylabel("φMny [kN-m]")
    ax.set_zlabel("φPn / Pu [kN]")
    ax.view_init(elev=22, azim=38)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _docx_add_picture_or_note(doc, image_buf, width_cm=15.0, fallback="Figure could not be generated from the latest calculation state."):
    """Insert a DOCX picture if available, otherwise insert a clear note."""
    if image_buf:
        try:
            from docx.shared import Cm
            doc.add_picture(image_buf, width=Cm(width_cm))
            return True
        except Exception:
            pass
    doc.add_paragraph(fallback)
    return False


def build_pile_design_word_report(report):
    """Build a professional Word DOCX report for the latest pile-design run."""
    try:
        from docx import Document
        from docx.shared import Cm, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.section import WD_SECTION
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing Word export dependency: python-docx. Install project requirements first.") from exc

    if not report:
        raise RuntimeError("No pile design report is available. Run pile design first.")

    meta = report.get("meta", {})
    inputs = report.get("inputs", {})
    summary = report.get("summary", {})
    project = report.get("project", {})
    load_cases = report.get("load_cases", pd.DataFrame())
    demand_df = report.get("demand_df", pd.DataFrame())
    profile_df = report.get("profile_df", pd.DataFrame())
    sensitivity_df = report.get("sensitivity_df", pd.DataFrame())
    qa_checklist = report.get("qa_checklist", build_pile_design_qa_checklist(report))
    bar_df = report.get("bar_df", pd.DataFrame())
    pmm_df = report.get("pmm_df", pd.DataFrame())
    mx_curve = report.get("mx_curve", pd.DataFrame())
    my_curve = report.get("my_curve", pd.DataFrame())
    shear_summary = report.get("shear_summary", {})

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9)
    for style_name, size, color in [
        ("Title", 18, RGBColor(0x1A, 0x4F, 0x8A)),
        ("Heading 1", 13, RGBColor(0x1A, 0x4F, 0x8A)),
        ("Heading 2", 10.5, RGBColor(0x1A, 0x4F, 0x8A)),
    ]:
        style = doc.styles[style_name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color

    # Footer
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("Pile Soil Spring Design Report | Preliminary Engineering Review")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    title = doc.add_paragraph()
    title.style = doc.styles["Title"]
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("Pile Lateral Soil Spring Design Report")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run("Winkler Soil Spring Response | Pile Section Check | QA Traceability").italic = True

    _docx_add_kv_table(doc, "1. Project Information", [
        ("Project No.", project.get("project_no", "-")),
        ("Project Title", project.get("project_title", "-")),
        ("Structure / Location", project.get("structure_name", "-")),
        ("Designer", project.get("designer", "-")),
        ("Checker", project.get("checker", "-")),
        ("Revision", project.get("revision", "-")),
        ("Generated", meta.get("timestamp", "-")),
        ("App Version", meta.get("app_version", "-")),
        ("Load-case source", meta.get("load_case_source", "Manual / in-app table")),
        ("Calculation notes", project.get("project_notes", "-")),
    ])

    _docx_add_kv_table(doc, "2. Design Basis and Assumptions", [
        ("kh method", inputs.get("kh_method", "-")),
        ("Design stage", inputs.get("design_stage", "-")),
        ("Spring source", inputs.get("spring_source", "-")),
        ("Pile-head condition", inputs.get("head_condition", "-")),
        ("Ktheta head [kN-m/rad]", inputs.get("ktheta_head", 0.0)),
        ("Design demand basis", inputs.get("design_demand_basis", summary.get("design_demand_basis", "-"))),
        ("Water table [m]", inputs.get("water_table", 0.0)),
        ("Scour depth [m]", inputs.get("scour_depth", 0.0)),
    ])
    doc.add_paragraph("Fixed Head solves the head reaction moment internally. Do not double-count external pile-head moments from another model.")

    _docx_add_kv_table(doc, "3. Pile Geometry and Reinforcement", [
        ("Pile type", inputs.get("pile_type", "-")),
        ("Pile D [m]", inputs.get("D", 0.0)),
        ("Pile B [m]", inputs.get("B", 0.0)),
        ("Pile H [m]", inputs.get("H", 0.0)),
        ("Pile length L [m]", inputs.get("L", 0.0)),
        ("Concrete fc [MPa]", inputs.get("fc", 0.0)),
        ("Clear cover [mm]", inputs.get("cover_mm", 0.0)),
        ("Main reinforcement", f"{len(bar_df) if bar_df is not None else 0}-{inputs.get('main_bar', '-')}") ,
        ("Provided As [mm2]", summary.get("as_provided_mm2", 0.0)),
        ("Tie / spiral bar", inputs.get("tie_bar", "-")),
        ("Tie spacing [mm]", inputs.get("tie_spacing_mm", 0.0)),
        ("Transverse system", inputs.get("transverse_system", "-")),
    ])
    doc.add_paragraph("Pile section and longitudinal reinforcement layout used for the PMM section-capacity check:")
    _docx_add_picture_or_note(
        doc,
        _docx_section_rebar_image(inputs, bar_df),
        width_cm=10.5,
        fallback="Pile section reinforcement figure could not be generated. Review in-app section preview."
    )

    as_req_total = float(shear_summary.get("as_req_total_mm2", 0.0)) if isinstance(shear_summary, dict) else 0.0
    as_prov = float(summary.get("as_provided_mm2", 0.0))
    main_ok = bool(shear_summary.get("main_ok", as_prov >= as_req_total)) if isinstance(shear_summary, dict) else (as_prov >= as_req_total)
    tie_ok = bool(summary.get("provided_tie_spacing_ok", True))
    _docx_add_kv_table(doc, "4. Pile Reinforcement Design Summary", [
        ("Main reinforcement provided", f"{len(bar_df) if bar_df is not None else 0}-{inputs.get('main_bar', '-')}") ,
        ("As,min / preliminary required [mm2]", as_req_total),
        ("As provided [mm2]", as_prov),
        ("Longitudinal steel status", "OK" if main_ok else "NG"),
        ("Tie / spiral provided", f"{inputs.get('tie_bar', '-')} @ {float(inputs.get('tie_spacing_mm', 0.0)):,.0f} mm"),
        ("Recommended tie spacing [mm]", summary.get("recommended_tie_spacing_mm", 0.0)),
        ("Tie spacing status", "OK" if tie_ok else "NG"),
        ("Effective depth d [mm]", shear_summary.get("d_eff_mm", 0.0) if isinstance(shear_summary, dict) else 0.0),
        ("Vc preliminary [kN]", (float(shear_summary.get("vc_n", 0.0)) / 1000.0) if isinstance(shear_summary, dict) else 0.0),
        ("Shear / tie note", shear_summary.get("shear_status", "-") if isinstance(shear_summary, dict) else "-"),
    ])

    _docx_add_dataframe(doc, "5. Load Cases Used", load_cases, max_rows=25, max_cols=6)

    _docx_add_kv_table(doc, "6. Governing Design Summary", [
        ("Governing load case", summary.get("governing_case", "-")),
        ("Max Pu [kN]", summary.get("overall_pu_max", 0.0)),
        ("Min Pu [kN]", summary.get("overall_pu_min", 0.0)),
        ("Max |Mux| [kN-m]", summary.get("overall_mx", 0.0)),
        ("Max |Muy| [kN-m]", summary.get("overall_my", 0.0)),
        ("Max |V| [kN]", summary.get("overall_v", 0.0)),
        ("Shear/tie demand source", summary.get("shear_design_case", "-")),
        ("Shear/tie design Pu [kN]", summary.get("shear_design_pu_kN", 0.0)),
        ("Shear/tie design V [kN]", summary.get("shear_design_v_kN", 0.0)),
        ("Shear/tie design M [kN-m]", summary.get("shear_design_m_kN_m", 0.0)),
        ("PMM utilization", summary.get("max_pmm_util", 0.0)),
        ("Tension utilization", summary.get("max_tension_util", 0.0)),
        ("Overall utilization", summary.get("max_util", 0.0)),
        ("Overall status", summary.get("overall_status", "-")),
    ])

    _docx_add_dataframe(doc, "7. Load Case Result Table", demand_df, max_rows=30, max_cols=12)

    _docx_add_kv_table(doc, "8. PMM Section Capacity Check", [
        ("PMM method", "Preliminary ACI-style strain-compatible φPMM surface"),
        ("Governing load case", summary.get("governing_case", "-")),
        ("PMM utilization", summary.get("max_pmm_util", 0.0)),
        ("Tension utilization", summary.get("max_tension_util", 0.0)),
        ("Overall utilization", summary.get("max_util", 0.0)),
        ("PMM status", "OK" if float(summary.get("max_pmm_util", 999.0)) <= 1.0 else "NG"),
        ("Overall section status", summary.get("overall_status", "-")),
        ("Pure steel tension capacity φTn [kN]", summary.get("phi_tn_kN", 0.0)),
    ])
    doc.add_paragraph(
        "The PMM figures below show the section design-strength surface and demand points from the latest pile design run. "
        "They are review figures only; final detailing, anchorage, confinement, and geotechnical uplift capacity must be checked separately."
    )

    doc.add_heading("9. PMM Figures — Section Capacity", level=2)
    _docx_add_picture_or_note(
        doc,
        _docx_pmm_uniaxial_image(mx_curve, my_curve, demand_df),
        width_cm=15.0,
        fallback="Uniaxial PMM figure could not be generated. Review in-app PMM interaction diagrams."
    )
    _docx_add_picture_or_note(
        doc,
        _docx_pmm_slice_image(pmm_df, demand_df, summary),
        width_cm=13.5,
        fallback="Governing PMM slice figure could not be generated. Review in-app PMM slice diagram."
    )
    _docx_add_picture_or_note(
        doc,
        _docx_pmm_3d_image(pmm_df, demand_df, summary),
        width_cm=15.0,
        fallback="3D PMM surface figure could not be generated. Review in-app 3D PMM figure."
    )

    doc.add_heading("10. Force Diagrams Along Pile", level=2)
    gov_label = None
    if demand_df is not None and len(demand_df) > 0:
        gov_lc = str(summary.get("governing_case", ""))
        if "Load Case" in demand_df.columns and "Case Plot Label" in demand_df.columns:
            m = demand_df[demand_df["Load Case"].astype(str) == gov_lc]
            if not m.empty:
                gov_label = str(m["Case Plot Label"].iloc[0])
    force_img = _docx_profile_plot_image(
        profile_df, gov_label,
        ["Pu [kN]", "Mux [kN-m]", "Muy [kN-m]", "V resultant [kN]"],
        "Force Diagrams Along Pile"
    )
    if force_img:
        doc.add_picture(force_img, width=Cm(15.5))
    else:
        doc.add_paragraph("Force diagram image could not be generated. See QA workbook Force_Profile sheet.")

    doc.add_heading("11. Displacement Diagrams Along Pile", level=2)
    disp_img = _docx_profile_plot_image(
        profile_df, gov_label,
        ["Disp X [mm]", "Disp Y [mm]", "Disp resultant [mm]"],
        "Displacement Diagrams Along Pile"
    )
    if disp_img:
        doc.add_picture(disp_img, width=Cm(15.5))
    else:
        doc.add_paragraph("Displacement diagram image could not be generated. See QA workbook Force_Profile sheet.")

    _docx_add_dataframe(doc, "12. Head Boundary Sensitivity", sensitivity_df, max_rows=25, max_cols=10)
    _docx_add_dataframe(doc, "13. QA Checklist", qa_checklist, max_rows=30, max_cols=4)
    _docx_add_dataframe(doc, "14. Final Report Review / Punch List", final_review, max_rows=40, max_cols=5)

    _docx_add_kv_table(doc, "15. Design Conclusion", [
        ("Governing case", summary.get("governing_case", "-")),
        ("Structural PMM status", "OK" if float(summary.get("max_pmm_util", 999.0)) <= 1.0 else "NG"),
        ("Tie spacing status", "OK" if bool(summary.get("provided_tie_spacing_ok", False)) else "NG"),
        ("Overall status", summary.get("overall_status", "-")),
        ("Action if NG", "Revise reinforcement / section / load path and re-run checks." if str(summary.get("overall_status", "-")).upper() != "OK" else "Proceed to independent design review and geotechnical verification."),
    ])

    doc.add_heading("16. Limitations / QA Notes", level=2)
    notes = [
        "This report is generated from the latest in-app calculation state. Re-run pile design after changing input data.",
        "Pile structural design is preliminary and must be reviewed against the governing project code, detailing, anchorage, constructability, geotechnical axial capacity, and uplift requirements.",
        "Soil spring stiffness is only as reliable as the input soil profile and selected kh method.",
        "Case-by-case design basis is recommended. Non-concurrent envelope demand may combine maxima from different load cases and should be treated as a screening check.",
        "For final work, keep this report with the exported spring workbook and the source pile-cap STM transfer file.",
    ]
    for note in notes:
        doc.add_paragraph(note, style="List Bullet")

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# V.1 Verification / benchmark test cases
# These tests are intentionally independent from Streamlit widgets. They provide
# regression checks for the lateral-response solver and head-boundary behavior.
# They do not replace external validation against LPILE/FEA; they protect the
# app against accidental internal changes in future milestones.
# ─────────────────────────────────────────────────────────────────────────────

VERIFICATION_BENCHMARKS = [
    {
        "Case ID": "V1-FREE-ROUND",
        "Description": "Round pile, uniform soil, free head",
        "Pile Type": "Round", "D": 1.0, "B": 1.0, "Hsec": 1.0, "fc": 35.0,
        "L": 20.0, "dL": 1.0, "kh": 15000.0, "Hload": 100.0,
        "Axis": "X", "Head Condition": "Free Head / Shear Only", "Ktheta": 0.0,
        "Expected": {
            "Head displacement [mm]": 3.001988,
            "Head rotation [rad]": -0.000681,
            "Head restraint moment [kN-m]": 0.0,
            "Max displacement [mm]": 3.001988,
            "Max moment [kN-m]": 136.900437,
            "z @ max moment [m]": 3.0,
            "Max shear [kN]": 77.485092,
            "Reaction balance error [kN]": 0.0,
        },
    },
    {
        "Case ID": "V2-FIXED-ROUND",
        "Description": "Round pile, uniform soil, fixed head",
        "Pile Type": "Round", "D": 1.0, "B": 1.0, "Hsec": 1.0, "fc": 35.0,
        "L": 20.0, "dL": 1.0, "kh": 15000.0, "Hload": 100.0,
        "Axis": "X", "Head Condition": "Fixed Head (theta = 0)", "Ktheta": 0.0,
        "Expected": {
            "Head displacement [mm]": 1.526525,
            "Head rotation [rad]": 0.0,
            "Head restraint moment [kN-m]": 216.503099,
            "Max displacement [mm]": 1.526525,
            "Max moment [kN-m]": 478.646105,
            "z @ max moment [m]": 7.0,
            "Max shear [kN]": 88.551062,
            "Reaction balance error [kN]": 0.0,
        },
    },
    {
        "Case ID": "V3-KTHETA-MED",
        "Description": "Round pile, uniform soil, rotational spring Ktheta = 100,000",
        "Pile Type": "Round", "D": 1.0, "B": 1.0, "Hsec": 1.0, "fc": 35.0,
        "L": 20.0, "dL": 1.0, "kh": 15000.0, "Hload": 100.0,
        "Axis": "X", "Head Condition": "Rotational Spring", "Ktheta": 100000.0,
        "Expected": {
            "Head displacement [mm]": 2.648742,
            "Head rotation [rad]": -0.000518,
            "Head restraint moment [kN-m]": 51.833763,
            "Max displacement [mm]": 2.648742,
            "Max moment [kN-m]": 211.307090,
            "z @ max moment [m]": 4.0,
            "Max shear [kN]": 80.134435,
            "Reaction balance error [kN]": 0.0,
        },
    },
    {
        "Case ID": "V4-STM-LIKE",
        "Description": "Round pile, STM-like imported head shear, fixed head",
        "Pile Type": "Round", "D": 1.0, "B": 1.0, "Hsec": 1.0, "fc": 35.0,
        "L": 25.0, "dL": 1.0, "kh": 20000.0, "Hload": 60.0,
        "Axis": "X", "Head Condition": "Fixed Head (theta = 0)", "Ktheta": 0.0,
        "Expected": {
            "Head displacement [mm]": 0.738056,
            "Head rotation [rad]": 0.0,
            "Head restraint moment [kN-m]": 120.702227,
            "Max displacement [mm]": 0.738056,
            "Max moment [kN-m]": 266.809241,
            "z @ max moment [m]": 6.0,
            "Max shear [kN]": 52.619442,
            "Reaction balance error [kN]": 0.0,
        },
    },
    {
        "Case ID": "V5-RECT-X",
        "Description": "Rectangular pile, X-load direction, high rotational restraint",
        "Pile Type": "Square", "D": 0.8, "B": 0.6, "Hsec": 0.8, "fc": 35.0,
        "L": 18.0, "dL": 1.0, "kh": 18000.0, "Hload": 80.0,
        "Axis": "X", "Head Condition": "Rotational Spring", "Ktheta": 1000000.0,
        "Expected": {
            "Head displacement [mm]": 2.334803,
            "Head rotation [rad]": -0.000123,
            "Head restraint moment [kN-m]": 123.158518,
            "Max displacement [mm]": 2.334803,
            "Max moment [kN-m]": 278.918251,
            "z @ max moment [m]": 5.0,
            "Max shear [kN]": 67.392066,
            "Reaction balance error [kN]": 0.0,
        },
    },
]


def run_verification_case(case, tolerance_pct=1.0):
    """Run one benchmark case and return a metric-by-metric comparison table."""
    L = float(case["L"])
    dL = float(case["dL"])
    depths = np.arange(0.0, L + 1e-9, dL)
    pile_type_for_props = "Round" if case["Pile Type"] == "Round" else "Square"
    Ap_v, Ipx_v, Ipy_v, Ep_v, Deq_x_v, Deq_y_v = calc_pile_props(
        pile_type_for_props,
        float(case["D"]),
        float(case.get("B", case["D"])),
        float(case.get("Hsec", case["D"])),
        float(case["fc"]),
    )
    if str(case.get("Axis", "X")).upper() == "X":
        Ip = Ipy_v
        Deq = Deq_x_v
    else:
        Ip = Ipx_v
        Deq = Deq_y_v
    spring_k = float(case["kh"]) * Deq * calc_tributary_lengths(depths, L)
    y, theta, reactions, shear, moment, head_restraint = solve_pile_lateral_response(
        depths,
        spring_k,
        Ep_v * Ip,
        head_shear=float(case["Hload"]),
        head_moment=0.0,
        head_condition=case["Head Condition"],
        rotational_stiffness=float(case.get("Ktheta", 0.0)),
    )
    i_m = int(np.argmax(np.abs(moment))) if len(moment) else 0
    actual = {
        "Head displacement [mm]": float(y[0] * 1000.0),
        "Head rotation [rad]": float(theta[0]),
        "Head restraint moment [kN-m]": float(head_restraint),
        "Max displacement [mm]": float(np.max(np.abs(y)) * 1000.0),
        "Max moment [kN-m]": float(np.max(np.abs(moment))),
        "z @ max moment [m]": float(depths[i_m]),
        "Max shear [kN]": float(np.max(np.abs(shear))),
        "Reaction balance error [kN]": float(float(case["Hload"]) - np.sum(reactions)),
    }
    rows = []
    expected = case.get("Expected", {})
    for metric, exp_val in expected.items():
        act_val = float(actual.get(metric, np.nan))
        exp_val = float(exp_val)
        # Depth index and zero-balance checks need a small absolute tolerance;
        # response quantities use the relative tolerance selected by the user.
        if metric.startswith("z @"):
            tol = 0.001
        elif abs(exp_val) <= 1e-9:
            tol = 1e-5
        else:
            tol = max(1e-5, abs(exp_val) * float(tolerance_pct) / 100.0)
        diff = act_val - exp_val
        status = "OK" if abs(diff) <= tol else "NG"
        rows.append({
            "Case ID": case["Case ID"],
            "Description": case["Description"],
            "Metric": metric,
            "Actual": act_val,
            "Expected baseline": exp_val,
            "Difference": diff,
            "Tolerance": tol,
            "Status": status,
        })
    return pd.DataFrame(rows)


def run_verification_suite(tolerance_pct=1.0):
    """Run all benchmark cases and return summary and detail tables."""
    detail_frames = [run_verification_case(case, tolerance_pct) for case in VERIFICATION_BENCHMARKS]
    detail_df = pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame()
    if detail_df.empty:
        return pd.DataFrame(), detail_df
    summary = []
    for case_id, grp in detail_df.groupby("Case ID", sort=False):
        n_total = int(len(grp))
        n_ok = int((grp["Status"] == "OK").sum())
        max_abs_diff = float(grp["Difference"].abs().max())
        status = "OK" if n_ok == n_total else "NG"
        desc = str(grp["Description"].iloc[0])
        summary.append({
            "Case ID": case_id,
            "Description": desc,
            "Checks OK": n_ok,
            "Checks Total": n_total,
            "Max |Difference|": max_abs_diff,
            "Status": status,
        })
    return pd.DataFrame(summary), detail_df


def verification_cases_dataframe():
    """Return benchmark case definitions without the embedded expected dictionary."""
    rows = []
    for case in VERIFICATION_BENCHMARKS:
        rows.append({
            "Case ID": case["Case ID"],
            "Description": case["Description"],
            "Pile Type": case["Pile Type"],
            "D [m]": case["D"],
            "B [m]": case.get("B", case["D"]),
            "H [m]": case.get("Hsec", case["D"]),
            "fc [MPa]": case["fc"],
            "L [m]": case["L"],
            "dL [m]": case["dL"],
            "uniform kh [kN/m3]": case["kh"],
            "Head shear [kN]": case["Hload"],
            "Axis": case["Axis"],
            "Head Condition": case["Head Condition"],
            "Ktheta [kN-m/rad]": case.get("Ktheta", 0.0),
        })
    return pd.DataFrame(rows)


def build_verification_markdown_report(summary_df, detail_df, tolerance_pct):
    """Build a compact markdown verification report."""
    lines = []
    lines.append("# Pile Soil Spring Verification Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"App version: {VERSION}")
    lines.append(f"Tolerance: ±{float(tolerance_pct):.2f}% for response quantities")
    lines.append("")
    overall = "OK" if len(summary_df) and (summary_df["Status"] == "OK").all() else "NG"
    lines.append(f"Overall verification status: **{overall}**")
    lines.append("")
    lines.append("## Benchmark Cases")
    lines.append(_df_to_markdown_table(verification_cases_dataframe(), max_rows=20))
    lines.append("")
    lines.append("## Summary")
    lines.append(_df_to_markdown_table(summary_df, max_rows=20))
    lines.append("")
    lines.append("## Detailed Metric Checks")
    lines.append(_df_to_markdown_table(detail_df, max_rows=120))
    lines.append("")
    lines.append("## QA Notes")
    lines.append("- These benchmarks are regression checks against the current internal solver implementation.")
    lines.append("- They are not independent external validation against LPILE, PLAXIS, SAP2000/CSI, or field load-test data.")
    lines.append("- If a future code change causes NG status, review whether the change is intentional engineering improvement or an unintended regression.")
    return "\n".join(lines)


def build_verification_workbook(summary_df, detail_df, tolerance_pct):
    """Build an Excel workbook for verification results."""
    try:
        import xlsxwriter  # noqa: F401
    except Exception as exc:
        raise RuntimeError("xlsxwriter is required to export verification workbook. Install it with: pip install xlsxwriter") from exc
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        fmt_title = wb.add_format({"bold": True, "font_size": 14, "font_color": "#1F4E79"})
        fmt_note = wb.add_format({"italic": True, "font_color": "#666666"})
        cases_df = verification_cases_dataframe()
        cases_df.to_excel(writer, sheet_name="Benchmark_Cases", index=False, startrow=3)
        ws = writer.sheets["Benchmark_Cases"]
        ws.write(0, 0, "Verification Benchmark Case Definitions", fmt_title)
        ws.write(1, 0, f"Tolerance: ±{float(tolerance_pct):.2f}% for response quantities", fmt_note)
        ws.set_column(0, len(cases_df.columns) - 1, 18)
        summary_df.to_excel(writer, sheet_name="Verification_Summary", index=False, startrow=3)
        ws = writer.sheets["Verification_Summary"]
        ws.write(0, 0, "Verification Summary", fmt_title)
        ws.set_column(0, len(summary_df.columns) - 1, 20)
        detail_df.to_excel(writer, sheet_name="Detailed_Metrics", index=False, startrow=3)
        ws = writer.sheets["Detailed_Metrics"]
        ws.write(0, 0, "Detailed Metric-by-Metric Checks", fmt_title)
        ws.set_column(0, len(detail_df.columns) - 1, 20)
    return buf.getvalue()

st.sidebar.title("Pile Spring Calculator")
st.sidebar.caption(f"version {VERSION}")

for _msg_key, _box in (("_just_loaded_msg", st.sidebar.success),
                      ("_just_profile_msg", st.sidebar.success)):
    if _msg_key in st.session_state and st.session_state[_msg_key]:
        _box(st.session_state.pop(_msg_key))

save_load_panel = st.sidebar.container()
st.sidebar.markdown("---")

st.sidebar.header("0. Project Metadata")
with st.sidebar.expander("Calculation header", expanded=False):
    project_no = st.text_input("Project No.", value="", key="project_no")
    project_title = st.text_input("Project Title", value="", key="project_title")
    structure_name = st.text_input("Structure / Location", value="", key="structure_name")
    pc1, pc2 = st.columns(2)
    designer = pc1.text_input("Designer", value="", key="designer")
    checker = pc2.text_input("Checker", value="", key="checker")
    revision = st.text_input("Revision", value="Rev. 0", key="revision")
    project_notes = st.text_area("Calculation Notes", value="", key="project_notes", height=90)
project_meta = {
    "project_no": project_no,
    "project_title": project_title,
    "structure_name": structure_name,
    "designer": designer,
    "checker": checker,
    "revision": revision,
    "project_notes": project_notes,
}

st.sidebar.header("1. Project Settings")
c1, c2 = st.sidebar.columns(2)
design_stage = c1.selectbox(
    "Design Stage", ["Normal", "Seismic"], key="stage",
    help="Normal uses standard stiffness. Seismic doubles E0."
)
method = c2.selectbox(
    "kh Method", ["JRA", "Terzaghi", "Vesic 1961", "Broms 1964"], key="method",
    help="Select the lateral subgrade modulus method. JRA is recommended for routine design."
)

_method_tips = {
    "JRA": ("Recommended primary method", "success",
            "Primary method for bridge/highway work. Uses N-SPT directly and is commonly used for preliminary design."),
    "Terzaghi": ("Conservative cross-check", "info",
                  "Often gives a conservative lower-bound kh. Useful for checking sensitivity against JRA."),
    "Vesic 1961": ("Requires reliable Es", "warning",
                    "Best used when a reliable soil modulus Es is available from lab/PMT data."),
    "Broms 1964": ("Capacity-oriented check", "error",
                    "Broms is based on ultimate lateral resistance and should not be treated as a direct elastic spring for final FEA design."),
}
_tip = _method_tips[method]
with st.sidebar.expander(_tip[0], expanded=True):
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[_tip[1]](_tip[2])

st.sidebar.header("2. Pile Properties")
pile_type = st.sidebar.selectbox("Pile Type", ["Round", "Square/Rectangular"], key="pile_type")
if pile_type == "Round":
    D = st.sidebar.number_input("Diameter D [m]", 0.1, 5.0, 0.6, 0.05, key="D",
                                help="Diameter of the round pile.")
    B = H = D
else:
    c3, c4 = st.sidebar.columns(2)
    B = c3.number_input("Width B [m]", 0.1, 5.0, 0.35, 0.05, key="B", help="Pile width parallel to the X axis.")
    H = c4.number_input("Height H [m]", 0.1, 5.0, 0.35, 0.05, key="H", help="Pile height parallel to the Y axis.")
    D = max(B, H)

L = st.sidebar.number_input("Pile Length L [m]", 1.0, 120.0, 25.0, 1.0, key="L",
                            help="Total pile length.")
fc = st.sidebar.number_input("Concrete f'c [MPa]", 15.0, 100.0, 28.0, 1.0, key="fc",
                             help="Specified compressive strength of concrete.")
node_spacing = st.sidebar.number_input("Node Spacing dL [m]", 0.25, 5.0, 1.0, 0.25, key="dl",
                                       help="Depth interval used to generate spring nodes.")

if method == "Vesic 1961":
    nu = st.sidebar.number_input("Poisson Ratio nu", 0.10, 0.50, 0.35, 0.05, key="nu")
else:
    nu = float(st.session_state.get("nu", 0.35))

st.sidebar.header("3. Site Conditions")
water_table = st.sidebar.number_input("Water Table Depth [m]", 0.0, float(L), 1.0, 0.5, key="wt",
                                      help="Depth to groundwater from ground surface. Use 0 for water at ground level.")
scour_depth = st.sidebar.number_input("Scour Depth [m]", 0.0, float(L), 0.0, 0.5, key="scour",
                                      help="Depth where soil support is removed; kh is set to zero above this level.")

st.sidebar.header("4. Group Effect")
use_group = st.sidebar.checkbox("Apply Group Effect (p-multiplier)", key="use_group",
                                help="Apply p-multiplier reduction for pile groups.")
if use_group:
    s_D = st.sidebar.number_input("Pile Spacing s/D", 2.0, 12.0, 3.0, 0.5, key="sD",
                                  help="Center-to-center pile spacing divided by pile diameter/equivalent width.")
    gc1, gc2 = st.sidebar.columns(2)
    nx = gc1.number_input("Piles in X", 1, 20, 3, 1, key="nx")
    ny = gc2.number_input("Piles in Y", 1, 20, 3, 1, key="ny")
    spring_output = st.sidebar.radio(
        "Spring Output",
        ["Global average spring", "Row-based spring table"],
        key="spring_output",
        help="Choose a global average spring table or a detailed row-based spring table."
    )
    n_total = int(nx * ny)

    def fm_row_list(n_piles, s_over_D):
        fms = []
        for i in range(n_piles):
            pos = group_row_position(i)
            fms.append(calc_pmultiplier(s_over_D, pos))
        return fms

    fms_x = fm_row_list(int(nx), s_D)
    fms_y = fm_row_list(int(ny), s_D)
    fm_vals = [min(fms_x[ix], fms_y[iy]) for iy in range(int(ny)) for ix in range(int(nx))]
    Pmult = sum(fm_vals) / n_total if n_total > 0 else 1.0

    if s_D >= 6.0:
        st.sidebar.success("s/D >= 6: fm = 1.00 (no group reduction).")
        Pmult = 1.0
        fms_x = [1.0] * int(nx)
        fms_y = [1.0] * int(ny)
    else:
        st.sidebar.info(
            f"**Average fm = {Pmult:.3f}** (used for the global average table)\n\n"
            f"nx={int(nx)}, ny={int(ny)}, n={n_total} piles\n\n"
            f"Global average uses `min(fm_x, fm_y)` at each pile before averaging.\n\n"
            f"Ref: FHWA-NHI-16-009 Section 9.4"
        )
        with st.sidebar.expander("fm breakdown per row"):
            st.caption("**X-direction rows** (loading toward X)")
            for i, fm in enumerate(fms_x):
                lbl = "Lead" if i == 0 else ("2nd" if i == 1 else "3rd+")
                st.write(f"Row {i+1} ({lbl}): fm = {fm:.3f}")
            st.caption("**Y-direction rows** (loading toward Y)")
            for i, fm in enumerate(fms_y):
                lbl = "Lead" if i == 0 else ("2nd" if i == 1 else "3rd+")
                st.write(f"Row {i+1} ({lbl}): fm = {fm:.3f}")
else:
    s_D = float(st.session_state.get("sD", 3.0))
    nx = int(st.session_state.get("nx", 3))
    ny = int(st.session_state.get("ny", 3))
    spring_output = "Global average spring"
    fms_x = [1.0]
    fms_y = [1.0]
    Pmult = 1.0
pile_is_round = (pile_type == "Round")
Ap, Ipx, Ipy, Ep, Deq_x, Deq_y = calc_pile_props("Round" if pile_is_round else "Square", D, B, H, fc)

#  TABS
st.title("Pile Lateral Soil Spring Stiffness Calculator")
st.caption("Units: kN, m  |  Methods: JRA / Terzaghi 1955 / Vesic 1961 / Broms 1964")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Input & Pile Section", "Results & Profile", "kh & Spring Plots",
    "Pile Design", "N-SPT Reference", "Formulas & References", "Report / QA",
    "Verification"
])

with tab1:
    left_col, right_col = st.columns([3, 2], gap="large")
    with right_col:
        st.subheader("Pile Cross-Section")
        st.plotly_chart(
            pile_section_figure("Round" if pile_is_round else "Square", D, B, H, Ap, Ipx, Ipy, Ep, compact=True),
            use_container_width=True
        )
        st.markdown("**Section Properties**")
        mc1, mc2 = st.columns(2)
        mc1.metric("Ap [m2]", f"{Ap:.4f}"); mc2.metric("Ep [MPa]", f"{Ep/1000:.0f}")
        mc3, mc4 = st.columns(2)
        mc3.metric("Ix [m4]", f"{Ipx:.5f}"); mc4.metric("Iy [m4]", f"{Ipy:.5f}")

        st.subheader("Pile Group Plan")
        st.plotly_chart(
            pile_group_plan_figure("Round" if pile_is_round else "Square", D, B, H, s_D, nx, ny, use_group),
            use_container_width=True
        )

    with left_col:
        st.subheader("Soil Layer Input")

        with st.expander("Predefined Soil Profiles", expanded=False):
            selected_profile = st.selectbox("Select profile:", list(SOIL_PROFILES.keys()), key="_profile_selector")
            st.dataframe(SOIL_PROFILES[selected_profile], use_container_width=True, hide_index=True)
            st.info("Predefined profiles are for preliminary comparison only. Replace them with project-specific borehole data for design.")
            if st.button("Use this profile", use_container_width=True, type="primary", key="_use_profile_btn"):
                st.session_state["_pending_profile"] = selected_profile
                st.rerun()

        clay_opts = list(SOIL_DB["Clay"].keys())
        sand_opts = list(SOIL_DB["Sand"].keys())
        all_cons = clay_opts + sand_opts

        _df_input = st.session_state.soil_layers.copy()
        for _col in ["Depth_From", "Depth_To", "SPT_N", "Es", "cu", "phi", "Gamma"]:
            if _col in _df_input.columns:
                _df_input[_col] = pd.to_numeric(_df_input[_col], errors="coerce").astype(float)
        # BUG FIX 2a: fill NaN in SPT_N so data_editor shows 0 instead of "None"
        if "SPT_N" in _df_input.columns:
            _df_input["SPT_N"] = _df_input["SPT_N"].fillna(0.0)

        edited_df = st.data_editor(
            _df_input,
            num_rows="dynamic",
            use_container_width=True,
            key="soil_editor",
            column_config={
                "Depth_From": st.column_config.NumberColumn("From [m]", format="%.2f", width="small"),
                "Depth_To": st.column_config.NumberColumn("To [m]", format="%.2f", width="small"),
                "Soil_Type": st.column_config.SelectboxColumn("Type", options=["Clay", "Sand"], width="small"),
                "Consistency": st.column_config.SelectboxColumn("Consist.", options=all_cons, width="medium"),
                "SPT_N": st.column_config.NumberColumn("N-SPT", format="%.0f", min_value=0.0, step=1.0, width="small", help="Edit N-SPT directly — phi/cu and Consistency update automatically"),
                "Es": st.column_config.NumberColumn("Es [kPa]", format="%.0f", width="small"),
                "cu": st.column_config.NumberColumn("cu [kPa]", format="%.1f", width="small"),
                "phi": st.column_config.NumberColumn("phi [deg]", format="%.1f", width="small"),
                "Gamma": st.column_config.NumberColumn("gamma [kN/m3]", format="%.1f", width="small"),
            }
        )

        prev_tc = st.session_state.get("_prev_type_cons", {})
        prev_N  = st.session_state.get("_prev_N", {})
        new_tc  = {}
        new_N   = {}
        autofilled = edited_df.copy()
        did_fill = False
        fill_reason = ""

        for idx, row in edited_df.iterrows():
            stype   = str(row.get("Soil_Type", "") or "")
            cons    = str(row.get("Consistency", "") or "")
            _raw_N  = row.get("SPT_N", 0)
            curr_N  = float(_raw_N) if (_raw_N is not None and str(_raw_N) not in ("", "nan", "None")) else 0.0
            new_tc[idx] = (stype, cons)
            new_N[idx]  = curr_N

            type_cons_changed = (stype and cons and stype in SOIL_DB
                                 and cons in SOIL_DB.get(stype, {})
                                 and prev_tc.get(idx) != (stype, cons))
            n_changed = (idx in prev_N
                         and abs(curr_N - prev_N[idx]) > 0.49
                         and not type_cons_changed
                         and stype in ("Clay", "Sand")
                         and curr_N > 0)

            if type_cons_changed:
                # Consistency เปลี่ยน → autofill N + interpolate phi/cu
                filled_row, ok = autofill_soil_row(row.to_dict())
                if ok:
                    autofilled.loc[idx] = pd.Series(filled_row)
                    new_N[idx] = filled_row["SPT_N"]
                    did_fill = True
                    fill_reason = "Soil parameters auto-filled from SOIL_DB."
            elif n_changed:
                # N-SPT เปลี่ยน → interpolate phi/cu + update Consistency label
                filled_row, ok = autofill_from_N_change(row.to_dict())
                if ok:
                    autofilled.loc[idx] = pd.Series(filled_row)
                    # CRITICAL FIX: update new_tc with the NEW Consistency label
                    # so next render does NOT see it as type_cons_changed and
                    # re-trigger a full SOIL_DB autofill that would reset N
                    new_tc[idx] = (stype, str(filled_row.get("Consistency", cons)))
                    did_fill = True
                    fill_reason = f"phi/cu interpolated from N-SPT = {curr_N:.0f} (Table 6.3.2-1)."

        st.session_state["_prev_type_cons"] = new_tc
        st.session_state["_prev_N"] = new_N

        if did_fill:
            st.session_state.soil_layers = autofilled
            for w in ("soil_editor", "_soil_edited"):
                if w in st.session_state:
                    del st.session_state[w]
            st.toast(fill_reason)
            st.rerun()
        else:
            st.session_state["_soil_edited"] = edited_df

        _msgs = validate_soil_profile(edited_df)
        if _msgs:
            with st.expander(f"Soil profile warnings ({len(_msgs)})", expanded=False):
                for m in _msgs:
                    st.write(m)
df_soil = st.session_state.get("_soil_edited", st.session_state.soil_layers)

with save_load_panel:
    st.header("Save / Load Design")
    project_data = save_project_to_dict(
        design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
        water_table, scour_depth, use_group, s_D, nx, ny, spring_output,
        df_soil, VERSION, project_meta=project_meta
    )
    json_str = json.dumps(project_data, indent=2, ensure_ascii=True)
    st.download_button(
        "Save Project",
        data=json_str,
        file_name=f"PileProject_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        use_container_width=True
    )

    uploaded_file = st.file_uploader(
        "Open project JSON",
        type=["json"],
        help="Select a saved .json project file.",
        key="_project_uploader",
    )

    # Use the pending-load pattern to avoid Streamlit widget-state errors.
    if uploaded_file is not None:
        file_id = getattr(uploaded_file, "file_id", uploaded_file.name + str(uploaded_file.size))
        last_id = st.session_state.get("_last_loaded_file_id")
        if last_id != file_id:
            try:
                loaded_data = json.load(uploaded_file)
                updates = load_project_from_dict(loaded_data)
                updates["__msg__"] = (
                    f"Project loaded successfully. "
                    f"Saved at: {loaded_data.get('saved_timestamp', 'N/A')[:19]}"
                )
                st.session_state["_pending_load"] = updates
                st.session_state["_last_loaded_file_id"] = file_id
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON file: {e}")
            except Exception as e:
                st.error(f"Could not load project file: {e}")

_REQUIRED_COLS = {
    "Depth_From": "Depth_From",
    "Depth_To": "Depth_To",
    "Soil_Type": "Soil_Type",
    "SPT_N": "SPT_N",
}
_ready = True

_df_check = df_soil.dropna(how="all").copy()

if len(_df_check) == 0:
    st.warning("Please enter at least one soil layer before running the calculation.")
    _ready = False
else:
    _incomplete = []
    for _enum_i, (_i, _row) in enumerate(_df_check.iterrows(), start=1):
        _missing = []
        for _col, _label in _REQUIRED_COLS.items():
            _v = _row.get(_col, None)
            if _v is None or (isinstance(_v, float) and np.isnan(_v)) or str(_v).strip() in ("", "None"):
                _missing.append(_label)
        if _missing:
            _row_no = _enum_i
            _depth_label = f"From {_row.get('Depth_From','?')} m" if not pd.isna(_row.get("Depth_From")) else f"Row {_row_no}"
            _incomplete.append(f"- **{_depth_label}** missing: {', '.join(_missing)}")

    if _incomplete:
        st.warning(
            "**Soil layer data is incomplete.** Please fill the missing values before calculation:\n\n"
            + "\n".join(_incomplete)
        )
        _ready = False

    if _ready:
        _df_valid = _df_check.dropna(subset=["Depth_From", "Depth_To"])
        _max_depth = _df_valid["Depth_To"].max() if len(_df_valid) > 0 else 0
        if L > _max_depth + 1e-3:
            st.warning(
                f"Pile length L = {L:.1f} m is deeper than the entered soil profile ({_max_depth:.1f} m). "
                f"The deepest entered soil layer will be used below the profile depth."
            )
depths  = np.arange(0, L + 1e-9, node_spacing)
if len(depths) == 0 or abs(depths[-1] - L) > 1e-6:
    depths = np.append(depths, L)
tributary_lengths = calc_tributary_lengths(depths, L)
results = []

_req_draw = ["Depth_From", "Depth_To", "Soil_Type", "SPT_N"]
df_soil_draw = df_soil.dropna(subset=_req_draw).copy()
df_soil_draw = df_soil_draw[
    df_soil_draw["Soil_Type"].astype(str).str.strip().isin(["Clay", "Sand"])
].reset_index(drop=True)

if not _ready:
    df_results = pd.DataFrame()
    df_row_results = pd.DataFrame()
    N_tip = 0.0; Kv_tip = 0.0; kv_tip = 0.0
    D_tip_eq = D if pile_is_round else equivalent_circular_diameter_from_area(Ap)
    beta = beta_x = beta_y = 0.0
    kh_avg = kh_avg_x = kh_avg_y = 0.0
    kh_max_surface = kh_min_deep = as_ratio_rec = As_min = 0.0
else:
    _req = ["Depth_From", "Depth_To", "Soil_Type", "SPT_N"]
    df_soil_calc = df_soil.dropna(subset=_req).copy()
    df_soil_calc = df_soil_calc[
        df_soil_calc["Soil_Type"].astype(str).str.strip().isin(["Clay", "Sand"])
    ].reset_index(drop=True)

    row_results = []
    for node_no, (z, trib_len) in enumerate(zip(depths, tributary_lengths)):
        mask  = (df_soil_calc["Depth_From"] <= z) & (df_soil_calc["Depth_To"] > z)
        layer = df_soil_calc[mask].iloc[0] if mask.any() else df_soil_calc.iloc[-1]

        soil_type   = layer["Soil_Type"]
        N_val       = float(layer["SPT_N"])
        below_water = z > water_table
        z_mid       = max(z, 0.05)

        if z <= scour_depth:
            kh_x = kh_y = E0 = 0.0
            pu = np.nan
        else:
            pu = np.nan
            if method == "JRA":
                kh_x, E0 = calc_kh_jra(N_val, Deq_x, design_stage, soil_type, below_water)
                kh_y, _  = calc_kh_jra(N_val, Deq_y, design_stage, soil_type, below_water)
            elif method == "Terzaghi":
                cu_val = layer.get("cu", None) if soil_type == "Clay" else None
                kh_x = calc_kh_terzaghi(N_val, soil_type, Deq_x, z_mid, below_water, cu_val)
                kh_y = calc_kh_terzaghi(N_val, soil_type, Deq_y, z_mid, below_water, cu_val)
                E0 = 2800 * N_val
            elif method == "Vesic 1961":
                Es_kPa = float(layer.get("Es", 20000))
                if soil_type == "Sand" and below_water:
                    Es_kPa *= 0.6
                kh_x = calc_kh_vesic(Es_kPa, Deq_x, Ep, Ipy, nu)
                kh_y = calc_kh_vesic(Es_kPa, Deq_y, Ep, Ipx, nu)
                E0 = Es_kPa
            else:  # Broms
                gamma_v = float(layer.get("Gamma", 18))
                gamma_eff = gamma_v - 10 if below_water else gamma_v
                cu  = float(layer.get("cu",  6.25*N_val)) if soil_type == "Clay" else None
                phi = float(layer.get("phi", 28)) if soil_type == "Sand" else None
                kh_x, pu = calc_kh_broms(soil_type, N_val, z, Deq_x, gamma_eff, phi, cu)
                kh_y, _  = calc_kh_broms(soil_type, N_val, z, Deq_y, gamma_eff, phi, cu)
                E0 = float(layer.get("Es", 20000))

        Ksx = kh_x * Deq_x * trib_len * Pmult
        Ksy = kh_y * Deq_y * trib_len * Pmult

        results.append({
            "Node":         node_no,
            "Depth [m]":    round(z, 3),
            "Trib. L [m]":  round(trib_len, 3),
            "Soil_Type":    soil_type,
            "N-SPT":        N_val,
            "kh_x [kN/m3]": round(kh_x, 1),
            "kh_y [kN/m3]": round(kh_y, 1),
            "Ksx [kN/m]":   round(Ksx, 1),
            "Ksy [kN/m]":   round(Ksy, 1),
            "pu [kN/m]":    round(pu, 1) if not np.isnan(pu) else np.nan,
        })

        if use_group:
            for row_idx, fm in enumerate(fms_x):
                row_results.append({
                    "Node":         node_no,
                    "Depth [m]":    round(z, 3),
                    "Trib. L [m]":  round(trib_len, 3),
                    "Direction":    "X",
                    "Row No.":      row_idx + 1,
                    "Row Position": group_row_position(row_idx),
                    "fm":           round(float(fm), 3),
                    "Soil_Type":    soil_type,
                    "N-SPT":        N_val,
                    "kh [kN/m3]":   round(kh_x, 1),
                    "Deq [m]":      round(Deq_x, 3),
                    "Kspring [kN/m]": round(kh_x * Deq_x * trib_len * float(fm), 1),
                })
            for row_idx, fm in enumerate(fms_y):
                row_results.append({
                    "Node":         node_no,
                    "Depth [m]":    round(z, 3),
                    "Trib. L [m]":  round(trib_len, 3),
                    "Direction":    "Y",
                    "Row No.":      row_idx + 1,
                    "Row Position": group_row_position(row_idx),
                    "fm":           round(float(fm), 3),
                    "Soil_Type":    soil_type,
                    "N-SPT":        N_val,
                    "kh [kN/m3]":   round(kh_y, 1),
                    "Deq [m]":      round(Deq_y, 3),
                    "Kspring [kN/m]": round(kh_y * Deq_y * trib_len * float(fm), 1),
                })

    df_results = pd.DataFrame(results)
    df_row_results = pd.DataFrame(row_results)
    if not df_row_results.empty:
        df_row_results = df_row_results[[
            "Node", "Depth [m]", "Trib. L [m]", "Direction", "Row No.",
            "Row Position", "fm", "Soil_Type", "N-SPT", "kh [kN/m3]",
            "Deq [m]", "Kspring [kN/m]"
        ]]
    eps_depth = 1e-9
    tip_mask = (df_soil_calc["Depth_From"] <= L + eps_depth) & (df_soil_calc["Depth_To"] >= L - eps_depth)
    # If the pile tip lies exactly on a layer boundary, use the lower layer
    # where available because the pile tip bears into the material below.
    tip_layer = df_soil_calc[tip_mask].iloc[-1] if tip_mask.any() else df_soil_calc.iloc[-1]
    N_tip          = float(tip_layer["SPT_N"])
    D_tip_eq = D if pile_is_round else equivalent_circular_diameter_from_area(Ap)
    Kv_tip, kv_tip = calc_kv_tip(N_tip, D_tip_eq, Ap, design_stage)

    kh_avg_x = df_results["kh_x [kN/m3]"].replace(0, np.nan).mean()
    kh_avg_y = df_results["kh_y [kN/m3]"].replace(0, np.nan).mean()

    def _calc_beta(kh_avg_dir, Deq_dir, Ip_dir):
        if pd.isna(kh_avg_dir) or kh_avg_dir <= 0 or Ep * Ip_dir <= 0:
            return 0.0
        return (kh_avg_dir * Deq_dir / (4 * Ep * Ip_dir))**0.25

    beta_x = _calc_beta(kh_avg_x, Deq_x, Ipy)
    beta_y = _calc_beta(kh_avg_y, Deq_y, Ipx)
    beta = beta_x
    kh_avg = kh_avg_x

    kh_max_surface, kh_min_deep, as_ratio_rec, As_min = calculate_rebar_params(df_results, Ap)

st.sidebar.header("5. Export")
if _ready:
    try:
        excel_data = build_excel(
            df_results, df_row_results, df_soil_draw, N_tip, Kv_tip, kv_tip, D_tip_eq, Ap, Ep, Ipx, Ipy, B, H, L, fc,
            node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta, beta_x, beta_y,
            kh_max_surface, kh_min_deep, as_ratio_rec, As_min, use_group, spring_output
        )
        st.sidebar.download_button(
            "Download Excel (.xlsx)",
            data=excel_data,
            file_name=f"PileSpring_{method}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except RuntimeError as e:
        st.sidebar.error(str(e))
else:
    st.sidebar.button(
        "Download Excel (.xlsx)",
        disabled=True,
        use_container_width=True,
        help="Complete the soil layer input first.",
    )

st.sidebar.markdown("---")
st.sidebar.caption(f"App Version {VERSION}")
with tab2:
    mc = st.columns(6)
    mc[0].metric("Method", method)
    mc[1].metric("Beta X [1/m]", f"{beta_x:.3f}" if (_ready and beta_x > 0) else "-")
    mc[2].metric("Beta Y [1/m]", f"{beta_y:.3f}" if (_ready and beta_y > 0) else "-")
    mc[3].metric("Kv_tip [kN/m]", f"{Kv_tip:,.0f}" if _ready else "-")
    if use_group and spring_output == "Row-based spring table":
        mc[4].metric("p-mult", "Row-based")
    else:
        mc[4].metric("Avg p-mult", f"{Pmult:.3f}")
    mc[5].metric("Nodes", len(depths) if _ready else "-")
    st.divider()

    r_left, r_right = st.columns([2, 3], gap="medium")
    with r_left:
        st.subheader("Calculation Results")
        if not _ready or df_results.empty:
            st.info("Complete the soil layer input to show calculation results.")
        else:
            if use_group and spring_output == "Row-based spring table" and not df_row_results.empty:
                st.caption("Row-based output: one spring stiffness per depth, direction, and pile row.")
                st.dataframe(df_row_results.style.format({
                    "Depth [m]": "{:.2f}",
                    "Trib. L [m]": "{:.3f}",
                    "fm": "{:.3f}",
                    "N-SPT": "{:.0f}",
                    "kh [kN/m3]": "{:,.0f}",
                    "Deq [m]": "{:.3f}",
                    "Kspring [kN/m]": "{:,.1f}",
                }), use_container_width=True, height=580)
            else:
                st.caption("Global average output: Ksx and Ksy use the average p-multiplier shown in the sidebar.")
                st.dataframe(df_results.style.format({
                    "Depth [m]": "{:.2f}",
                    "kh_x [kN/m3]": "{:,.0f}",
                    "kh_y [kN/m3]": "{:,.0f}",
                    "Ksx [kN/m]": "{:,.1f}",
                    "Ksy [kN/m]": "{:,.1f}",
                }), use_container_width=True, height=580)

    with r_right:
        st.subheader("Soil-Pile Profile with Springs (Global Average)")
        SOIL_COLORS = {"Clay": "#8B6354", "Sand": "#D4AA6A"}
        fig_p = go.Figure()
        x_pile = Deq_x / 2
        x_max = Deq_x * 4.0

        for _, lrow in df_soil_draw.iterrows():
            fig_p.add_shape(type="rect", x0=-x_max, y0=lrow["Depth_From"], x1=x_max, y1=lrow["Depth_To"],
                            fillcolor=SOIL_COLORS.get(lrow["Soil_Type"], "#888"), opacity=0.25, line_width=0, layer="below")
            mid = (lrow["Depth_From"] + lrow["Depth_To"]) / 2
            fig_p.add_annotation(x=x_max * 1.02, y=mid, text=f"<b>{lrow['Soil_Type']}</b> N={lrow['SPT_N']:.0f}",
                                 showarrow=False, xanchor="left", font=dict(size=10))

        if scour_depth > 0:
            fig_p.add_shape(type="rect", x0=-x_max, y0=0, x1=x_max, y1=scour_depth,
                            fillcolor="rgba(200,200,200,0.55)", line_width=0, layer="below")
            fig_p.add_annotation(x=-x_max * 0.95, y=scour_depth / 2, text=f"<b>SCOUR</b><br>{scour_depth:.1f} m",
                                 showarrow=False, xanchor="left", font=dict(size=10, color="#555"))

        fig_p.add_shape(type="rect", x0=-x_pile, y0=0, x1=x_pile, y1=L,
                        line=dict(color="#1a4f8a", width=2), fillcolor="rgba(180,210,240,0.6)", layer="above")
        spr_len = Deq_x * 1.2
        if _ready and not df_results.empty:
            for z, ksx in zip(depths, df_results["Ksx [kN/m]"]):
                if ksx > 1e-3:
                    sx, sy = draw_spring(x_pile, x_pile + spr_len, z)
                    fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines', line=dict(color='#2166ac', width=1.8), showlegend=False, hoverinfo='skip'))
                    sx, sy = draw_spring(-x_pile - spr_len, -x_pile, z)
                    fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines', line=dict(color='#2166ac', width=1.8), showlegend=False, hoverinfo='skip'))
            fig_p.add_trace(go.Scatter(x=[0] * len(depths), y=depths, mode='markers', marker=dict(color='red', size=7),
                                       name="Node", hovertemplate='z=%{y:.2f}m<br>Ksx=%{customdata[0]:.0f} kN/m<extra></extra>',
                                       customdata=list(zip(df_results["Ksx [kN/m]"]))))
            fig_p.add_trace(go.Scatter(x=[0], y=[L], mode='markers+text', marker=dict(color='#d62728', size=14, symbol='diamond'),
                                       text=[f"  Kv_tip={Kv_tip:,.0f}"], textposition="middle right", name="Kv_tip", showlegend=False))
        fig_p.add_hline(y=water_table, line_dash="dash", line_color="#2196F3", line_width=1.5,
                        annotation_text=f"WT @ {water_table:.1f} m", annotation_position="right")
        fig_p.update_layout(height=700, yaxis=dict(autorange="reversed", title="Depth [m]"),
                            xaxis=dict(title="Width [m]"), plot_bgcolor="rgba(248,250,255,1)",
                            margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_p, use_container_width=True)

with tab3:
    if not _ready or df_results.empty:
        st.info("Complete the soil layer input to show plots.")
    else:
        p1, p2 = st.columns(2)
        with p1:
            st.subheader("kh vs Depth (Base kh before p-mult)")
            fig_kh = go.Figure()
            fig_kh.add_trace(go.Scatter(x=df_results["kh_x [kN/m3]"], y=df_results["Depth [m]"],
                                        mode='lines+markers', name='kh_x',
                                        line=dict(color='#1a4f8a', width=2), marker=dict(size=5)))
            if not pile_is_round:
                fig_kh.add_trace(go.Scatter(x=df_results["kh_y [kN/m3]"], y=df_results["Depth [m]"],
                                            mode='lines+markers', name='kh_y',
                                            line=dict(color='#c0392b', width=2, dash='dash'), marker=dict(size=5)))
            if water_table < L:
                fig_kh.add_hline(y=water_table, line_dash="dot", line_color="#2196F3",
                                 annotation_text=f"WT {water_table:.1f}m", annotation_position="right")
            if scour_depth > 0:
                fig_kh.add_hrect(y0=0, y1=scour_depth, fillcolor="rgba(150,150,150,0.25)",
                                 line_width=0, annotation_text="Scour", annotation_position="top left")
            fig_kh.update_layout(height=500, yaxis=dict(autorange="reversed", title="Depth [m]"),
                                 xaxis=dict(title="kh [kN/m3]"),
                                 legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                                             bgcolor="rgba(255,255,255,0.85)", bordercolor="#ccc", borderwidth=1),
                                 margin=dict(l=10, r=10, t=60, b=10))
            st.plotly_chart(fig_kh, use_container_width=True)

        with p2:
            st.subheader("Spring Stiffness vs Depth (Global Average)")
            fig_ks = go.Figure()
            fig_ks.add_trace(go.Scatter(x=df_results["Ksx [kN/m]"], y=df_results["Depth [m]"],
                                        mode='lines+markers', name='Ksx', line=dict(color='#1a4f8a', width=2),
                                        fill='tozerox', fillcolor='rgba(26,79,138,0.08)'))
            if not pile_is_round:
                fig_ks.add_trace(go.Scatter(x=df_results["Ksy [kN/m]"], y=df_results["Depth [m]"],
                                            mode='lines+markers', name='Ksy', line=dict(color='#c0392b', width=2, dash='dash'),
                                            fill='tozerox', fillcolor='rgba(192,57,43,0.06)'))
            fig_ks.add_trace(go.Scatter(x=[Kv_tip], y=[L], mode='markers', name='Kv_tip',
                                        marker=dict(color='#d62728', size=14, symbol='diamond'),
                                        hovertemplate=f'Kv_tip = {Kv_tip:,.0f} kN/m<extra></extra>'))
            fig_ks.add_annotation(x=Kv_tip, y=L, ax=20, ay=-30, xref='x', yref='y', axref='pixel', ayref='pixel',
                                  text=f"<b>Kv_tip = {Kv_tip:,.0f}</b>", showarrow=True, arrowhead=2, arrowsize=1,
                                  arrowwidth=1.2, arrowcolor='#d62728', bgcolor="rgba(255,255,255,0.9)",
                                  bordercolor="#d62728", borderwidth=1, borderpad=4, font=dict(size=11, color='#d62728'))
            if water_table < L:
                fig_ks.add_hline(y=water_table, line_dash="dot", line_color="#2196F3",
                                 annotation_text=f"WT {water_table:.1f}m", annotation_position="right")
            if scour_depth > 0:
                fig_ks.add_hrect(y0=0, y1=scour_depth, fillcolor="rgba(150,150,150,0.25)",
                                 line_width=0, annotation_text="Scour", annotation_position="top left")
            fig_ks.update_layout(height=500, yaxis=dict(autorange="reversed", title="Depth [m]"),
                                 xaxis=dict(title="Spring Stiffness [kN/m]"),
                                 legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                                             bgcolor="rgba(255,255,255,0.85)", bordercolor="#ccc", borderwidth=1),
                                 margin=dict(l=10, r=10, t=60, b=10))
            st.plotly_chart(fig_ks, use_container_width=True)

        st.subheader("Beta - Relative Stiffness")
        beta_rows = []
        for label, beta_val, kh_avg_dir, Deq_dir, Ip_dir in [
            ("X", beta_x, kh_avg_x, Deq_x, Ipy),
            ("Y", beta_y, kh_avg_y, Deq_y, Ipx),
        ]:
            if beta_val > 0:
                beta_rows.append({
                    "Direction": label,
                    "kh_avg [kN/m3]": kh_avg_dir,
                    "Deq [m]": Deq_dir,
                    "Ip used [m4]": Ip_dir,
                    "Beta [1/m]": beta_val,
                    "1/Beta [m]": 1 / beta_val,
                    "4/Beta [m]": 4 / beta_val,
                    "Pile Type": "Long" if L > 4 / beta_val else "Short",
                })
        if beta_rows:
            st.dataframe(pd.DataFrame(beta_rows).style.format({
                "kh_avg [kN/m3]": "{:,.0f}",
                "Deq [m]": "{:.3f}",
                "Ip used [m4]": "{:.6f}",
                "Beta [1/m]": "{:.4f}",
                "1/Beta [m]": "{:.2f}",
                "4/Beta [m]": "{:.2f}",
            }), use_container_width=True, hide_index=True)
            st.caption("Beta X uses kh_x, Deq_x, and Iy. Beta Y uses kh_y, Deq_y, and Ix.")
        else:
            st.warning("Beta cannot be computed because average kh is zero. Check scour depth and soil profile.")

        st.divider()
        st.subheader("Engineering Guidance")
        with st.expander("How to interpret the kh methods", expanded=True):
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("""
**Typical kh trend depends on soil type and depth.**

| Situation | Typical kh trend |
|-----------|------------------|
| Soft clay, shallow depth | Terzaghi approx. Vesic < JRA << Broms |
| Stiff clay, deeper layer | Terzaghi < JRA approx. Vesic << Broms |
| Loose sand, shallow depth | Terzaghi < Vesic < JRA << Broms |
| Dense sand, deeper layer | Vesic < JRA < Terzaghi << Broms |

**Broms often gives high stiffness** because it is derived from ultimate lateral resistance at a reference displacement. Treat it as a capacity-oriented check, not a direct elastic spring for final FEA.
""")
            with col_g2:
                st.markdown("""
**Suggested workflow**

| Method | Role | Note |
|--------|------|------|
| JRA | Primary design | Practical for bridge/highway preliminary spring values. |
| Terzaghi | Cross-check | Useful conservative comparison. |
| Vesic | Special check | Best when reliable Es is available. |
| Broms | Capacity check | Do not use directly as the only elastic spring. |

Report the chosen primary method and include sensitivity checks where project risk is high.
""")
with tab4:
    st.header("Pile Design")
    st.caption(
        "Load-case based reinforced concrete pile design. Enter factored axial load and pile-head shears, "
        "then review force diagrams, envelopes, and preliminary ACI 318-style PMM interaction checks."
    )

    if not _ready or df_results.empty:
        st.info("Please complete the soil profile first. Pile Design uses the calculated spring table.")
    else:
        source_options = ["Global average spring"]
        if use_group and not df_row_results.empty:
            source_options.append("Row-based spring")

        src_col, rowx_col, rowy_col = st.columns([1.2, 1.0, 1.0])
        spring_source = src_col.selectbox(
            "Spring source",
            source_options,
            help="Global average uses Ksx/Ksy from the main results table. Row-based uses selected pile rows."
        )
        if spring_source == "Row-based spring":
            x_design_row = rowx_col.selectbox("X-direction pile row", list(range(1, int(nx) + 1)))
            y_design_row = rowy_col.selectbox("Y-direction pile row", list(range(1, int(ny) + 1)))
        else:
            x_design_row = y_design_row = 1
            rowx_col.metric("X pile row", "Average")
            rowy_col.metric("Y pile row", "Average")

        st.subheader("Pile Head Boundary Condition")
        bc1, bc2, bc3 = st.columns([1.25, 1.15, 1.0])
        head_condition = bc1.selectbox(
            "Head condition",
            ["Free Head / Shear Only", "Fixed Head (theta = 0)", "Rotational Spring"],
            index=1,
            help=(
                "Free Head applies Hx/Hy with zero external head moment. "
                "Fixed Head restrains pile-head rotation and solves the reaction moment internally. "
                "Rotational Spring adds Kθ at the pile head."
            ),
        )

        ktheta_presets = {
            "Low restraint — 10,000": 1.0e4,
            "Medium restraint — 100,000": 1.0e5,
            "High restraint — 1,000,000": 1.0e6,
            "Nearly fixed — 10,000,000": 1.0e7,
            "Custom": None,
        }

        if head_condition == "Rotational Spring":
            ktheta_preset = bc2.selectbox(
                "Kθ preset",
                list(ktheta_presets.keys()),
                index=1,
                help=(
                    "Trial rotational restraint values. These are modelling parameters, not fixed code values. "
                    "Run a sensitivity check against Free Head and Fixed Head for final design."
                ),
            )
            if ktheta_presets[ktheta_preset] is None:
                ktheta_head = bc3.number_input(
                    "Custom Kθ [kN-m/rad]",
                    min_value=0.0,
                    value=1.0e5,
                    step=1.0e4,
                    format="%.3g",
                    help="Custom pile-head rotational spring stiffness. Use 0 to approach free-head behavior.",
                )
            else:
                ktheta_head = float(ktheta_presets[ktheta_preset])
                bc3.metric("Kθ used [kN-m/rad]", f"{ktheta_head:,.0f}")
        else:
            ktheta_head = 0.0
            bc2.metric("Kθ preset", "—")
            bc3.metric("Kθ used [kN-m/rad]", "—")

        if head_condition == "Free Head / Shear Only":
            st.caption("Assumption: applied Hx/Hy act at the pile head with free rotation; Mhead = 0 unless future optional head moment is introduced.")
        elif head_condition == "Fixed Head (theta = 0)":
            st.caption("Recommended for a pile embedded in a rigid pile cap when no external head moment is supplied. The app solves the head reaction moment internally; do not also add external Mux/Muy from another model.")
        else:
            st.info(
                "Recommended Kθ trial values: 10,000 = low restraint, 100,000 = medium restraint, "
                "1,000,000 = high restraint, 10,000,000 = nearly fixed. "
                "Kθ is not a code-prescribed constant; compare Free Head, Fixed Head, and the selected rotational spring as a sensitivity check."
            )

        sens_col1, sens_col2 = st.columns([1.0, 1.4])
        run_head_sensitivity = sens_col1.checkbox(
            "Run head-condition sensitivity",
            value=False,
            help=(
                "Compare Free Head, rotational springs, and Fixed Head for the same load demand. "
                "This is recommended when the pile-cap rotational restraint is uncertain."
            ),
        )
        if run_head_sensitivity:
            sensitivity_scope = sens_col2.selectbox(
                "Sensitivity scope",
                ["Governing case from current design", "All active load cases"],
                index=0,
                help=(
                    "Governing case is faster and easier to read. All active load cases provides an envelope, "
                    "but can be slower when many cases are imported."
                ),
            )
            st.caption(
                "Sensitivity compares: Free Head, Kθ = 10k / 100k / 1,000k kN-m/rad, and Fixed Head. "
                "Use it to bracket pile-head moment and displacement; it does not change the selected design condition above."
            )
        else:
            sensitivity_scope = "Governing case from current design"

        st.subheader("Design Demand Basis")
        design_demand_basis = st.radio(
            "Preliminary reinforcement/shear demand basis",
            [
                "Case-by-case governing (recommended)",
                "Non-concurrent envelope (legacy / conservative)",
            ],
            index=0,
            horizontal=True,
            help=(
                "Case-by-case uses the actual governing load case and its concurrent response. "
                "Non-concurrent envelope combines maxima that may come from different load cases; keep it only as a conservative legacy screen."
            ),
        )
        if design_demand_basis.startswith("Case-by-case"):
            st.caption(
                "Recommended: design summary uses the governing load case and concurrent max force resultants from that case."
            )
        else:
            st.warning(
                "Legacy envelope mode may combine Pu, V, Mx and My from different load cases. "
                "Use only as a conservative screening check, not as the only final design basis."
            )

        st.subheader("Load Cases")
        default_load_cases = pd.DataFrame({
            "Use": [True, True, True],
            "Load Case": ["LC1", "LC2", "LC3"],
            "Pu [kN]": [1500.0, 1800.0, 1200.0],
            "Hx [kN]": [200.0, 0.0, 160.0],
            "Hy [kN]": [0.0, 200.0, 120.0],
        })
        if "pile_design_load_cases" not in st.session_state:
            st.session_state["pile_design_load_cases"] = default_load_cases.copy()

        with st.expander("Import load cases from Pile Cap STM / Excel", expanded=False):
            st.caption(
                "Recommended transfer format: Use | Load Case | Pu [kN] | Hx [kN] | Hy [kN]. "
                "This matches the Soil Spring Input (.tsv) exported from the Pile Cap STM app. "
                "You may also paste only Load Case | Pu [kN] | Hx [kN] | Hy [kN]."
            )

            uploaded_lc_file = st.file_uploader(
                "Upload Soil Spring Input from Pile Cap STM (.tsv/.csv/.xlsx)",
                type=["tsv", "csv", "txt", "xlsx", "xls"],
                key="pile_design_load_case_upload",
                help=(
                    "Use the .tsv exported by the Pile Cap STM app, or an Excel file "
                    "with columns Use, Load Case, Pu [kN], Hx [kN], Hy [kN]."
                ),
            )
            up_col1, up_col2 = st.columns([1.0, 3.0])
            if up_col1.button("Import uploaded file", use_container_width=True):
                try:
                    imported_cases = parse_uploaded_load_case_file(uploaded_lc_file)
                    st.session_state["pile_design_load_cases"] = imported_cases.copy()
                    st.session_state["pile_design_load_case_source"] = (
                        getattr(uploaded_lc_file, "name", "uploaded file") if uploaded_lc_file is not None else "uploaded file"
                    )
                    if "pile_design_load_case_editor" in st.session_state:
                        del st.session_state["pile_design_load_case_editor"]
                    st.success(f"Imported {len(imported_cases)} load cases from uploaded file.")
                except Exception as e:
                    st.error(f"Cannot import uploaded load cases: {e}")
            up_col2.caption(
                "Import replaces the current load-case table. Check signs: compression Pu is positive; uplift is negative."
            )

            paste_text = st.text_area(
                "Paste Excel cells here",
                value="",
                height=140,
                placeholder=(
                    "Use\tLoad Case\tPu [kN]\tHx [kN]\tHy [kN]\n"
                    "TRUE\tLC1\t1500\t200\t0\n"
                    "TRUE\tLC2\t1800\t0\t200"
                ),
                key="pile_design_load_case_paste_text",
            )
            imp_col1, imp_col2, imp_col3 = st.columns([1.0, 1.0, 2.0])
            if imp_col1.button("Import pasted table", use_container_width=True):
                try:
                    imported_cases = parse_pasted_load_cases(paste_text)
                    st.session_state["pile_design_load_cases"] = imported_cases.copy()
                    st.session_state["pile_design_load_case_source"] = "Excel/clipboard paste"
                    if "pile_design_load_case_editor" in st.session_state:
                        del st.session_state["pile_design_load_case_editor"]
                    st.success(f"Imported {len(imported_cases)} load cases from Excel paste.")
                except Exception as e:
                    st.error(f"Cannot import pasted load cases: {e}")
            if imp_col2.button("Reset default cases", use_container_width=True):
                st.session_state["pile_design_load_cases"] = default_load_cases.copy()
                st.session_state.pop("pile_design_load_case_source", None)
                if "pile_design_load_case_editor" in st.session_state:
                    del st.session_state["pile_design_load_case_editor"]
                st.info("Default load cases restored.")
            imp_col3.caption("Import replaces the current load-case table only. Calculation formulas are unchanged.")

        if st.session_state.get("pile_design_load_case_source"):
            st.info(
                f"Current load-case table source: {st.session_state['pile_design_load_case_source']} "
                "(verify units and signs before design)."
            )

        load_case_input = st.data_editor(
            st.session_state["pile_design_load_cases"],
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="pile_design_load_case_editor",
            column_config={
                "Use": st.column_config.CheckboxColumn("Use", default=True, width="small"),
                "Load Case": st.column_config.TextColumn("Load Case", width="medium"),
                "Pu [kN]": st.column_config.NumberColumn("Pu [kN]", format="%.1f", help="Compression positive; use negative for tension/uplift."),
                "Hx [kN]": st.column_config.NumberColumn("Pile-head shear Hx [kN]", format="%.1f"),
                "Hy [kN]": st.column_config.NumberColumn("Pile-head shear Hy [kN]", format="%.1f"),
            }
        )

        load_cases = clean_pile_load_cases(load_case_input, drop_blank=True)
        st.session_state["pile_design_load_cases"] = load_cases.copy()
        active_cases = load_cases[load_cases["Use"]].copy().reset_index(drop=True)

        st.subheader("Reinforcement and ACI PMM Settings")
        det1, det2, det3, det4, det5 = st.columns(5)
        cover_mm = det1.number_input("Clear cover [mm]", min_value=40, max_value=150, value=75, step=5)
        main_bar = det2.selectbox("Main bar", list(REBAR_DB.keys()), index=2)
        tie_bar = det3.selectbox("Tie / spiral bar", list(REBAR_DB.keys()), index=1)
        tie_spacing_mm = det4.number_input("Provided tie spacing [mm]", min_value=50, max_value=400, value=150, step=10)
        transverse_system = det5.selectbox("Transverse system", ["Tied", "Spiral"], index=0)

        if pile_type == "Round":
            cfg1, cfg2 = st.columns(2)
            n_main_bars = cfg1.number_input("Number of main bars", min_value=4, max_value=60, value=10, step=1)
            n_tie_legs = cfg2.number_input("Equivalent tie legs", min_value=2, max_value=12, value=2, step=1)
            n_b_face = n_h_face = None
        else:
            cfg1, cfg2, cfg3 = st.columns(3)
            n_b_face = cfg1.number_input("Bars on B face", min_value=2, max_value=30, value=4, step=1)
            n_h_face = cfg2.number_input("Bars on H face", min_value=2, max_value=30, value=4, step=1)
            n_tie_legs = cfg3.number_input("Tie legs", min_value=2, max_value=12, value=2, step=1)
            n_main_bars = None

        try:
            load_case_hash = int(pd.util.hash_pandas_object(load_cases, index=True).sum())
        except Exception:
            load_case_hash = hash(load_cases.to_json())
        if spring_source == "Row-based spring" and use_group and not df_row_results.empty:
            spring_sig_df = df_row_results[["Direction", "Row No.", "Node", "Depth [m]", "Kspring [kN/m]"]].copy()
        else:
            spring_sig_df = df_results[["Node", "Depth [m]", "Ksx [kN/m]", "Ksy [kN/m]"]].copy()
        try:
            spring_table_hash = int(pd.util.hash_pandas_object(spring_sig_df, index=True).sum())
        except Exception:
            spring_table_hash = hash(spring_sig_df.to_json())
        pile_design_signature = json.dumps({
            "load_case_hash": load_case_hash,
            "spring_source": spring_source,
            "x_design_row": int(x_design_row),
            "y_design_row": int(y_design_row),
            "spring_table_hash": spring_table_hash,
            "pile_type": pile_type,
            "D": float(D),
            "B": float(B),
            "H": float(H),
            "L": float(L),
            "fc": float(fc),
            "cover_mm": float(cover_mm),
            "main_bar": main_bar,
            "tie_bar": tie_bar,
            "tie_spacing_mm": float(tie_spacing_mm),
            "transverse_system": transverse_system,
            "head_condition": head_condition,
            "ktheta_head": float(ktheta_head),
            "design_demand_basis": design_demand_basis,
            "n_main_bars": None if n_main_bars is None else int(n_main_bars),
            "n_b_face": None if n_b_face is None else int(n_b_face),
            "n_h_face": None if n_h_face is None else int(n_h_face),
            "n_tie_legs": int(n_tie_legs),
        }, sort_keys=True)

        previous_signature = st.session_state.get("pile_design_last_signature")
        if bool(st.session_state.get("pile_design_has_run", False)) and previous_signature != pile_design_signature:
            st.session_state["pile_design_has_run"] = False
            st.session_state["pile_design_stale_reason"] = "Inputs changed after the last run."

        run_col, note_col = st.columns([1.0, 2.2])
        if run_col.button("Run / Update Pile Design", type="primary", use_container_width=True):
            st.session_state["pile_design_has_run"] = True
            st.session_state["pile_design_last_signature"] = pile_design_signature
            st.session_state.pop("pile_design_stale_reason", None)
        note_col.caption("PMM interaction and force diagrams are calculated only after pressing this button. Editing inputs makes the previous run stale.")
        design_has_run = bool(st.session_state.get("pile_design_has_run", False))
        if not design_has_run:
            stale_reason = st.session_state.get("pile_design_stale_reason", "")
            if stale_reason:
                st.warning(f"{stale_reason} Click **Run / Update Pile Design** to recalculate.")
            else:
                st.info("Click **Run / Update Pile Design** after editing load cases or reinforcement.")
            active_cases = active_cases.iloc[0:0].copy()

        if active_cases.empty:
            if design_has_run:
                st.warning("Add at least one active load case to run pile design.")
        else:
            if spring_source == "Global average spring":
                spring_k_x = df_results["Ksx [kN/m]"].to_numpy(dtype=float)
                spring_k_y = df_results["Ksy [kN/m]"].to_numpy(dtype=float)
                spring_note = "Using global average Ksx and Ksy spring tables."
            else:
                spring_df_x = df_row_results[
                    (df_row_results["Direction"] == "X")
                    & (df_row_results["Row No."] == int(x_design_row))
                ].sort_values("Node").copy()
                spring_df_y = df_row_results[
                    (df_row_results["Direction"] == "Y")
                    & (df_row_results["Row No."] == int(y_design_row))
                ].sort_values("Node").copy()
                spring_k_x = spring_df_x["Kspring [kN/m]"].to_numpy(dtype=float)
                spring_k_y = spring_df_y["Kspring [kN/m]"].to_numpy(dtype=float)
                spring_note = f"Using row-based springs: X row {x_design_row}, Y row {y_design_row}."

            st.info(spring_note)
            spring_ok = (
                len(spring_k_x) == len(depths)
                and len(spring_k_y) == len(depths)
                and np.any(np.abs(spring_k_x) > 1e-9)
                and np.any(np.abs(spring_k_y) > 1e-9)
            )
            if not spring_ok:
                st.error("The selected spring source is empty or does not align with the pile depth nodes.")
            else:
                pmm_df, bar_df = build_aci_pmm_interaction(
                    pile_type, D, B, H, fc, cover_mm, tie_bar, main_bar,
                    n_main_bars=n_main_bars, n_b_face=n_b_face, n_h_face=n_h_face,
                    transverse_system=transverse_system
                )
                mx_curve = uniaxial_interaction_curve(pmm_df, "Mx")
                my_curve = uniaxial_interaction_curve(pmm_df, "My")
                phi_tn_kN = calc_phi_tension_capacity_from_bars(bar_df)
                pmm_finite, pmm_p_min, pmm_p_max, pmm_p_tol = prepare_pmm_surface_for_checks(pmm_df)
                pmm_slice_cache = {}

                profile_frames = []
                summary_rows = []
                response_error = None
                EI_x_loading = Ep * Ipy
                EI_y_loading = Ep * Ipx

                for case_no, (_, case) in enumerate(active_cases.iterrows(), start=1):
                    lc = str(case["Load Case"])
                    case_plot_label = f"{case_no:03d} - {lc}"
                    pu_kN = float(case["Pu [kN]"])
                    hx_kN = float(case["Hx [kN]"])
                    hy_kN = float(case["Hy [kN]"])
                    try:
                        disp_x, theta_x, soil_rx, shear_x, moment_y, mhead_y = solve_pile_lateral_response(
                            depths, spring_k_x, EI_x_loading, head_shear=hx_kN, head_moment=0.0,
                            head_condition=head_condition, rotational_stiffness=ktheta_head
                        )
                        disp_y, theta_y, soil_ry, shear_y, moment_x, mhead_x = solve_pile_lateral_response(
                            depths, spring_k_y, EI_y_loading, head_shear=hy_kN, head_moment=0.0,
                            head_condition=head_condition, rotational_stiffness=ktheta_head
                        )
                    except Exception as exc:
                        response_error = f"{lc}: {exc}"
                        break

                    axial = np.full(len(depths), pu_kN, dtype=float)
                    shear_resultant = np.sqrt(shear_x**2 + shear_y**2)
                    moment_resultant = np.sqrt(moment_x**2 + moment_y**2)
                    frame = pd.DataFrame({
                        "Case No.": case_no,
                        "Case Plot Label": case_plot_label,
                        "Load Case": lc,
                        "Head Condition": head_condition,
                        "Mhead X [kN-m]": float(mhead_x),
                        "Mhead Y [kN-m]": float(mhead_y),
                        "Depth [m]": depths,
                        "Pu [kN]": axial,
                        "Vx [kN]": shear_x,
                        "Vy [kN]": shear_y,
                        "V resultant [kN]": shear_resultant,
                        "Mux [kN-m]": moment_x,
                        "Muy [kN-m]": moment_y,
                        "M resultant [kN-m]": moment_resultant,
                        "Disp X [mm]": disp_x * 1000.0,
                        "Disp Y [mm]": disp_y * 1000.0,
                        "Soil Rx [kN]": soil_rx,
                        "Soil Ry [kN]": soil_ry,
                    })
                    profile_frames.append(frame)

                    mcap_x = moment_capacity_at_p(mx_curve, pu_kN)
                    mcap_y = moment_capacity_at_p(my_curve, pu_kN)
                    linear_util_profile = (
                        np.abs(moment_x) / max(mcap_x, 1e-9)
                        + np.abs(moment_y) / max(mcap_y, 1e-9)
                    )
                    linear_util_profile = np.where(np.isfinite(linear_util_profile), linear_util_profile, np.inf)
                    if pmm_finite.empty:
                        pmm_checks = [
                            {
                                "utilization": np.inf,
                                "capacity_m": 0.0,
                                "capacity_mux": 0.0,
                                "capacity_muy": 0.0,
                                "pu_used": pu_kN,
                                "status": "No PMM surface",
                            }
                            for _ in range(len(moment_x))
                        ]
                    else:
                        pu_use, pu_out_status = clamp_pu_to_pmm_range(pu_kN, pmm_p_min, pmm_p_max, pmm_p_tol)
                        cache_key = round(float(pu_use), 6)
                        if pu_out_status:
                            slice_for_case = pd.DataFrame()
                        else:
                            if cache_key not in pmm_slice_cache:
                                pmm_slice_cache[cache_key] = pmm_slice_at_p(pmm_finite, pu_use)
                            slice_for_case = pmm_slice_cache[cache_key]
                        pmm_checks = [
                            pmm_utilization_from_slice(slice_for_case, pu_use, mx, my, pu_out_status)
                            for mx, my in zip(moment_x, moment_y)
                        ]
                    util_profile = np.asarray([chk["utilization"] for chk in pmm_checks], dtype=float)
                    util_profile = np.where(np.isfinite(util_profile), util_profile, np.inf)
                    tension_util, tension_status = tension_utilization_for_pu(pu_kN, phi_tn_kN)
                    overall_case_util = max(float(np.max(util_profile)), float(tension_util))
                    overall_case_status = "OK" if overall_case_util <= 1.0 else "NG"
                    imx = int(np.argmax(np.abs(moment_x))) if len(moment_x) else 0
                    imy = int(np.argmax(np.abs(moment_y))) if len(moment_y) else 0
                    iv = int(np.argmax(np.abs(shear_resultant))) if len(shear_resultant) else 0
                    iu = int(np.argmax(util_profile)) if len(util_profile) else 0
                    governing_pmm = pmm_checks[iu] if pmm_checks else {
                        "capacity_m": 0.0,
                        "capacity_mux": 0.0,
                        "capacity_muy": 0.0,
                        "status": "No PMM check",
                    }
                    summary_rows.append({
                        "Case No.": case_no,
                        "Case Plot Label": case_plot_label,
                        "Load Case": lc,
                        "Head Condition": head_condition,
                        "Mhead X [kN-m]": float(mhead_x),
                        "Mhead Y [kN-m]": float(mhead_y),
                        "Max Pu [kN]": float(np.max(axial)),
                        "Min Pu [kN]": float(np.min(axial)),
                        "Max |Mux| [kN-m]": float(np.max(np.abs(moment_x))),
                        "z @ Mux [m]": float(depths[imx]),
                        "Max |Muy| [kN-m]": float(np.max(np.abs(moment_y))),
                        "z @ Muy [m]": float(depths[imy]),
                        "Max M resultant [kN-m]": float(np.max(moment_resultant)),
                        "z @ M resultant [m]": float(depths[int(np.argmax(moment_resultant))]) if len(moment_resultant) else 0.0,
                        "Max |V| [kN]": float(np.max(np.abs(shear_resultant))),
                        "z @ V [m]": float(depths[iv]),
                        "PMM Util.": float(np.max(util_profile)),
                        "Tension Util.": float(tension_util),
                        "Overall Util.": float(overall_case_util),
                        "Overall Status": overall_case_status,
                        "Linear PMM Util.": float(np.max(linear_util_profile)),
                        "z @ PMM [m]": float(depths[iu]),
                        "PMM Mux [kN-m]": float(moment_x[iu]) if len(moment_x) else 0.0,
                        "PMM Muy [kN-m]": float(moment_y[iu]) if len(moment_y) else 0.0,
                        "PMM M resultant [kN-m]": float(moment_resultant[iu]) if len(moment_resultant) else 0.0,
                        "PMM radial cap [kN-m]": float(governing_pmm["capacity_m"]),
                        "PMM cap Mux [kN-m]": float(governing_pmm["capacity_mux"]),
                        "PMM cap Muy [kN-m]": float(governing_pmm["capacity_muy"]),
                        "PMM Status": governing_pmm["status"],
                        "φTn tension cap [kN]": float(phi_tn_kN),
                        "Tension Status": tension_status,
                        "Pu Sign": "Tension/Uplift" if pu_kN < 0.0 else "Compression",
                        "Mx cap @ Pu [kN-m]": mcap_x,
                        "My cap @ Pu [kN-m]": mcap_y,
                    })

                if response_error:
                    st.error(f"Pile response analysis could not run: {response_error}")
                else:
                    profile_df = pd.concat(profile_frames, ignore_index=True)
                    demand_df = pd.DataFrame(summary_rows)
                    max_util = float(demand_df["Overall Util."].max()) if not demand_df.empty else np.inf
                    max_pmm_util = float(demand_df["PMM Util."].max()) if not demand_df.empty else np.inf
                    max_tension_util = float(demand_df["Tension Util."].max()) if not demand_df.empty else 0.0
                    governing = demand_df.loc[demand_df["Overall Util."].idxmax()] if not demand_df.empty else None
                    overall_pu_max = float(demand_df["Max Pu [kN]"].max())
                    overall_pu_min = float(demand_df["Min Pu [kN]"].min())
                    overall_mx = float(demand_df["Max |Mux| [kN-m]"].max())
                    overall_my = float(demand_df["Max |Muy| [kN-m]"].max())
                    overall_v = float(demand_df["Max |V| [kN]"].max())
                    overall_m = float(np.sqrt(overall_mx**2 + overall_my**2))

                    if design_demand_basis.startswith("Case-by-case") and governing is not None:
                        shear_design_case = str(governing["Load Case"])
                        shear_design_pu = max(float(governing["Max Pu [kN]"]), 0.0)
                        shear_design_v = float(governing["Max |V| [kN]"])
                        shear_design_m = float(governing.get("Max M resultant [kN-m]", governing.get("PMM M resultant [kN-m]", 0.0)))
                        shear_design_note = "Case-by-case governing demand; force resultants are from the controlling load case."
                    else:
                        shear_design_case = "Non-concurrent envelope"
                        shear_design_pu = max(overall_pu_max, 0.0)
                        shear_design_v = overall_v
                        shear_design_m = overall_m
                        shear_design_note = "Legacy envelope demand; maxima may come from different load cases."

                    shear_summary = calc_pile_design_summary(
                        pile_type, D, B, H, fc, cover_mm, main_bar, tie_bar,
                        "X", shear_design_pu, shear_design_v, shear_design_m,
                        n_main_bars, n_b_face, n_h_face, n_tie_legs, as_ratio_rec
                    )
                    tie_ok = float(tie_spacing_mm) <= float(shear_summary["s_rec_mm"]) + 1e-9

                    # Store latest design run for Report / QA tab. This does not affect calculation results.
                    latest_report = {
                        "project": project_meta.copy(),
                        "meta": {
                            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "app_version": VERSION,
                            "load_case_source": st.session_state.get("pile_design_load_case_source", "Manual / in-app table"),
                        },
                        "inputs": {
                            "kh_method": method,
                            "design_stage": design_stage,
                            "spring_source": spring_source,
                            "x_design_row": int(x_design_row),
                            "y_design_row": int(y_design_row),
                            "head_condition": head_condition,
                            "ktheta_head": float(ktheta_head),
                            "design_demand_basis": design_demand_basis,
                            "pile_type": pile_type,
                            "D": float(D),
                            "B": float(B),
                            "H": float(H),
                            "L": float(L),
                            "fc": float(fc),
                            "node_spacing": float(node_spacing),
                            "water_table": float(water_table),
                            "scour_depth": float(scour_depth),
                            "main_bar": main_bar,
                            "tie_bar": tie_bar,
                            "tie_spacing_mm": float(tie_spacing_mm),
                            "transverse_system": transverse_system,
                            "cover_mm": float(cover_mm),
                            "n_main_bars": int(n_main_bars) if pile_type == "Round" else None,
                            "n_b_face": int(n_b_face) if pile_type != "Round" else None,
                            "n_h_face": int(n_h_face) if pile_type != "Round" else None,
                        },
                        "summary": {
                            "governing_case": str(governing["Load Case"]) if governing is not None else "-",
                            "overall_pu_max": float(overall_pu_max),
                            "overall_pu_min": float(overall_pu_min),
                            "overall_mx": float(overall_mx),
                            "overall_my": float(overall_my),
                            "overall_v": float(overall_v),
                            "overall_m_resultant_envelope": float(overall_m),
                            "design_demand_basis": design_demand_basis,
                            "shear_design_case": shear_design_case,
                            "shear_design_pu_kN": float(shear_design_pu),
                            "shear_design_v_kN": float(shear_design_v),
                            "shear_design_m_kN_m": float(shear_design_m),
                            "shear_design_note": shear_design_note,
                            "max_pmm_util": float(max_pmm_util),
                            "max_tension_util": float(max_tension_util),
                            "max_util": float(max_util),
                            "overall_status": "OK" if max_util <= 1.0 else "NG",
                            "as_provided_mm2": float(bar_df["As_mm2"].sum()),
                            "phi_tn_kN": float(phi_tn_kN),
                            "recommended_tie_spacing_mm": float(shear_summary["s_rec_mm"]),
                            "provided_tie_spacing_ok": bool(tie_ok),
                        },
                        "load_cases": active_cases.copy(),
                        "demand_df": demand_df.copy(),
                        "profile_df": profile_df.copy(),
                        "sensitivity_df": pd.DataFrame(),
                        "bar_df": bar_df.copy(),
                        "pmm_df": pmm_df.copy(),
                        "mx_curve": mx_curve.copy(),
                        "my_curve": my_curve.copy(),
                        "shear_summary": dict(shear_summary),
                    }
                    latest_report["qa_checklist"] = build_pile_design_qa_checklist(latest_report)
                    latest_report["final_review_checklist"] = build_final_report_review_checklist(latest_report)
                    st.session_state["latest_pile_design_report"] = latest_report

                    st.subheader("Design Envelope")
                    env1, env2, env3, env4, env5 = st.columns(5)
                    env1.metric("Max Pu [kN]", f"{overall_pu_max:,.1f}")
                    env2.metric("Min Pu [kN]", f"{overall_pu_min:,.1f}")
                    env3.metric("Max |Mux| [kN-m]", f"{overall_mx:,.1f}")
                    env4.metric("Max |Muy| [kN-m]", f"{overall_my:,.1f}")
                    env5.metric("Max Overall Util.", f"{max_util:,.2f}", "OK" if max_util <= 1.0 else "Increase steel / check uplift")
                    st.caption(
                        f"Preliminary shear/tie design basis: {design_demand_basis}. "
                        f"Demand source = {shear_design_case}; Pu = {shear_design_pu:,.1f} kN, "
                        f"V = {shear_design_v:,.1f} kN, M = {shear_design_m:,.1f} kN-m."
                    )

                    left_design, right_design = st.columns([1.05, 1.15], gap="large")
                    with left_design:
                        st.subheader("Pile Section with Reinforcement")
                        st.plotly_chart(
                            pile_rebar_section_figure(
                                pile_type, D, B, H, cover_mm, tie_bar, main_bar,
                                n_round_bars=n_main_bars, n_b_face=n_b_face, n_h_face=n_h_face
                            ),
                            use_container_width=True
                        )
                        section_info = [
                            ("Main bar", f"{len(bar_df)} {main_bar}", f"fy = {get_rebar_fy_mpa(main_bar):.0f} MPa"),
                            ("Provided As", f"{bar_df['As_mm2'].sum():,.0f} mm2", f"{bar_df['As_mm2'].sum() / 100.0:,.1f} cm2"),
                            ("Transverse system", transverse_system, f"{tie_bar} @ {tie_spacing_mm:.0f} mm"),
                            ("PMM interaction", "OK" if max_pmm_util <= 1.0 else "NG", f"max PMM U = {max_pmm_util:.3f}"),
                            ("Uplift/tension", "OK" if max_tension_util <= 1.0 else "NG", f"φTn = {phi_tn_kN:,.1f} kN; max tension U = {max_tension_util:.3f}"),
                            ("Overall structural", "OK" if max_util <= 1.0 else "NG", f"governing = {governing['Load Case'] if governing is not None else '-'}"),
                            ("Recommended tie spacing", f"{shear_summary['s_rec_mm']:.0f} mm", "preliminary shear/confinement check"),
                            ("Shear/tie demand basis", shear_design_case, shear_design_note),
                        ]
                        st.table(pd.DataFrame(section_info, columns=["Item", "Value", "Note"]))
                        if max_pmm_util > 1.0:
                            st.warning("PMM utilization exceeds 1.0. Increase main bar size/quantity or revise the section.")
                        if max_tension_util > 1.0:
                            st.warning("Uplift/tension utilization exceeds 1.0. Increase longitudinal steel or revise the uplift load path.")
                        if overall_pu_min < 0.0:
                            st.info("At least one load case has Pu < 0 (tension/uplift). The app now checks φTn = 0.90·ΣAsfy separately, but pile-cap anchorage and geotechnical uplift must still be verified outside this PMM plot.")
                        if not tie_ok:
                            st.warning("Provided tie spacing is larger than the preliminary recommended spacing.")

                    with right_design:
                        st.subheader("Load Case Results")
                        st.dataframe(
                            demand_df.drop(columns=["Case Plot Label"], errors="ignore").style.format({
                                "Mhead X [kN-m]": "{:,.1f}",
                                "Mhead Y [kN-m]": "{:,.1f}",
                                "Max Pu [kN]": "{:,.1f}",
                                "Min Pu [kN]": "{:,.1f}",
                                "Max |Mux| [kN-m]": "{:,.1f}",
                                "z @ Mux [m]": "{:.2f}",
                                "Max |Muy| [kN-m]": "{:,.1f}",
                                "z @ Muy [m]": "{:.2f}",
                                "Max M resultant [kN-m]": "{:,.1f}",
                                "z @ M resultant [m]": "{:.2f}",
                                "Max |V| [kN]": "{:,.1f}",
                                "z @ V [m]": "{:.2f}",
                                "PMM Util.": "{:.3f}",
                                "Tension Util.": "{:.3f}",
                                "Overall Util.": "{:.3f}",
                                "Linear PMM Util.": "{:.3f}",
                                "z @ PMM [m]": "{:.2f}",
                                "PMM Mux [kN-m]": "{:,.1f}",
                                "PMM Muy [kN-m]": "{:,.1f}",
                                "PMM M resultant [kN-m]": "{:,.1f}",
                                "PMM radial cap [kN-m]": "{:,.1f}",
                                "PMM cap Mux [kN-m]": "{:,.1f}",
                                "PMM cap Muy [kN-m]": "{:,.1f}",
                                "Mx cap @ Pu [kN-m]": "{:,.1f}",
                                "My cap @ Pu [kN-m]": "{:,.1f}",
                                "φTn tension cap [kN]": "{:,.1f}",
                            }),
                            use_container_width=True,
                            hide_index=True,
                            height=260
                        )
                        st.markdown(
                            f"""
                            - **Provided main steel:** `{bar_df['As_mm2'].sum():,.0f} mm2`
                            - **Maximum shear resultant:** `{overall_v:,.1f} kN`
                            - **Recommended tie spacing:** `{shear_summary['s_rec_mm']:.0f} mm`
                            - **PMM check:** 3D surface radial utilization from the ACI-style strain-compatible φPMM surface.
                            - **Uplift check:** φTn = `0.90·ΣAsfy = {phi_tn_kN:,.1f} kN`; Overall U = max(PMM U, Tension U).
                            """
                        )

                    if run_head_sensitivity:
                        st.subheader("Head Boundary Sensitivity Check")
                        st.caption(
                            "This comparison brackets the pile response for uncertain pile-cap rotational restraint. "
                            "For final design, review whether the governing demand is controlled by free-head displacement "
                            "or fixed/semi-fixed head bending moment."
                        )

                        sensitivity_cases = []
                        if sensitivity_scope == "All active load cases":
                            sensitivity_cases = [case for _, case in active_cases.iterrows()]
                            if len(sensitivity_cases) > 30:
                                st.warning(
                                    "Sensitivity is running for more than 30 active cases. "
                                    "Consider using the governing-case scope to keep the table readable."
                                )
                        else:
                            if governing is not None and not active_cases.empty:
                                try:
                                    gov_case_idx = int(governing.get("Case No.", 1)) - 1
                                    gov_case_idx = min(max(gov_case_idx, 0), len(active_cases) - 1)
                                    sensitivity_cases = [active_cases.iloc[gov_case_idx]]
                                except Exception:
                                    sensitivity_cases = [active_cases.iloc[0]]

                        sensitivity_scenarios = [
                            ("Free Head", "Free Head / Shear Only", 0.0),
                            ("Kθ = 10,000", "Rotational Spring", 1.0e4),
                            ("Kθ = 100,000", "Rotational Spring", 1.0e5),
                            ("Kθ = 1,000,000", "Rotational Spring", 1.0e6),
                            ("Fixed Head", "Fixed Head (theta = 0)", 0.0),
                        ]

                        sensitivity_rows = []
                        sensitivity_profiles = []
                        sensitivity_error = None
                        for case in sensitivity_cases:
                            lc = str(case["Load Case"])
                            pu_kN = float(case["Pu [kN]"])
                            hx_kN = float(case["Hx [kN]"])
                            hy_kN = float(case["Hy [kN]"])
                            for scenario_label, scenario_condition, scenario_ktheta in sensitivity_scenarios:
                                try:
                                    s_disp_x, s_theta_x, _s_rx, s_shear_x, s_moment_y, s_mhead_y = solve_pile_lateral_response(
                                        depths, spring_k_x, EI_x_loading,
                                        head_shear=hx_kN, head_moment=0.0,
                                        head_condition=scenario_condition,
                                        rotational_stiffness=scenario_ktheta,
                                    )
                                    s_disp_y, s_theta_y, _s_ry, s_shear_y, s_moment_x, s_mhead_x = solve_pile_lateral_response(
                                        depths, spring_k_y, EI_y_loading,
                                        head_shear=hy_kN, head_moment=0.0,
                                        head_condition=scenario_condition,
                                        rotational_stiffness=scenario_ktheta,
                                    )
                                except Exception as exc:
                                    sensitivity_error = f"{lc} / {scenario_label}: {exc}"
                                    break

                                s_disp_res_mm = np.sqrt(s_disp_x**2 + s_disp_y**2) * 1000.0
                                s_shear_res = np.sqrt(s_shear_x**2 + s_shear_y**2)
                                s_moment_res = np.sqrt(s_moment_x**2 + s_moment_y**2)
                                im = int(np.argmax(np.abs(s_moment_res))) if len(s_moment_res) else 0
                                idisp = int(np.argmax(np.abs(s_disp_res_mm))) if len(s_disp_res_mm) else 0
                                iv = int(np.argmax(np.abs(s_shear_res))) if len(s_shear_res) else 0

                                if pmm_finite.empty:
                                    s_util_profile = np.full(len(depths), np.inf, dtype=float)
                                else:
                                    pu_use, pu_out_status = clamp_pu_to_pmm_range(pu_kN, pmm_p_min, pmm_p_max, pmm_p_tol)
                                    if pu_out_status:
                                        s_slice_for_case = pd.DataFrame()
                                    else:
                                        cache_key = round(float(pu_use), 6)
                                        if cache_key not in pmm_slice_cache:
                                            pmm_slice_cache[cache_key] = pmm_slice_at_p(pmm_finite, pu_use)
                                        s_slice_for_case = pmm_slice_cache[cache_key]
                                    s_checks = [
                                        pmm_utilization_from_slice(s_slice_for_case, pu_use, mx, my, pu_out_status)
                                        for mx, my in zip(s_moment_x, s_moment_y)
                                    ]
                                    s_util_profile = np.asarray([chk["utilization"] for chk in s_checks], dtype=float)
                                    s_util_profile = np.where(np.isfinite(s_util_profile), s_util_profile, np.inf)

                                s_tension_util, _s_tension_status = tension_utilization_for_pu(pu_kN, phi_tn_kN)
                                s_pmm_util = float(np.max(s_util_profile)) if len(s_util_profile) else np.inf
                                s_overall_util = max(s_pmm_util, float(s_tension_util))
                                sensitivity_rows.append({
                                    "Load Case": lc,
                                    "Scenario": scenario_label,
                                    "Head Condition": scenario_condition,
                                    "Kθ [kN-m/rad]": float(scenario_ktheta),
                                    "Pu [kN]": pu_kN,
                                    "Hx [kN]": hx_kN,
                                    "Hy [kN]": hy_kN,
                                    "Head disp. [mm]": float(s_disp_res_mm[0]) if len(s_disp_res_mm) else 0.0,
                                    "Max disp. [mm]": float(np.max(np.abs(s_disp_res_mm))) if len(s_disp_res_mm) else 0.0,
                                    "z @ max disp. [m]": float(depths[idisp]) if len(depths) else 0.0,
                                    "Mhead X [kN-m]": float(s_mhead_x),
                                    "Mhead Y [kN-m]": float(s_mhead_y),
                                    "Mhead resultant [kN-m]": float(np.hypot(s_mhead_x, s_mhead_y)),
                                    "Max |Mux| [kN-m]": float(np.max(np.abs(s_moment_x))) if len(s_moment_x) else 0.0,
                                    "Max |Muy| [kN-m]": float(np.max(np.abs(s_moment_y))) if len(s_moment_y) else 0.0,
                                    "Max |M| [kN-m]": float(np.max(np.abs(s_moment_res))) if len(s_moment_res) else 0.0,
                                    "z @ max M [m]": float(depths[im]) if len(depths) else 0.0,
                                    "Max |V| [kN]": float(np.max(np.abs(s_shear_res))) if len(s_shear_res) else 0.0,
                                    "z @ max V [m]": float(depths[iv]) if len(depths) else 0.0,
                                    "PMM Util.": s_pmm_util,
                                    "Tension Util.": float(s_tension_util),
                                    "Overall Util.": float(s_overall_util),
                                    "Status": "OK" if s_overall_util <= 1.0 else "NG",
                                })

                                if sensitivity_scope == "Governing case from current design":
                                    sensitivity_profiles.append(pd.DataFrame({
                                        "Scenario": scenario_label,
                                        "Depth [m]": depths,
                                        "M resultant [kN-m]": s_moment_res,
                                        "Disp resultant [mm]": s_disp_res_mm,
                                    }))
                            if sensitivity_error:
                                break

                        if sensitivity_error:
                            st.error(f"Head-boundary sensitivity could not run: {sensitivity_error}")
                        elif sensitivity_rows:
                            sensitivity_df = pd.DataFrame(sensitivity_rows)
                            if "latest_pile_design_report" in st.session_state:
                                st.session_state["latest_pile_design_report"]["sensitivity_df"] = sensitivity_df.copy()
                                st.session_state["latest_pile_design_report"]["qa_checklist"] = build_pile_design_qa_checklist(st.session_state["latest_pile_design_report"])
                            if sensitivity_scope == "All active load cases":
                                envelope_df = (
                                    sensitivity_df
                                    .groupby(["Scenario", "Head Condition", "Kθ [kN-m/rad]"], as_index=False)
                                    .agg({
                                        "Head disp. [mm]": "max",
                                        "Max disp. [mm]": "max",
                                        "Mhead resultant [kN-m]": "max",
                                        "Max |Mux| [kN-m]": "max",
                                        "Max |Muy| [kN-m]": "max",
                                        "Max |M| [kN-m]": "max",
                                        "Max |V| [kN]": "max",
                                        "PMM Util.": "max",
                                        "Tension Util.": "max",
                                        "Overall Util.": "max",
                                    })
                                )
                                envelope_df["Status"] = np.where(envelope_df["Overall Util."] <= 1.0, "OK", "NG")
                                st.markdown("**Sensitivity envelope across all active load cases**")
                                st.dataframe(
                                    envelope_df.style.format({
                                        "Kθ [kN-m/rad]": "{:,.0f}",
                                        "Head disp. [mm]": "{:,.2f}",
                                        "Max disp. [mm]": "{:,.2f}",
                                        "Mhead resultant [kN-m]": "{:,.1f}",
                                        "Max |Mux| [kN-m]": "{:,.1f}",
                                        "Max |Muy| [kN-m]": "{:,.1f}",
                                        "Max |M| [kN-m]": "{:,.1f}",
                                        "Max |V| [kN]": "{:,.1f}",
                                        "PMM Util.": "{:.3f}",
                                        "Tension Util.": "{:.3f}",
                                        "Overall Util.": "{:.3f}",
                                    }),
                                    use_container_width=True,
                                    hide_index=True,
                                )
                                with st.expander("Detailed sensitivity by load case", expanded=False):
                                    st.dataframe(
                                        sensitivity_df.style.format({
                                            "Kθ [kN-m/rad]": "{:,.0f}",
                                            "Pu [kN]": "{:,.1f}",
                                            "Hx [kN]": "{:,.1f}",
                                            "Hy [kN]": "{:,.1f}",
                                            "Head disp. [mm]": "{:,.2f}",
                                            "Max disp. [mm]": "{:,.2f}",
                                            "z @ max disp. [m]": "{:.2f}",
                                            "Mhead X [kN-m]": "{:,.1f}",
                                            "Mhead Y [kN-m]": "{:,.1f}",
                                            "Mhead resultant [kN-m]": "{:,.1f}",
                                            "Max |Mux| [kN-m]": "{:,.1f}",
                                            "Max |Muy| [kN-m]": "{:,.1f}",
                                            "Max |M| [kN-m]": "{:,.1f}",
                                            "z @ max M [m]": "{:.2f}",
                                            "Max |V| [kN]": "{:,.1f}",
                                            "z @ max V [m]": "{:.2f}",
                                            "PMM Util.": "{:.3f}",
                                            "Tension Util.": "{:.3f}",
                                            "Overall Util.": "{:.3f}",
                                        }),
                                        use_container_width=True,
                                        hide_index=True,
                                    )
                            else:
                                st.dataframe(
                                    sensitivity_df.style.format({
                                        "Kθ [kN-m/rad]": "{:,.0f}",
                                        "Pu [kN]": "{:,.1f}",
                                        "Hx [kN]": "{:,.1f}",
                                        "Hy [kN]": "{:,.1f}",
                                        "Head disp. [mm]": "{:,.2f}",
                                        "Max disp. [mm]": "{:,.2f}",
                                        "z @ max disp. [m]": "{:.2f}",
                                        "Mhead X [kN-m]": "{:,.1f}",
                                        "Mhead Y [kN-m]": "{:,.1f}",
                                        "Mhead resultant [kN-m]": "{:,.1f}",
                                        "Max |Mux| [kN-m]": "{:,.1f}",
                                        "Max |Muy| [kN-m]": "{:,.1f}",
                                        "Max |M| [kN-m]": "{:,.1f}",
                                        "z @ max M [m]": "{:.2f}",
                                        "Max |V| [kN]": "{:,.1f}",
                                        "z @ max V [m]": "{:.2f}",
                                        "PMM Util.": "{:.3f}",
                                        "Tension Util.": "{:.3f}",
                                        "Overall Util.": "{:.3f}",
                                    }),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                                if sensitivity_profiles:
                                    sens_profile_df = pd.concat(sensitivity_profiles, ignore_index=True)
                                    cs1, cs2 = st.columns(2)
                                    fig_m_sens = go.Figure()
                                    fig_d_sens = go.Figure()
                                    for scenario, grp in sens_profile_df.groupby("Scenario", sort=False):
                                        grp = grp.sort_values("Depth [m]")
                                        fig_m_sens.add_trace(go.Scatter(
                                            x=grp["M resultant [kN-m]"],
                                            y=grp["Depth [m]"],
                                            mode="lines+markers",
                                            name=str(scenario),
                                        ))
                                        fig_d_sens.add_trace(go.Scatter(
                                            x=grp["Disp resultant [mm]"],
                                            y=grp["Depth [m]"],
                                            mode="lines+markers",
                                            name=str(scenario),
                                        ))
                                    fig_m_sens.update_layout(
                                        height=360,
                                        title="Sensitivity: Moment Resultant",
                                        yaxis=dict(autorange="reversed", title="Depth [m]"),
                                        xaxis=dict(title="M resultant [kN-m]", zeroline=True),
                                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                                        margin=dict(l=10, r=10, t=45, b=10),
                                    )
                                    fig_d_sens.update_layout(
                                        height=360,
                                        title="Sensitivity: Displacement Resultant",
                                        yaxis=dict(autorange="reversed", title="Depth [m]"),
                                        xaxis=dict(title="Displacement [mm]", zeroline=True),
                                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                                        margin=dict(l=10, r=10, t=45, b=10),
                                    )
                                    cs1.plotly_chart(fig_m_sens, use_container_width=True)
                                    cs2.plotly_chart(fig_d_sens, use_container_width=True)

                            st.info(
                                "Interpretation: Free Head generally bounds larger rotation/displacement behavior, "
                                "while Fixed Head generally increases head-restraint moment. Use the selected design condition "
                                "only after confirming it is compatible with the actual pile-cap stiffness/detailing."
                            )

                    st.subheader("Force Diagrams Along Pile")
                    force_case_labels = demand_df["Case Plot Label"].astype(str).tolist()
                    governing_case_label = str(governing["Case Plot Label"]) if governing is not None else (force_case_labels[0] if force_case_labels else "")
                    plot_mode = st.radio(
                        "Force diagram display",
                        ["Governing case only", "Selected case only", "All active cases"],
                        horizontal=True,
                        index=0,
                        help="Plotting all cases can be slow and unreadable when many load cases are imported."
                    )
                    if plot_mode == "Selected case only":
                        selected_force_case = st.selectbox(
                            "Force diagram load case",
                            force_case_labels,
                            index=force_case_labels.index(governing_case_label) if governing_case_label in force_case_labels else 0,
                        )
                        plot_profile_df = profile_df[profile_df["Case Plot Label"].astype(str) == str(selected_force_case)].copy()
                    elif plot_mode == "All active cases":
                        plot_profile_df = profile_df.copy()
                        if len(force_case_labels) > 20:
                            st.warning("Many load cases are selected for plotting. Switch back to governing/selected mode if the page feels slow.")
                    else:
                        plot_profile_df = profile_df[profile_df["Case Plot Label"].astype(str) == str(governing_case_label)].copy()

                    symbols = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon", "triangle-down", "pentagon"]
                    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]

                    def _force_figure(x_col, title, x_title):
                        fig = go.Figure()
                        for i, (lc, grp) in enumerate(plot_profile_df.groupby("Case Plot Label", sort=False)):
                            grp = grp.sort_values("Depth [m]").copy()
                            fig.add_trace(go.Scatter(
                                x=grp[x_col],
                                y=grp["Depth [m]"],
                                mode="lines+markers",
                                name=str(lc),
                                line=dict(color=colors[i % len(colors)], width=2),
                                marker=dict(symbol=symbols[i % len(symbols)], size=7),
                                connectgaps=False,
                            ))
                        fig.update_layout(
                            height=410,
                            margin=dict(l=10, r=10, t=45, b=10),
                            title=dict(text=title, font=dict(size=14)),
                            yaxis=dict(autorange="reversed", title="Depth [m]"),
                            xaxis=dict(title=x_title, zeroline=True, zerolinecolor="rgba(60,60,60,0.45)"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        return fig

                    fd1, fd2 = st.columns(2)
                    fd3, fd4 = st.columns(2)
                    fd1.plotly_chart(_force_figure("Pu [kN]", "Axial Force P", "Compression P [kN]"), use_container_width=True)
                    fd2.plotly_chart(_force_figure("Mux [kN-m]", "Bending Moment About X", "Mux [kN-m]"), use_container_width=True)
                    fd3.plotly_chart(_force_figure("Muy [kN-m]", "Bending Moment About Y", "Muy [kN-m]"), use_container_width=True)
                    fd4.plotly_chart(_force_figure("V resultant [kN]", "Shear Force Resultant", "V = sqrt(Vx^2 + Vy^2) [kN]"), use_container_width=True)

                    st.subheader("Displacement Diagrams Along Pile")
                    st.caption(
                        "Displacements are plotted from the same solved pile-response profiles and load-case selection used above. "
                        "Positive/negative X and Y signs follow the applied head shear directions; resultant displacement is shown as magnitude."
                    )

                    disp_plot_df = plot_profile_df.copy()
                    if not disp_plot_df.empty:
                        disp_plot_df["Disp resultant [mm]"] = np.sqrt(
                            disp_plot_df["Disp X [mm]"].astype(float) ** 2
                            + disp_plot_df["Disp Y [mm]"].astype(float) ** 2
                        )
                        disp_summary_rows = []
                        for lc, grp in disp_plot_df.groupby("Case Plot Label", sort=False):
                            grp = grp.sort_values("Depth [m]").copy()
                            if grp.empty:
                                continue
                            ix = int(np.argmax(np.abs(grp["Disp X [mm]"].to_numpy(dtype=float))))
                            iy = int(np.argmax(np.abs(grp["Disp Y [mm]"].to_numpy(dtype=float))))
                            ir = int(np.argmax(grp["Disp resultant [mm]"].to_numpy(dtype=float)))
                            disp_summary_rows.append({
                                "Load Case": str(lc),
                                "Head X disp. [mm]": float(grp["Disp X [mm]"].iloc[0]),
                                "Head Y disp. [mm]": float(grp["Disp Y [mm]"].iloc[0]),
                                "Max |X disp.| [mm]": float(abs(grp["Disp X [mm]"].iloc[ix])),
                                "z @ X disp. [m]": float(grp["Depth [m]"].iloc[ix]),
                                "Max |Y disp.| [mm]": float(abs(grp["Disp Y [mm]"].iloc[iy])),
                                "z @ Y disp. [m]": float(grp["Depth [m]"].iloc[iy]),
                                "Max resultant disp. [mm]": float(grp["Disp resultant [mm]"].iloc[ir]),
                                "z @ resultant [m]": float(grp["Depth [m]"].iloc[ir]),
                            })

                        def _disp_figure(x_col, title, x_title, signed=True):
                            fig = go.Figure()
                            for i, (lc, grp) in enumerate(disp_plot_df.groupby("Case Plot Label", sort=False)):
                                grp = grp.sort_values("Depth [m]").copy()
                                fig.add_trace(go.Scatter(
                                    x=grp[x_col],
                                    y=grp["Depth [m]"],
                                    mode="lines+markers",
                                    name=str(lc),
                                    line=dict(color=colors[i % len(colors)], width=2),
                                    marker=dict(symbol=symbols[i % len(symbols)], size=7),
                                    connectgaps=False,
                                ))
                            fig.update_layout(
                                height=410,
                                margin=dict(l=10, r=10, t=45, b=10),
                                title=dict(text=title, font=dict(size=14)),
                                yaxis=dict(autorange="reversed", title="Depth [m]"),
                                xaxis=dict(
                                    title=x_title,
                                    zeroline=True,
                                    zerolinecolor="rgba(60,60,60,0.45)",
                                    rangemode=None if signed else "tozero",
                                ),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            )
                            return fig

                        dsum_df = pd.DataFrame(disp_summary_rows)
                        if not dsum_df.empty:
                            st.dataframe(
                                dsum_df.style.format({
                                    "Head X disp. [mm]": "{:,.2f}",
                                    "Head Y disp. [mm]": "{:,.2f}",
                                    "Max |X disp.| [mm]": "{:,.2f}",
                                    "z @ X disp. [m]": "{:.2f}",
                                    "Max |Y disp.| [mm]": "{:,.2f}",
                                    "z @ Y disp. [m]": "{:.2f}",
                                    "Max resultant disp. [mm]": "{:,.2f}",
                                    "z @ resultant [m]": "{:.2f}",
                                }),
                                use_container_width=True,
                                hide_index=True,
                                height=min(260, 70 + 36 * len(dsum_df)),
                            )

                        dd1, dd2 = st.columns(2)
                        dd3, dd4 = st.columns(2)
                        dd1.plotly_chart(_disp_figure("Disp X [mm]", "Lateral Displacement in X", "Ux [mm]"), use_container_width=True)
                        dd2.plotly_chart(_disp_figure("Disp Y [mm]", "Lateral Displacement in Y", "Uy [mm]"), use_container_width=True)
                        dd3.plotly_chart(_disp_figure("Disp resultant [mm]", "Displacement Resultant", "sqrt(Ux² + Uy²) [mm]", signed=False), use_container_width=True)

                        fig_path = go.Figure()
                        for i, (lc, grp) in enumerate(disp_plot_df.groupby("Case Plot Label", sort=False)):
                            grp = grp.sort_values("Depth [m]").copy()
                            fig_path.add_trace(go.Scatter(
                                x=grp["Disp X [mm]"],
                                y=grp["Disp Y [mm]"],
                                mode="lines+markers",
                                name=str(lc),
                                line=dict(color=colors[i % len(colors)], width=2),
                                marker=dict(symbol=symbols[i % len(symbols)], size=7),
                                connectgaps=False,
                            ))
                        fig_path.update_layout(
                            height=410,
                            margin=dict(l=10, r=10, t=45, b=10),
                            title=dict(text="Plan Displacement Path Ux-Uy", font=dict(size=14)),
                            xaxis=dict(title="Ux [mm]", zeroline=True, zerolinecolor="rgba(60,60,60,0.45)"),
                            yaxis=dict(title="Uy [mm]", zeroline=True, zerolinecolor="rgba(60,60,60,0.45)", scaleanchor="x", scaleratio=1),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        dd4.plotly_chart(fig_path, use_container_width=True)
                    else:
                        st.info("No displacement profile is available for the selected force-diagram mode.")

                    st.subheader("ACI φPMM Design Strength Interaction")

                    ag_mm2 = Ap * 1e6
                    as_total_mm2 = float(bar_df["As_mm2"].sum())
                    rho_total = as_total_mm2 / max(ag_mm2, 1e-9)
                    rho_min_aci = ACI_MIN_LONG_RATIO
                    rho_max_aci = ACI_MAX_LONG_RATIO
                    as_min_aci_mm2 = rho_min_aci * ag_mm2
                    as_max_aci_mm2 = rho_max_aci * ag_mm2
                    min_ok = as_total_mm2 >= as_min_aci_mm2
                    max_ok = as_total_mm2 <= as_max_aci_mm2
                    aci_ratio_ok = min_ok and max_ok
                    if pile_type == "Round":
                        face_note = "Round pile: face-by-face rectangular distribution check is not applicable."
                    else:
                        as_b_face = int(n_b_face) * get_rebar_area_mm2(main_bar)
                        as_h_face = int(n_h_face) * get_rebar_area_mm2(main_bar)
                        face_req = as_min_aci_mm2 / 2.0
                        face_note = (
                            f"Required each main face = {face_req:,.0f} mm2; "
                            f"B faces = {as_b_face:,.0f} mm2 ({'OK' if as_b_face >= face_req else 'NG'}), "
                            f"H faces = {as_h_face:,.0f} mm2 ({'OK' if as_h_face >= face_req else 'NG'})."
                        )

                    st.markdown(
                        f"""
                        <div style="border:1px solid #c8d5e6;border-radius:6px;padding:12px 14px;background:#f8fbff;margin-bottom:10px">
                            <div style="font-weight:700;margin-bottom:6px">Minimum Reinforcement Check</div>
                            <div style="font-size:13px;line-height:1.55">
                                ACI 318-19 10.6.1.1 longitudinal minimum for nonprestressed compression members.<br>
                                Required rho range = {rho_min_aci*100:.3f}% to {rho_max_aci*100:.1f}%; provided rho = {rho_total*100:.3f}%<br>
                                As,min total = {as_min_aci_mm2:,.0f} mm2, As provided total = {as_total_mm2:,.0f} mm2
                                <b style="color:{'#087f23' if aci_ratio_ok else '#c4123f'}">({'OK' if aci_ratio_ok else 'NG'})</b><br>
                                {face_note}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    mx_env = interaction_curve_envelope(mx_curve)
                    my_env = interaction_curve_envelope(my_curve)

                    fig_uni = go.Figure()
                    fig_uni.add_trace(go.Scatter(
                        x=my_env["phiM [kN-m]"],
                        y=my_env["phiPn [kN]"],
                        mode="lines",
                        line=dict(color="#c4123f", width=4, dash="dash"),
                        name="about y"
                    ))
                    fig_uni.add_trace(go.Scatter(
                        x=mx_env["phiM [kN-m]"],
                        y=mx_env["phiPn [kN]"],
                        mode="lines",
                        line=dict(color="#2356d7", width=4),
                        name="about x"
                    ))
                    fig_uni.add_trace(go.Scatter(
                        x=demand_df["Max |Mux| [kN-m]"],
                        y=demand_df["Max Pu [kN]"],
                        mode="markers+text",
                        marker=dict(symbol="x", size=13, color="#2356d7", line=dict(width=3)),
                        text=demand_df["Load Case"],
                        textposition="bottom center",
                        name="Pu, Mux"
                    ))
                    fig_uni.add_trace(go.Scatter(
                        x=demand_df["Max |Muy| [kN-m]"],
                        y=demand_df["Max Pu [kN]"],
                        mode="markers+text",
                        marker=dict(symbol="x", size=13, color="#c4123f", line=dict(width=3)),
                        text=demand_df["Load Case"],
                        textposition="top center",
                        name="Pu, Muy"
                    ))
                    fig_uni.update_layout(
                        height=500,
                        title=dict(text="Uniaxial φPMM Design Strength Curves", font=dict(size=18)),
                        margin=dict(l=10, r=10, t=70, b=10),
                        xaxis=dict(title="φMn [kN-m]", zeroline=True, zerolinecolor="#758195", gridcolor="#dbe2ec"),
                        yaxis=dict(title="φPn [kN]", zeroline=True, zerolinecolor="#758195", gridcolor="#dbe2ec"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="center", x=0.5),
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_uni, use_container_width=True)
                    if pile_type == "Round":
                        st.caption("For round piles, the about-x and about-y interaction curves are nearly identical, so the dashed red curve can overlap the blue curve.")

                    governing_index = int(demand_df["Overall Util."].idxmax()) if not demand_df.empty else 0
                    slice_case = st.selectbox(
                        "φPMM slice load case",
                        demand_df["Case Plot Label"].astype(str).tolist(),
                        index=governing_index,
                        help="The Mux-Muy slice is drawn at the selected load case Pu."
                    )
                    slice_row = demand_df[demand_df["Case Plot Label"].astype(str) == str(slice_case)].iloc[0]
                    slice_case_name = str(slice_row["Load Case"])
                    slice_pu = float(slice_row["Max Pu [kN]"])
                    slice_df = pmm_slice_at_p(pmm_df, slice_pu)
                    demand_mx = float(slice_row["PMM Mux [kN-m]"])
                    demand_my = float(slice_row["PMM Muy [kN-m]"])

                    fig_slice = go.Figure()
                    if not slice_df.empty:
                        fig_slice.add_trace(go.Scatter(
                            x=slice_df["phiMnx [kN-m]"],
                            y=slice_df["phiMny [kN-m]"],
                            mode="lines",
                            fill="toself",
                            fillcolor="rgba(0, 150, 220, 0.12)",
                            line=dict(color="#008fd3", width=3),
                            name="φPMM design slice"
                        ))
                    fig_slice.add_trace(go.Scatter(
                        x=[0.0, demand_mx],
                        y=[0.0, demand_my],
                        mode="lines",
                        line=dict(color="#1b6b6b", width=2),
                        name="demand vector"
                    ))
                    fig_slice.add_trace(go.Scatter(
                        x=[demand_mx],
                        y=[demand_my],
                        mode="markers+text",
                        marker=dict(symbol="x", color="#1b6b6b", size=13, line=dict(width=3)),
                        text=[f"{slice_case_name}<br>Overall U={slice_row['Overall Util.']:.3f}<br>PMM U={slice_row['PMM Util.']:.3f}"],
                        textposition="bottom right",
                        name="demand"
                    ))
                    fig_slice.update_layout(
                        height=500,
                        title=dict(text=f"φPMM Mux-Muy Design Strength Slice at Pu = {slice_pu:,.0f} kN", font=dict(size=15)),
                        margin=dict(l=10, r=10, t=60, b=10),
                        xaxis=dict(title="φMnx [kN-m]", zeroline=True, zerolinecolor="#3f4654", gridcolor="#e2e8f0"),
                        yaxis=dict(title="φMny [kN-m]", zeroline=True, zerolinecolor="#3f4654", gridcolor="#e2e8f0", scaleanchor="x", scaleratio=1),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_slice, use_container_width=True)
                    st.caption("The slice boundary is φ-reduced design strength (φMnx, φMny) at the selected Pu; the marker/vector is the demand point.")

                    show_3d_pmm = st.checkbox(
                        "Show 3D φPMM design strength surface",
                        value=False,
                        help="The 3D φPMM plot is useful for review but can be heavier to render. The displayed aspect ratio is adjusted for readability."
                    )
                    if show_3d_pmm:
                        fig_pmm = go.Figure()
                        surface_grid = pmm_polar_surface_grid(pmm_df)
                        if surface_grid is not None:
                            sx, sy, sz = surface_grid
                            fig_pmm.add_trace(go.Surface(
                                x=sx,
                                y=sy,
                                z=sz,
                                opacity=0.42,
                                colorscale=[[0, "#cfe7f6"], [1, "#5fa7dc"]],
                                showscale=False,
                                name="φPMM design surface",
                                contours=dict(
                                    x=dict(show=False),
                                    y=dict(show=False),
                                    z=dict(show=True, color="#7aaed2", width=1),
                                ),
                                lighting=dict(ambient=0.65, diffuse=0.55, roughness=0.75),
                            ))
                        if not slice_df.empty:
                            fig_pmm.add_trace(go.Scatter3d(
                                x=slice_df["phiMnx [kN-m]"],
                                y=slice_df["phiMny [kN-m]"],
                                z=np.full(len(slice_df), slice_pu),
                                mode="lines",
                                line=dict(color="#008fd3", width=5),
                                name="current Pu slice"
                            ))
                        fig_pmm.add_trace(go.Scatter3d(
                            x=[0.0, demand_mx],
                            y=[0.0, demand_my],
                            z=[slice_pu, slice_pu],
                            mode="lines",
                            line=dict(color="#1b6b6b", width=5),
                            name="demand vector"
                        ))
                        if phi_tn_kN > 0.0:
                            fig_pmm.add_trace(go.Scatter3d(
                                x=[0.0],
                                y=[0.0],
                                z=[-phi_tn_kN],
                                mode="markers+text",
                                marker=dict(size=7, color="#b45309", symbol="diamond", line=dict(color="white", width=1)),
                                text=["pure tension φTn"],
                                textposition="bottom center",
                                name="pure tension φTn"
                            ))
                        load_point_colors = [
                            "#c4123f" if float(u) > 1.0 else ("#b45309" if str(sign).startswith("Tension") else "#1b6b6b")
                            for u, sign in zip(demand_df["Overall Util."], demand_df["Pu Sign"])
                        ]
                        fig_pmm.add_trace(go.Scatter3d(
                            x=demand_df["PMM Mux [kN-m]"],
                            y=demand_df["PMM Muy [kN-m]"],
                            z=demand_df["Max Pu [kN]"],
                            mode="markers+text",
                            marker=dict(
                                size=6,
                                color=load_point_colors,
                                line=dict(color="white", width=1),
                            ),
                            text=demand_df["Load Case"],
                            textposition="top center",
                            customdata=np.stack([
                                demand_df["Overall Util."].to_numpy(dtype=float),
                                demand_df["PMM Util."].to_numpy(dtype=float),
                                demand_df["Tension Util."].to_numpy(dtype=float),
                                demand_df["PMM Mux [kN-m]"].to_numpy(dtype=float),
                                demand_df["PMM Muy [kN-m]"].to_numpy(dtype=float),
                                demand_df["Max Pu [kN]"].to_numpy(dtype=float),
                            ], axis=-1),
                            hovertemplate=(
                                "%{text}<br>"
                                "Overall U = %{customdata[0]:.3f}<br>"
                                "PMM U = %{customdata[1]:.3f}<br>"
                                "Tension U = %{customdata[2]:.3f}<br>"
                                "Mux = %{customdata[3]:,.1f} kN-m<br>"
                                "Muy = %{customdata[4]:,.1f} kN-m<br>"
                                "Pu = %{customdata[5]:,.1f} kN"
                                "<extra></extra>"
                            ),
                            name="all load points",
                        ))
                        fig_pmm.add_trace(go.Scatter3d(
                            x=[demand_mx],
                            y=[demand_my],
                            z=[slice_pu],
                            mode="markers+text",
                            marker=dict(size=8, color="#0f766e", line=dict(color="white", width=1.5)),
                            text=[f"Overall U={slice_row['Overall Util.']:.3f}"],
                            textposition="top center",
                            name="selected load point",
                        ))
                        fig_pmm.update_layout(
                            height=620,
                            margin=dict(l=0, r=0, t=45, b=0),
                            title=dict(text="3D φPMM Design Strength Surface with Tension Side and Load Points", font=dict(size=15)),
                            scene=dict(
                                xaxis_title="φMnx [kN-m]",
                                yaxis_title="φMny [kN-m]",
                                zaxis_title="φPn / Pu [kN]",
                                aspectmode="manual",
                                aspectratio=dict(x=1.30, y=1.30, z=0.72),
                                camera=dict(eye=dict(x=1.55, y=1.55, z=0.95)),
                            ),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        pmm_plot_col, pmm_summary_col = st.columns([4.2, 1.25], gap="medium")
                        with pmm_plot_col:
                            st.plotly_chart(fig_pmm, use_container_width=True)
                            st.caption(
                                "Note: the 3D φPMM surface uses different engineering units on each axis "
                                "(kN-m for moments and kN for axial force). The visual aspect ratio is adjusted "
                                "for readability and should not be interpreted as geometric proportionality. "
                                "For Pu < 0, the lower part of the surface is the tension/uplift side, closing toward pure steel tension φTn."
                            )
                        with pmm_summary_col:
                            with st.container(border=True):
                                st.markdown("**PMM / Uplift U Summary**")
                                st.caption("All active load cases; Overall U = max(PMM U, Tension U)")
                                for _, row in demand_df.sort_values("Overall Util.", ascending=False).iterrows():
                                    util = float(row["Overall Util."])
                                    status = "NG" if util > 1.0 else "OK"
                                    status_color = "red" if util > 1.0 else "green"
                                    selected_badge = " (selected)" if str(row["Case Plot Label"]) == str(slice_case) else ""
                                    st.markdown(f"**{row['Case Plot Label']}{selected_badge}**")
                                    st.markdown(f"Overall U = :{status_color}[**{util:.3f} ({status})**]")
                                    st.caption(
                                        f"Pu = {float(row['Max Pu [kN]']):,.1f} kN ({row['Pu Sign']})  \n"
                                        f"PMM U = {float(row['PMM Util.']):.3f}  \n"
                                        f"Tension U = {float(row['Tension Util.']):.3f}  \n"
                                        f"Mux = {float(row['PMM Mux [kN-m]']):,.1f} kN-m  \n"
                                        f"Muy = {float(row['PMM Muy [kN-m]']):,.1f} kN-m"
                                    )
                                    st.divider()
                    with st.expander("Detailed force table", expanded=False):
                        st.dataframe(
                            profile_df.drop(columns=["Case Plot Label"], errors="ignore").style.format({
                                "Depth [m]": "{:.2f}",
                                "Pu [kN]": "{:,.1f}",
                                "Mhead X [kN-m]": "{:,.1f}",
                                "Mhead Y [kN-m]": "{:,.1f}",
                                "Vx [kN]": "{:,.1f}",
                                "Vy [kN]": "{:,.1f}",
                                "V resultant [kN]": "{:,.1f}",
                                "Mux [kN-m]": "{:,.1f}",
                                "Muy [kN-m]": "{:,.1f}",
                                "M resultant [kN-m]": "{:,.1f}",
                                "Disp X [mm]": "{:,.3f}",
                                "Disp Y [mm]": "{:,.3f}",
                                "Soil Rx [kN]": "{:,.1f}",
                                "Soil Ry [kN]": "{:,.1f}",
                            }),
                            use_container_width=True,
                            height=420
                        )

                    with st.expander("φPMM assumptions and workflow", expanded=False):
                        st.markdown(
                            """
                            1. `Pu` is compression-positive and is held constant along the pile for each load case.
                            2. `Hx` produces lateral response in X and bending moment about the Y-axis (`Muy`).
                            3. `Hy` produces lateral response in Y and bending moment about the X-axis (`Mux`).
                            4. Pile-head boundary condition is applied independently from the load table. Fixed Head solves the head reaction moment internally; do not double-count external head moments from another model.
                            5. φPMM design strength capacity is generated by ACI 318-style strain compatibility using a Whitney stress block, steel yielding, and phi factors from tensile strain.
                            6. The primary biaxial PMM utilization is calculated by radial interpolation on the 3D φPMM design strength surface at the same `Pu`; the older linear uniaxial load-contour value is kept only as a comparison column.
                            7. Final design should still be verified with the governing ACI edition, project load combinations, slenderness/detailing requirements, and independent engineering review.
                            """
                        )

        st.divider()
with tab5:
    st.subheader("N-SPT Reference Values")
    st.markdown("### Clay")
    clay_ref = [{"Consistency": cons, "Typical N": db["N"], "cu [kPa]": db["cu"],
                 "Es [kPa]": db["Es"], "alpha (Bowles)": db["alpha"]}
                for cons, db in SOIL_DB["Clay"].items()]
    st.dataframe(pd.DataFrame(clay_ref), use_container_width=True, hide_index=True)

    st.markdown("### Sand")
    sand_ref = [{"Density": cons, "Typical N": db["N"], "phi [deg]": db["phi"],
                 "Es [kPa]": db["Es"], "nh wet": db["nh_wet"]}
                for cons, db in SOIL_DB["Sand"].items()]
    st.dataframe(pd.DataFrame(sand_ref), use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Formulas & References")
    st.markdown("**1. JRA:** $k_h = \\dfrac{E_0}{B_0} \\left(\\dfrac{D}{B_0}\\right)^{-3/4}$, $B_0=0.3$ m")
    st.markdown("**2. Terzaghi (Sand):** $k_h = \\dfrac{n_h \\cdot z}{D}$  |  **Clay:** $k_h = \\dfrac{\\alpha \\cdot c_u}{D}$")
    st.markdown("**3. Vesic 1961:** $k_h = 0.65 \\left(\\dfrac{E_s D^4}{E_p I_p}\\right)^{1/12} \\cdot \\dfrac{E_s}{D(1-\\nu^2)}$")
    st.markdown("**4. Broms 1964:** Sand $p_u = 3 K_p \\gamma' z D$  |  Clay $p_u = 9 c_u D$  |  $k_h = p_u / (0.01 D \\cdot D)$")
    st.markdown("**5. Spring:** $K_{sx} = k_{h,x} \\cdot D_x \\cdot L_{trib} \\cdot f_m$")
    st.markdown("**6. Beta:** $\\beta = \\left(\\dfrac{k_h \\cdot D}{4 E_p I_p}\\right)^{1/4}$")
    st.markdown("**7. Vertical tip (JRA):** $K_{v,tip} = \\dfrac{1}{3}\\dfrac{E_0}{B_0}\\left(\\dfrac{D}{B_0}\\right)^{-3/4} A_p$")

    st.divider()
    st.markdown(r"""
### Convention Notes
- **Loading width convention:** X-loading uses $D_x = B$, Y-loading uses $D_y = H$ in a JRA-style width convention.
- **Beta direction convention:** $Beta_X$ uses $k_{h,x}$, $D_x$, and $I_y$; $Beta_Y$ uses $k_{h,y}$, $D_y$, and $I_x$.
- **For X-direction loading:** the pile bends about the Y-axis, so $I_p = I_y$ is used in Vesic and response checks.
- **Global Average spring:** uses average group p-multiplier $P_{mult}$ for $K_{sx}$ and $K_{sy}$; the average is conservatively based on $\min(f_{m,x}, f_{m,y})$ at each pile.
- **Row-based spring table:** uses row-specific $f_m$ for each loading direction and row number; $K_{spring}=k_h \cdot D_{eq} \cdot L_{trib} \cdot f_m$.
- **Vertical tip spring for rectangular piles:** the JRA size-effect diameter is taken as the equivalent circular diameter $D_{eq,c}=\sqrt{4A_p/\pi}$.
- **Pile Design reinforcement guide:** recommended main steel ratio is a preliminary heuristic but is not allowed below the ACI 318-19 10.6.1.1 minimum of $0.01A_g$ for nonprestressed compression members.
- **Terzaghi sand $n_h$ values:** uses Terzaghi (1955) / Terzaghi & Peck (1967) values with 5-level N-range gradation (N<4, N≤10, N≤30, N≤50, N>50); confirm project-specific references if required.
- **N-SPT autofill:** When Soil Type + Consistency changes, N-SPT is set to the SOIL_DB representative value. When N-SPT is edited directly, $\phi$ (sand) and $c_u$ (clay) are linearly interpolated from Table 6.3.2-1 breakpoints, and Consistency label updates automatically.
- **Sand below water table:** JRA applies $E_0 \times 0.6$; Vesic applies $E_s \times 0.6$.

### References
1. **JRA (2002, 2017)** - *Specifications for Highway Bridges*, Japan Road Association.
2. **Bowles, J.E. (1997)** - *Foundation Analysis and Design*, 5th ed., McGraw-Hill.
3. **Vesic, A.S. (1961)** - *Beams on Elastic Subgrade and the Winkler's Hypothesis*.
4. **Broms, B.B. (1964)** - *Lateral Resistance of Piles in Cohesive/Cohesionless Soils*.
5. **AASHTO LRFD (2020)** - Table 10.7.2.4-1 p-multiplier.
6. **FHWA-NHI-16-009** - *Design and Construction of Driven Pile Foundations*, Section 9.4.
7. **Reese, L.C. & Van Impe, W.F. (2011)** - *Single Piles and Pile Groups Under Lateral Loading*.
""")

with tab7:
    st.subheader("Report / QA")
    st.caption(
        "Professional traceability output for the latest Pile Design run. "
        "Run / Update Pile Design first, then download the Markdown or Excel QA report."
    )
    report = st.session_state.get("latest_pile_design_report")
    if not report:
        st.info("No pile design report is available yet. Go to **Pile Design** and click **Run / Update Pile Design**.")
        st.markdown(
            """
            The report will include:
            - load-case source and assumptions
            - kh method, spring source, and pile-head boundary condition
            - governing pile design demands
            - PMM / tension utilization summary
            - head-boundary sensitivity results when available
            - QA limitations and traceability notes
            """
        )
    else:
        summary = report.get("summary", {})
        inputs = report.get("inputs", {})
        meta = report.get("meta", {})
        project = report.get("project", {})
        qa_checklist = report.get("qa_checklist", build_pile_design_qa_checklist(report))
        final_review = report.get("final_review_checklist", build_final_report_review_checklist(report))
        if str(project.get("project_title", "")).strip():
            st.info(f"Project: {project.get('project_title')} | Structure: {project.get('structure_name', '-')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Governing case", summary.get("governing_case", "-"))
        c2.metric("Overall Util.", f"{float(summary.get('max_util', 0.0)):.3f}", summary.get("overall_status", "-"))
        c3.metric("Head condition", inputs.get("head_condition", "-"))
        c4.metric("Report timestamp", meta.get("timestamp", "-"))

        st.markdown("### QA Summary")
        qa_rows = []
        for group_name, obj in (("Project", project), ("Meta", meta), ("Input", inputs), ("Summary", summary)):
            for k, v in obj.items():
                qa_rows.append({"Group": group_name, "Item": k, "Value": v})
        st.dataframe(pd.DataFrame(qa_rows), use_container_width=True, hide_index=True, height=300)

        st.markdown("### QA Checklist")
        st.dataframe(qa_checklist, use_container_width=True, hide_index=True, height=260)

        st.markdown("### Final Report Review / Punch List")
        fr_status = final_review["Status"].astype(str).str.upper() if final_review is not None and len(final_review) > 0 and "Status" in final_review.columns else pd.Series(dtype=str)
        fr_ng = int((fr_status == "NG").sum())
        fr_warn = int((fr_status == "WARN").sum())
        if fr_ng:
            st.error(f"Final report review has {fr_ng} NG item(s). Resolve before formal issue.")
        elif fr_warn:
            st.warning(f"Final report review has {fr_warn} warning item(s). Review and document acceptance before issue.")
        else:
            st.success("Final report review checklist has no NG/WARN items.")
        st.dataframe(final_review, use_container_width=True, hide_index=True, height=320)

        report_md = build_pile_design_markdown_report(report)
        dl1, dl2, dl3 = st.columns(3)
        try:
            report_docx = build_pile_design_word_report(report)
            dl1.download_button(
                "Download Word Report (.docx)",
                data=report_docx,
                file_name=f"PileSoilSpring_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except RuntimeError as e:
            dl1.error(str(e))
        dl2.download_button(
            "Download QA Report (.md)",
            data=report_md.encode("utf-8"),
            file_name=f"PileSoilSpring_QA_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        try:
            report_xlsx = build_pile_design_report_xlsx(report)
            dl3.download_button(
                "Download QA Workbook (.xlsx)",
                data=report_xlsx,
                file_name=f"PileSoilSpring_QA_Workbook_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except RuntimeError as e:
            dl3.error(str(e))

        with st.expander("Preview Markdown report", expanded=False):
            st.markdown(report_md)

        with st.expander("Data included in QA workbook", expanded=False):
            st.write("**QA checklist**")
            st.dataframe(qa_checklist, use_container_width=True, hide_index=True)
            st.write("**Final report review / punch list**")
            st.dataframe(final_review, use_container_width=True, hide_index=True)
            st.write("**Load cases**")
            st.dataframe(report.get("load_cases", pd.DataFrame()), use_container_width=True, hide_index=True)
            st.write("**Design demands**")
            st.dataframe(report.get("demand_df", pd.DataFrame()).drop(columns=["Case Plot Label"], errors="ignore"), use_container_width=True, hide_index=True)
            sensitivity_df = report.get("sensitivity_df", pd.DataFrame())
            if sensitivity_df is not None and len(sensitivity_df) > 0:
                st.write("**Head-boundary sensitivity**")
                st.dataframe(sensitivity_df, use_container_width=True, hide_index=True)
            else:
                st.info("Head-boundary sensitivity was not run for the latest design calculation.")

with tab8:
    st.subheader("Verification / Benchmark")
    st.caption(
        "Regression benchmark checks for the lateral-response solver and pile-head boundary conditions. "
        "These tests help detect accidental calculation changes after future code edits."
    )
    st.warning(
        "These benchmarks compare the app against locked internal baseline values. "
        "They are not a substitute for independent validation against LPILE/FEA or pile load-test data."
    )

    st.markdown("### Benchmark Cases")
    st.dataframe(verification_cases_dataframe(), use_container_width=True, hide_index=True, height=240)

    ctol, crun = st.columns([1, 2])
    with ctol:
        verification_tol = st.number_input(
            "Tolerance for response quantities [%]",
            min_value=0.10,
            max_value=10.0,
            value=1.0,
            step=0.10,
            help="Default 1% is intended for regression checks. Depth and zero-balance metrics use small absolute tolerances.",
        )
    with crun:
        st.markdown(" ")
        st.markdown(" ")
        run_verification = st.button("Run Verification Benchmarks", type="primary", use_container_width=True)

    if run_verification:
        summary_df, detail_df = run_verification_suite(verification_tol)
        st.session_state["latest_verification_summary"] = summary_df
        st.session_state["latest_verification_detail"] = detail_df
        st.session_state["latest_verification_tol"] = verification_tol

    summary_df = st.session_state.get("latest_verification_summary", pd.DataFrame())
    detail_df = st.session_state.get("latest_verification_detail", pd.DataFrame())
    verification_tol = st.session_state.get("latest_verification_tol", verification_tol)

    if summary_df is None or len(summary_df) == 0:
        st.info("Click **Run Verification Benchmarks** to execute the benchmark suite.")
    else:
        overall_ok = bool((summary_df["Status"] == "OK").all())
        m1, m2, m3 = st.columns(3)
        m1.metric("Overall Status", "OK" if overall_ok else "NG")
        m2.metric("Benchmark Cases", f"{len(summary_df)}")
        m3.metric("Tolerance", f"±{float(verification_tol):.2f}%")

        if overall_ok:
            st.success("All benchmark checks passed against the locked baseline values.")
        else:
            st.error("One or more benchmark checks failed. Review whether this is an intended engineering change or an unintended regression.")

        st.markdown("### Verification Summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True, height=240)

        st.markdown("### Detailed Metric Checks")
        st.dataframe(detail_df, use_container_width=True, hide_index=True, height=420)

        md_report = build_verification_markdown_report(summary_df, detail_df, verification_tol)
        dlv1, dlv2 = st.columns(2)
        dlv1.download_button(
            "Download Verification Report (.md)",
            data=md_report.encode("utf-8"),
            file_name=f"PileSoilSpring_Verification_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        try:
            verification_xlsx = build_verification_workbook(summary_df, detail_df, verification_tol)
            dlv2.download_button(
                "Download Verification Workbook (.xlsx)",
                data=verification_xlsx,
                file_name=f"PileSoilSpring_Verification_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except RuntimeError as exc:
            dlv2.error(str(exc))

        with st.expander("Preview verification markdown report", expanded=False):
            st.markdown(md_report)

