import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import json

st.set_page_config(page_title="Pile Soil Spring Calculator", layout="wide", page_icon="P")

VERSION = 9  # bumped: bug-fix Upload + UX improvements

#  CONSTANTS
WIDGET_KEYS = [
    "stage", "method", "pile_type",
    "D", "B", "H", "L", "fc", "dl", "nu",
    "wt", "scour", "use_group", "sD", "nx", "ny", "spring_output",
]

def _apply_pending_load():
    """Apply pending JSON project values before Streamlit widgets are created."""
    if "_pending_load" in st.session_state:
        pending = st.session_state.pop("_pending_load")
        for w in ("soil_editor", "_soil_edited", "_prev_type_cons"):
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
            for w in ("soil_editor", "_soil_edited", "_prev_type_cons"):
                if w in st.session_state:
                    del st.session_state[w]
            st.session_state["_just_profile_msg"] = f"Loaded predefined profile: {name}"

#  SAVE / LOAD PROJECT FUNCTIONS
def save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, s_D, nx, ny, spring_output,
    soil_layers, app_version
):
    """Create a dictionary with all project parameters for saving"""
    return {
        "app_version": app_version,
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
        "Very Soft":       {"N": 1,  "cu": 6,   "Es":  1500, "Gamma": 15, "alpha": 12,  "desc": "N<2,  cu<12 kPa, Bangkok Soft Clay"},
        "Soft":            {"N": 3,  "cu": 18,  "Es":  3000, "Gamma": 16, "alpha": 24,  "desc": "N=2-4, cu=12-25 kPa"},
        "Medium Stiff":    {"N": 6,  "cu": 36,  "Es":  8000, "Gamma": 17, "alpha": 48,  "desc": "N=5-8, cu=25-50 kPa"},
        "Stiff":           {"N": 12, "cu": 72,  "Es": 18000, "Gamma": 18, "alpha": 96,  "desc": "N=9-15, cu=50-100 kPa"},
        "Very Stiff":      {"N": 25, "cu": 150, "Es": 40000, "Gamma": 19, "alpha": 150, "desc": "N=16-30, cu=100-200 kPa"},
        "Hard":            {"N": 40, "cu": 250, "Es": 75000, "Gamma": 20, "alpha": 200, "desc": "N>30, cu>200 kPa"},
    },
    "Sand": {
        "Very Loose":   {"N": 2,  "phi": 26, "Es":  8000, "Gamma": 15, "nh_dry": 2200,  "nh_wet": 1300,  "desc": "N<4,   very loose, Dr<20%"},
        "Loose":        {"N": 7,  "phi": 30, "Es": 20000, "Gamma": 17, "nh_dry": 6600,  "nh_wet": 4000,  "desc": "N=4-10, loose, Dr=20-40%"},
        "Medium Dense": {"N": 20, "phi": 33, "Es": 45000, "Gamma": 18, "nh_dry": 17600, "nh_wet": 10500, "desc": "N=11-30, medium, Dr=40-60%"},
        "Dense":        {"N": 40, "phi": 37, "Es": 80000, "Gamma": 19, "nh_dry": 35000, "nh_wet": 21000, "desc": "N=31-50, dense, Dr=60-80%"},
        "Very Dense":   {"N": 55, "phi": 41, "Es":120000, "Gamma": 20, "nh_dry": 56000, "nh_wet": 34000, "desc": "N>50,  very dense, Dr>80%"},
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

#  ENGINEERING FUNCTIONS
def get_alpha_clay(N):
    """Bowles 1997 alpha factor for clay based on N-SPT"""
    if N <= 1:    return 12
    elif N <= 4:  return 24
    elif N <= 8:  return 48
    elif N <= 15: return 96
    elif N <= 30: return 150
    else:         return 200

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
    """Terzaghi sand nh values in kN/m3/m from Bowles 1997 Table 9-1."""
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
    """Broms (1964) ultimate lateral resistance โ’ secant kh at y=0.01D"""
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
    """Concrete pile properties. Ep = 4700โfc (MPa) โ’ kN/mยฒ"""
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

def solve_pile_lateral_response(depths, spring_k, EI, head_shear=0.0, head_moment=0.0):
    """Solve a Winkler beam with free-head loads and nodal springs."""
    depths = np.asarray(depths, dtype=float)
    spring_k = np.asarray(spring_k, dtype=float)
    n = len(depths)
    if n == 0:
        return np.array([]), np.array([]), np.array([]), np.array([]), np.array([])
    if n == 1 or (abs(head_shear) < 1e-12 and abs(head_moment) < 1e-12):
        zeros = np.zeros(n, dtype=float)
        return zeros, zeros, zeros, zeros, zeros
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

    u = np.linalg.solve(K, F)
    y = u[0::2]
    theta = u[1::2]
    reactions = spring_k * y

    shear = np.zeros(n, dtype=float)
    moment = np.zeros(n, dtype=float)
    for i, z in enumerate(depths):
        shear[i] = head_shear - reactions[:i + 1].sum()
        arm = z - depths[:i + 1]
        moment[i] = head_moment + head_shear * z - np.sum(reactions[:i + 1] * arm)

    return y, theta, reactions, shear, moment

def calc_kv_tip(N_tip, D, Ap, design_stage):
    """Vertical tip spring (JRA) Kv_tip = (E0/B0)(D/B0)^(-3/4)/3 ร— Ap"""
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N_tip
    kv = (E0 / B0) * (D / B0)**(-0.75) / 3.0
    Kv_tip = kv * Ap
    return Kv_tip, kv

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
    """Zigzag spring symbol between x0 and x1 at depth y"""
    length = abs(x1 - x0)
    dx = length / (n_coils * 4)
    xs = [x0]
    ys = [y]
    for i in range(n_coils):
        xs += [x0 + dx*(4*i+1), x0 + dx*(4*i+2), x0 + dx*(4*i+3), x0 + dx*(4*i+4)]
        ys += [y + dx, y - dx, y + dx, y]
    return xs, ys

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
    return msgs
def autofill_soil_row(row_dict):
    """Fill a soil row from SOIL_DB when Soil_Type and Consistency are known."""
    stype = str(row_dict.get("Soil_Type", "") or "")
    cons  = str(row_dict.get("Consistency", "") or "")
    if stype in SOIL_DB and cons in SOIL_DB[stype]:
        db = SOIL_DB[stype][cons]
        filled = dict(row_dict)
        filled["SPT_N"] = float(db["N"])
        filled["Es"]    = float(db["Es"])
        filled["Gamma"] = float(db["Gamma"])
        if stype == "Clay":
            filled["cu"]  = float(db["cu"])
            filled["phi"] = 0.0
        else:   # Sand
            filled["cu"]  = 0.0
            filled["phi"] = float(db["phi"])
        return filled, True
    return row_dict, False


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

    if bar_coords:
        bx, by = zip(*bar_coords)
        fig.add_trace(go.Scatter(
            x=bx,
            y=by,
            mode="markers",
            marker=dict(
                size=max(main_dia_mm * 0.75, 10),
                color="#c0392b",
                line=dict(color="white", width=1)
            ),
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
        df = pd.concat([
            df,
            pd.DataFrame([{
                "Angle [deg]": np.nan,
                "c [mm]": np.inf,
                "Pn [kN]": df["phiPnMax [kN]"].max() / (0.75 if transverse_system == "Spiral" else 0.65),
                "Mx [kN-m]": 0.0,
                "My [kN-m]": 0.0,
                "phi": 0.75 if transverse_system == "Spiral" else 0.65,
                "phiPn [kN]": df["phiPnMax [kN]"].max(),
                "phiMnx [kN-m]": 0.0,
                "phiMny [kN-m]": 0.0,
                "eps_t": 0.0,
                "phiPnMax [kN]": df["phiPnMax [kN]"].max(),
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
                "phiPnMax [kN]": df["phiPnMax [kN]"].max(),
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
    return pd.DataFrame({
        "phiPn [kN]": selected["phiPn [kN]"],
        "phiM [kN-m]": selected[m_col].abs(),
    }).dropna()

def moment_capacity_at_p(curve_df, pu_kN):
    """Interpolate factored uniaxial moment capacity at a factored axial demand."""
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
    if pu_kN < p_vals.min() or pu_kN > p_vals.max():
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
    curve = curve.groupby(curve["phiPn [kN]"].round(1), as_index=False)["phiM [kN-m]"].max()
    return curve.sort_values("phiPn [kN]").reset_index(drop=True)

def pmm_slice_at_p(pmm_df, pu_kN):
    """Interpolate an Mx-My capacity slice at a constant factored axial load."""
    if pmm_df.empty:
        return pd.DataFrame(columns=["phiMnx [kN-m]", "phiMny [kN-m]", "phiPn [kN]", "Angle [deg]"])

    rows = []
    for angle, grp in pmm_df.dropna(subset=["Angle [deg]"]).groupby("Angle [deg]"):
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
            nearest = grouped.iloc[(grouped["phiPn [kN]"] - pu_kN).abs().argmin()]
            mx = float(nearest["phiMnx [kN-m]"])
            my = float(nearest["phiMny [kN-m]"])
            p_use = float(nearest["phiPn [kN]"])
        else:
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

def pmm_surface_grid(pmm_df, n_levels=28):
    """Build PMM surface matrices by stacking constant-Pu interaction slices."""
    finite = pmm_df.dropna(subset=["Angle [deg]"]).copy()
    finite = finite[np.isfinite(finite["Angle [deg]"])]
    finite = finite[
        np.isfinite(finite["phiMnx [kN-m]"])
        & np.isfinite(finite["phiMny [kN-m]"])
        & np.isfinite(finite["phiPn [kN]"])
    ]
    if finite.empty:
        return None

    p_min = max(0.0, float(finite["phiPn [kN]"].quantile(0.02)))
    p_max = float(finite["phiPn [kN]"].quantile(0.98))
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
    """Build a closed PMM surface by stacking polar Mx-My capacity slices."""
    finite = pmm_df.dropna(subset=["Angle [deg]"]).copy()
    finite = finite[
        np.isfinite(finite["phiMnx [kN-m]"])
        & np.isfinite(finite["phiMny [kN-m]"])
        & np.isfinite(finite["phiPn [kN]"])
    ]
    if finite.empty:
        return None

    p_min = max(0.0, float(finite["phiPn [kN]"].quantile(0.02)))
    p_max = float(finite["phiPn [kN]"].quantile(0.98))
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
        as_ratio_rec = 0.015
    elif kh_max_surface <= 15000:
        as_ratio_rec = 0.010
    else:
        as_ratio_rec = 0.008
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
    as_min_mm2 = max(as_ratio_rec * ag_mm2, 0.01 * ag_mm2)

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

def build_excel(df_results, df_row_results, df_soil, N_tip, Kv_tip, Ap, Ep, Ipx, Ipy, B, H, L, fc,
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
            ("Pile tip area Ap", Ap, "m2"),
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
            ("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%", "Based on crack control / ACI 318"),
            ("Minimum As [m2]", round(As_min, 4), "As = Ap x Ratio"),
            ("Minimum Rebar Requirement", "See ACI 10.5.1 & 21.6", "Use the governing code and detailing requirement"),
        ]
        for ri, row in enumerate(rebar_data):
            for ci, val in enumerate(row):
                fmt_use = fmt_bold if ci == 0 else fmt_num if isinstance(val, (int, float)) else fmt_info
                ws5.write(2 + ri, ci, val, fmt_use)
        ws5.set_column(0, 0, 32); ws5.set_column(1, 1, 20); ws5.set_column(2, 2, 50)

    buf.seek(0)
    return buf.read()
st.sidebar.title("Pile Spring Calculator")
st.sidebar.caption(f"version {VERSION}")
st.sidebar.markdown("---")

for _msg_key, _box in (("_just_loaded_msg", st.sidebar.success),
                      ("_just_profile_msg", st.sidebar.success)):
    if _msg_key in st.session_state and st.session_state[_msg_key]:
        _box(st.session_state.pop(_msg_key))

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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Input & Pile Section", "Results & Profile", "kh & Spring Plots",
    "Pile Design", "N-SPT Reference", "Formulas & References"
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
                "SPT_N": st.column_config.NumberColumn("N-SPT", format="%.0f", width="small"),
                "Es": st.column_config.NumberColumn("Es [kPa]", format="%.0f", width="small"),
                "cu": st.column_config.NumberColumn("cu [kPa]", format="%.1f", width="small"),
                "phi": st.column_config.NumberColumn("phi [deg]", format="%.1f", width="small"),
                "Gamma": st.column_config.NumberColumn("gamma [kN/m3]", format="%.1f", width="small"),
            }
        )

        prev_tc = st.session_state.get("_prev_type_cons", {})
        new_tc = {}
        autofilled = edited_df.copy()
        did_fill = False

        for idx, row in edited_df.iterrows():
            stype = str(row.get("Soil_Type", "") or "")
            cons = str(row.get("Consistency", "") or "")
            new_tc[idx] = (stype, cons)
            if (stype and cons and stype in SOIL_DB and cons in SOIL_DB.get(stype, {}) and prev_tc.get(idx) != (stype, cons)):
                filled_row, ok = autofill_soil_row(row.to_dict())
                if ok:
                    autofilled.loc[idx] = pd.Series(filled_row)
                    did_fill = True

        st.session_state["_prev_type_cons"] = new_tc

        if did_fill:
            st.session_state.soil_layers = autofilled
            for w in ("soil_editor", "_soil_edited"):
                if w in st.session_state:
                    del st.session_state[w]
            st.toast("Soil parameters were auto-filled from SOIL_DB.")
            st.rerun()
        else:
            st.session_state["_soil_edited"] = edited_df

        _msgs = validate_soil_profile(edited_df)
        if _msgs:
            with st.expander(f"Soil profile warnings ({len(_msgs)})", expanded=False):
                for m in _msgs:
                    st.write(m)
df_soil = st.session_state.get("_soil_edited", st.session_state.soil_layers)

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
    for _i, _row in _df_check.iterrows():
        _missing = []
        for _col, _label in _REQUIRED_COLS.items():
            _v = _row.get(_col, None)
            if _v is None or (isinstance(_v, float) and np.isnan(_v)) or str(_v).strip() in ("", "None"):
                _missing.append(_label)
        if _missing:
            _row_no = _i + 1
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
        z_mid       = max(z - node_spacing / 2, 0.05)

        if z < scour_depth:
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
    tip_mask = (df_soil_calc["Depth_From"] <= L) & (df_soil_calc["Depth_To"] > L)
    tip_layer = df_soil_calc[tip_mask].iloc[0] if tip_mask.any() else df_soil_calc.iloc[-1]
    N_tip          = float(tip_layer["SPT_N"])
    Kv_tip, kv_tip = calc_kv_tip(N_tip, max(Deq_x, Deq_y), Ap, design_stage)

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
            df_results, df_row_results, df_soil_draw, N_tip, Kv_tip, Ap, Ep, Ipx, Ipy, B, H, L, fc,
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

st.sidebar.header("6. Save / Load Project")

project_data = save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, s_D, nx, ny, spring_output,
    st.session_state.get("_soil_edited", st.session_state.soil_layers), VERSION
)
json_str = json.dumps(project_data, indent=2, ensure_ascii=True)
st.sidebar.download_button(
    "Save Project (.json)",
    data=json_str,
    file_name=f"PileProject_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
    mime="application/json",
    use_container_width=True
)

st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader(
    "Open Project File",
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
            st.sidebar.error(f"Invalid JSON file: {e}")
        except Exception as e:
            st.sidebar.error(f"Could not load project file: {e}")

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

        st.subheader("Load Cases")
        default_load_cases = pd.DataFrame({
            "Use": [True, True, True],
            "Load Case": ["LC1", "LC2", "LC3"],
            "Pu [kN]": [1500.0, 1800.0, 1200.0],
            "Hx [kN]": [200.0, 0.0, 160.0],
            "Hy [kN]": [0.0, 200.0, 120.0],
        })
        if "pile_design_load_cases" not in st.session_state:
            st.session_state["pile_design_load_cases"] = default_load_cases

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
        st.session_state["pile_design_load_cases"] = load_case_input.copy()

        load_cases = load_case_input.copy()
        for col in ["Pu [kN]", "Hx [kN]", "Hy [kN]"]:
            load_cases[col] = pd.to_numeric(load_cases[col], errors="coerce").fillna(0.0)
        if "Use" not in load_cases:
            load_cases["Use"] = True
        load_cases["Use"] = load_cases["Use"].fillna(True).astype(bool)
        load_cases["Load Case"] = load_cases["Load Case"].astype(str).replace({"nan": ""})
        for idx in load_cases.index:
            if not load_cases.loc[idx, "Load Case"].strip():
                load_cases.loc[idx, "Load Case"] = f"LC{idx + 1}"
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

        run_col, note_col = st.columns([1.0, 2.2])
        if run_col.button("Run / Update Pile Design", type="primary", use_container_width=True):
            st.session_state["pile_design_has_run"] = True
        note_col.caption("PMM interaction and force diagrams are calculated only after running this design step.")
        design_has_run = bool(st.session_state.get("pile_design_has_run", False))
        if not design_has_run:
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

                profile_frames = []
                summary_rows = []
                response_error = None
                EI_x_loading = Ep * Ipy
                EI_y_loading = Ep * Ipx

                for case_idx, case in active_cases.iterrows():
                    lc = str(case["Load Case"])
                    pu_kN = float(case["Pu [kN]"])
                    hx_kN = float(case["Hx [kN]"])
                    hy_kN = float(case["Hy [kN]"])
                    try:
                        disp_x, theta_x, soil_rx, shear_x, moment_y = solve_pile_lateral_response(
                            depths, spring_k_x, EI_x_loading, head_shear=hx_kN, head_moment=0.0
                        )
                        disp_y, theta_y, soil_ry, shear_y, moment_x = solve_pile_lateral_response(
                            depths, spring_k_y, EI_y_loading, head_shear=hy_kN, head_moment=0.0
                        )
                    except Exception as exc:
                        response_error = f"{lc}: {exc}"
                        break

                    axial = np.full(len(depths), pu_kN, dtype=float)
                    shear_resultant = np.sqrt(shear_x**2 + shear_y**2)
                    moment_resultant = np.sqrt(moment_x**2 + moment_y**2)
                    frame = pd.DataFrame({
                        "Load Case": lc,
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
                    util_profile = (
                        np.abs(moment_x) / max(mcap_x, 1e-9)
                        + np.abs(moment_y) / max(mcap_y, 1e-9)
                    )
                    util_profile = np.where(np.isfinite(util_profile), util_profile, np.inf)
                    imx = int(np.argmax(np.abs(moment_x))) if len(moment_x) else 0
                    imy = int(np.argmax(np.abs(moment_y))) if len(moment_y) else 0
                    iv = int(np.argmax(np.abs(shear_resultant))) if len(shear_resultant) else 0
                    iu = int(np.argmax(util_profile)) if len(util_profile) else 0
                    summary_rows.append({
                        "Load Case": lc,
                        "Max Pu [kN]": float(np.max(axial)),
                        "Min Pu [kN]": float(np.min(axial)),
                        "Max |Mux| [kN-m]": float(np.max(np.abs(moment_x))),
                        "z @ Mux [m]": float(depths[imx]),
                        "Max |Muy| [kN-m]": float(np.max(np.abs(moment_y))),
                        "z @ Muy [m]": float(depths[imy]),
                        "Max |V| [kN]": float(np.max(np.abs(shear_resultant))),
                        "z @ V [m]": float(depths[iv]),
                        "PMM Util.": float(np.max(util_profile)),
                        "z @ PMM [m]": float(depths[iu]),
                        "Mx cap @ Pu [kN-m]": mcap_x,
                        "My cap @ Pu [kN-m]": mcap_y,
                    })

                if response_error:
                    st.error(f"Pile response analysis could not run: {response_error}")
                else:
                    profile_df = pd.concat(profile_frames, ignore_index=True)
                    demand_df = pd.DataFrame(summary_rows)
                    max_util = float(demand_df["PMM Util."].max()) if not demand_df.empty else np.inf
                    governing = demand_df.loc[demand_df["PMM Util."].idxmax()] if not demand_df.empty else None
                    overall_pu_max = float(demand_df["Max Pu [kN]"].max())
                    overall_pu_min = float(demand_df["Min Pu [kN]"].min())
                    overall_mx = float(demand_df["Max |Mux| [kN-m]"].max())
                    overall_my = float(demand_df["Max |Muy| [kN-m]"].max())
                    overall_v = float(demand_df["Max |V| [kN]"].max())
                    overall_m = float(np.sqrt(overall_mx**2 + overall_my**2))

                    shear_summary = calc_pile_design_summary(
                        pile_type, D, B, H, fc, cover_mm, main_bar, tie_bar,
                        "X", max(overall_pu_max, 0.0), overall_v, overall_m,
                        n_main_bars, n_b_face, n_h_face, n_tie_legs, as_ratio_rec
                    )
                    tie_ok = float(tie_spacing_mm) <= float(shear_summary["s_rec_mm"]) + 1e-9

                    st.subheader("Design Envelope")
                    env1, env2, env3, env4, env5 = st.columns(5)
                    env1.metric("Max Pu [kN]", f"{overall_pu_max:,.1f}")
                    env2.metric("Min Pu [kN]", f"{overall_pu_min:,.1f}")
                    env3.metric("Max |Mux| [kN-m]", f"{overall_mx:,.1f}")
                    env4.metric("Max |Muy| [kN-m]", f"{overall_my:,.1f}")
                    env5.metric("Max PMM Util.", f"{max_util:,.2f}", "OK" if max_util <= 1.0 else "Increase steel")

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
                            ("PMM interaction", "OK" if max_util <= 1.0 else "NG", f"governing = {governing['Load Case'] if governing is not None else '-'}"),
                            ("Recommended tie spacing", f"{shear_summary['s_rec_mm']:.0f} mm", "preliminary shear/confinement check"),
                        ]
                        st.table(pd.DataFrame(section_info, columns=["Item", "Value", "Note"]))
                        if max_util > 1.0:
                            st.warning("PMM utilization exceeds 1.0. Increase main bar size/quantity or revise the section.")
                        if not tie_ok:
                            st.warning("Provided tie spacing is larger than the preliminary recommended spacing.")

                    with right_design:
                        st.subheader("Load Case Results")
                        st.dataframe(
                            demand_df.style.format({
                                "Max Pu [kN]": "{:,.1f}",
                                "Min Pu [kN]": "{:,.1f}",
                                "Max |Mux| [kN-m]": "{:,.1f}",
                                "z @ Mux [m]": "{:.2f}",
                                "Max |Muy| [kN-m]": "{:,.1f}",
                                "z @ Muy [m]": "{:.2f}",
                                "Max |V| [kN]": "{:,.1f}",
                                "z @ V [m]": "{:.2f}",
                                "PMM Util.": "{:.3f}",
                                "z @ PMM [m]": "{:.2f}",
                                "Mx cap @ Pu [kN-m]": "{:,.1f}",
                                "My cap @ Pu [kN-m]": "{:,.1f}",
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
                            - **PMM check:** linear biaxial load-contour utilization using ACI-style uniaxial strain-compatible curves.
                            """
                        )

                    st.subheader("Force Diagrams Along Pile")
                    symbols = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon", "triangle-down", "pentagon"]
                    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]

                    def _force_figure(x_col, title, x_title):
                        fig = go.Figure()
                        for i, (lc, grp) in enumerate(profile_df.groupby("Load Case", sort=False)):
                            fig.add_trace(go.Scatter(
                                x=grp[x_col],
                                y=grp["Depth [m]"],
                                mode="lines+markers",
                                name=str(lc),
                                line=dict(color=colors[i % len(colors)], width=2),
                                marker=dict(symbol=symbols[i % len(symbols)], size=7),
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

                    st.subheader("ACI PMM Interaction")

                    ag_mm2 = Ap * 1e6
                    as_total_mm2 = float(bar_df["As_mm2"].sum())
                    rho_prov = as_total_mm2 / max(ag_mm2, 1e-9)
                    rho_min_temp = 0.002
                    as_min_temp_mm2 = rho_min_temp * ag_mm2
                    min_ok = as_total_mm2 >= as_min_temp_mm2
                    if pile_type == "Round":
                        face_note = "Round pile: face-by-face rectangular distribution check is not applicable."
                    else:
                        as_b_face = int(n_b_face) * get_rebar_area_mm2(main_bar)
                        as_h_face = int(n_h_face) * get_rebar_area_mm2(main_bar)
                        face_req = as_min_temp_mm2 / 2.0
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
                                Shrinkage/temperature distributed reinforcement only. Column longitudinal minimum should be checked separately.<br>
                                Required rho = {rho_min_temp*100:.3f}%<br>
                                As,min total = {as_min_temp_mm2:,.0f} mm2, As provided total = {as_total_mm2:,.0f} mm2
                                <b style="color:{'#087f23' if min_ok else '#c4123f'}">({'OK' if min_ok else 'NG'})</b><br>
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
                        title=dict(text="Uniaxial interaction curves", font=dict(size=18)),
                        margin=dict(l=10, r=10, t=70, b=10),
                        xaxis=dict(title="phi Mn (kN-m)", zeroline=True, zerolinecolor="#758195", gridcolor="#dbe2ec"),
                        yaxis=dict(title="phi Pn (kN)", zeroline=True, zerolinecolor="#758195", gridcolor="#dbe2ec"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="center", x=0.5),
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_uni, use_container_width=True)
                    if pile_type == "Round":
                        st.caption("For round piles, the about-x and about-y interaction curves are nearly identical, so the dashed red curve can overlap the blue curve.")

                    governing_index = int(demand_df["PMM Util."].idxmax()) if not demand_df.empty else 0
                    slice_case = st.selectbox(
                        "PMM slice load case",
                        demand_df["Load Case"].tolist(),
                        index=governing_index,
                        help="The Mux-Muy slice is drawn at the selected load case Pu."
                    )
                    slice_row = demand_df[demand_df["Load Case"] == slice_case].iloc[0]
                    slice_pu = float(slice_row["Max Pu [kN]"])
                    slice_df = pmm_slice_at_p(pmm_df, slice_pu)
                    demand_mx = float(slice_row["Max |Mux| [kN-m]"])
                    demand_my = float(slice_row["Max |Muy| [kN-m]"])

                    fig_slice = go.Figure()
                    if not slice_df.empty:
                        fig_slice.add_trace(go.Scatter(
                            x=slice_df["phiMnx [kN-m]"],
                            y=slice_df["phiMny [kN-m]"],
                            mode="lines",
                            fill="toself",
                            fillcolor="rgba(0, 150, 220, 0.12)",
                            line=dict(color="#008fd3", width=3),
                            name="PMM slice"
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
                        text=[f"{slice_case}<br>U={slice_row['PMM Util.']:.3f}"],
                        textposition="bottom right",
                        name="demand"
                    ))
                    fig_slice.update_layout(
                        height=500,
                        title=dict(text=f"PMM Mux-Muy slice at Pu = {slice_pu:,.0f} kN", font=dict(size=15)),
                        margin=dict(l=10, r=10, t=60, b=10),
                        xaxis=dict(title="Mux (kN-m)", zeroline=True, zerolinecolor="#3f4654", gridcolor="#e2e8f0"),
                        yaxis=dict(title="Muy (kN-m)", zeroline=True, zerolinecolor="#3f4654", gridcolor="#e2e8f0", scaleanchor="x", scaleratio=1),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_slice, use_container_width=True)

                    show_3d_pmm = st.checkbox(
                        "Show 3D PMM interaction surface",
                        value=False,
                        help="The 3D PMM plot is useful for review but can be heavier to render."
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
                                name="PMM surface",
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
                        fig_pmm.add_trace(go.Scatter3d(
                            x=[demand_mx],
                            y=[demand_my],
                            z=[slice_pu],
                            mode="markers+text",
                            marker=dict(size=7, color="#1b6b6b"),
                            text=[f"U={slice_row['PMM Util.']:.3f}"],
                            textposition="top center",
                            name="load point",
                        ))
                        fig_pmm.update_layout(
                            height=620,
                            margin=dict(l=0, r=0, t=45, b=0),
                            title=dict(text="3D PMM interaction surface with load point", font=dict(size=15)),
                            scene=dict(
                                xaxis_title="Mux (kN-m)",
                                yaxis_title="Muy (kN-m)",
                                zaxis_title="Pu (kN)",
                            ),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        st.plotly_chart(fig_pmm, use_container_width=True)
                    with st.expander("Detailed force table", expanded=False):
                        st.dataframe(
                            profile_df.style.format({
                                "Depth [m]": "{:.2f}",
                                "Pu [kN]": "{:,.1f}",
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

                    with st.expander("PMM assumptions and workflow", expanded=False):
                        st.markdown(
                            """
                            1. `Pu` is compression-positive and is held constant along the pile for each load case.
                            2. `Hx` produces lateral response in X and bending moment about the Y-axis (`Muy`).
                            3. `Hy` produces lateral response in Y and bending moment about the X-axis (`Mux`).
                            4. PMM capacity is generated by ACI 318-style strain compatibility using a Whitney stress block, steel yielding, and phi factors from tensile strain.
                            5. The biaxial PMM utilization shown is a preliminary linear load-contour check from the uniaxial P-Mx and P-My capacities at the same `Pu`.
                            6. Final design should still be verified with the governing ACI edition, project load combinations, slenderness/detailing requirements, and independent engineering review.
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
- **Global Average spring:** uses average group p-multiplier $P_{mult}$ for $K_{sx}$ and $K_{sy}$.
- **Row-based spring table:** uses row-specific $f_m$ for each loading direction and row number; $K_{spring}=k_h \cdot D_{eq} \cdot L_{trib} \cdot f_m$.
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
