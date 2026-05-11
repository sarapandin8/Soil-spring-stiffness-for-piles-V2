import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import json

st.set_page_config(page_title="Pile Soil Spring Calculator", layout="wide", page_icon="๐—๏ธ")

VERSION = 9  # bumped: bug-fix Upload + UX improvements

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  CONSTANTS
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
WIDGET_KEYS = [
    "stage", "method", "pile_type",
    "D", "B", "H", "L", "fc", "dl", "nu",
    "wt", "scour", "use_group", "sD", "nx", "ny", "spring_output",
]  # เธเธตเธขเนเธ—เธธเธเธ•เธฑเธงเธ—เธตเนเธเธนเธเธเธฑเธ Widget โ€” เธซเนเธฒเธกเนเธเนเนเธเธซเธฅเธฑเธ widget เธชเธฃเนเธฒเธเนเธฅเนเธง

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  PENDING-LOAD HANDLER  (เธ•เนเธญเธเธญเธขเธนเนเธเนเธญเธเธชเธฃเนเธฒเธ widget!)
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
def _apply_pending_load():
    """Apply เธเนเธฒเธ—เธตเน load เธเธฒเธเนเธเธฅเน JSON เธเนเธญเธเธ—เธตเน widget เธเธฐเธ–เธนเธเธชเธฃเนเธฒเธ
    เน€เธเธทเนเธญเธซเธฅเธตเธเน€เธฅเธตเนเธขเธ 'st.session_state.<key> cannot be modified after the widget is instantiated'."""
    if "_pending_load" in st.session_state:
        pending = st.session_state.pop("_pending_load")
        # เธฅเนเธฒเธ widget-state เธเธญเธ data_editor เน€เธเธทเนเธญเธเธฑเธเธเธฑเธเนเธซเน render DataFrame เนเธซเธกเน
        for w in ("soil_editor", "_soil_edited", "_prev_type_cons"):
            if w in st.session_state:
                del st.session_state[w]
        for k, v in pending.items():
            st.session_state[k] = v
        st.session_state["_just_loaded_msg"] = pending.get("__msg__", "")

def _apply_pending_profile():
    """เนเธเน Predefined soil profile (เน€เธฃเธตเธขเธเธเนเธญเธเธชเธฃเนเธฒเธ widget)"""
    if "_pending_profile" in st.session_state:
        name = st.session_state.pop("_pending_profile")
        if name in SOIL_PROFILES:
            st.session_state.soil_layers = SOIL_PROFILES[name].copy()
            for w in ("soil_editor", "_soil_edited", "_prev_type_cons"):
                if w in st.session_state:
                    del st.session_state[w]
            st.session_state["_just_profile_msg"] = f"โ… เนเธเนเนเธเธฃเนเธเธฅเน: {name}"

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  SAVE / LOAD PROJECT FUNCTIONS
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
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
            # Coerce types เธชเธณเธซเธฃเธฑเธ number_input (เธ•เนเธญเธเธเธฒเธฃ float/int เธ•เธฃเธเธเธฑเธ default)
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

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  REFERENCE DATABASE
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
SOIL_DB = {
    "Clay": {
        "Very Soft":       {"N": 1,  "cu": 6,   "Es":  1500, "Gamma": 15, "alpha": 12,  "desc": "N<2,  cu<12 kPa, Bangkok Soft Clay"},
        "Soft":            {"N": 3,  "cu": 18,  "Es":  3000, "Gamma": 16, "alpha": 24,  "desc": "N=2โ€“4, cu=12โ€“25 kPa"},
        "Medium Stiff":    {"N": 6,  "cu": 36,  "Es":  8000, "Gamma": 17, "alpha": 48,  "desc": "N=5โ€“8, cu=25โ€“50 kPa"},
        "Stiff":           {"N": 12, "cu": 72,  "Es": 18000, "Gamma": 18, "alpha": 96,  "desc": "N=9โ€“15, cu=50โ€“100 kPa"},
        "Very Stiff":      {"N": 25, "cu": 150, "Es": 40000, "Gamma": 19, "alpha": 150, "desc": "N=16โ€“30, cu=100โ€“200 kPa"},
        "Hard":            {"N": 40, "cu": 250, "Es": 75000, "Gamma": 20, "alpha": 200, "desc": "N>30, cu>200 kPa"},
    },
    "Sand": {
        "Very Loose":   {"N": 2,  "phi": 26, "Es":  8000, "Gamma": 15, "nh_dry": 2200,  "nh_wet": 1300,  "desc": "N<4,   very loose, Dr<20%"},
        "Loose":        {"N": 7,  "phi": 30, "Es": 20000, "Gamma": 17, "nh_dry": 6600,  "nh_wet": 4000,  "desc": "N=4โ€“10, loose, Dr=20โ€“40%"},
        "Medium Dense": {"N": 20, "phi": 33, "Es": 45000, "Gamma": 18, "nh_dry": 17600, "nh_wet": 10500, "desc": "N=11โ€“30, medium, Dr=40โ€“60%"},
        "Dense":        {"N": 40, "phi": 37, "Es": 80000, "Gamma": 19, "nh_dry": 35000, "nh_wet": 21000, "desc": "N=31โ€“50, dense, Dr=60โ€“80%"},
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

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  SESSION STATE INIT  (must run BEFORE handlers below)
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
if 'version' not in st.session_state or st.session_state.version < VERSION:
    st.session_state.clear()
    st.session_state.version = VERSION

# โ… CRITICAL: เธ•เนเธญเธ apply pending changes เธเนเธญเธ widget เธ–เธนเธเธชเธฃเนเธฒเธเธ—เธฑเนเธเธซเธกเธ”
_apply_pending_load()
_apply_pending_profile()

# เธ•เนเธญเธ init soil_layers เธซเธฅเธฑเธ pending handlers (เน€เธเธฃเธฒเธฐ Reset เธญเธฒเธเธฅเธ key เธเธตเนเนเธ)
if 'soil_layers' not in st.session_state:
    st.session_state.soil_layers = SOIL_PROFILES["Bangkok - General Profile"].copy()

# _prev_type_cons: เน€เธเนเธ (Soil_Type, Consistency) เธเธญเธเนเธ•เนเธฅเธฐเนเธ–เธงเธเธฒเธ rerun เธ—เธตเนเนเธฅเนเธง
# เนเธเนเธ•เธฃเธงเธเธเธฑเธเธงเนเธฒเธเธนเนเนเธเนเน€เธเธฅเธตเนเธขเธเธเธเธดเธ”เธ”เธดเธ โ’ trigger auto-fill
if "_prev_type_cons" not in st.session_state:
    _init = st.session_state.soil_layers
    st.session_state["_prev_type_cons"] = {
        i: (str(r.get("Soil_Type", "")), str(r.get("Consistency", "")))
        for i, r in _init.iterrows()
    }

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  ENGINEERING FUNCTIONS
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
def get_alpha_clay(N):
    """Bowles 1997 alpha factor for clay based on N-SPT"""
    if N <= 1:    return 12
    elif N <= 4:  return 24
    elif N <= 8:  return 48
    elif N <= 15: return 96
    elif N <= 30: return 150
    else:         return 200

def calc_kh_jra(N, D, design_stage, soil_type, below_water):
    """JRA: kh = (E0/B0)ยท(D/B0)^(-3/4); E0=2800N (Normal) | 5600N (Seismic); Sand below WT ร— 0.6"""
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N
    if soil_type == "Sand" and below_water:
        E0 *= 0.6
    kh = (E0 / B0) * (D / B0) ** (-0.75)
    return kh, E0

def get_nh_terzaghi(N, below_water):
    """Terzaghi (1955) nh values for sand [kN/mยณ/m] (Bowles 1997 Table 9-1)"""
    if N < 10:   return 4000  if below_water else 7000
    elif N < 30: return 12000 if below_water else 21000
    else:        return 34000 if below_water else 56000

def calc_kh_terzaghi(N, soil_type, D, z_mid, below_water, cu=None):
    """Terzaghi (1955) / Bowles (1997): Sand kh=nhยทz/D  |  Clay kh=ฮฑยทcu/D"""
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
    """เธ•เธฃเธงเธเธชเธญเธ Gap / Overlap เนเธเธเธฑเนเธเธ”เธดเธ โ€” เธเนเธฒเธกเนเธ–เธงเธ—เธตเนเธขเธฑเธเธเธฃเธญเธ Depth เนเธกเนเธเธฃเธ"""
    msgs = []
    if df is None or len(df) == 0:
        return ["โ ๏ธ เนเธกเนเธกเธตเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธ"]
    # เธเธฃเธญเธเน€เธเธเธฒเธฐเนเธ–เธงเธ—เธตเนเธกเธตเธเนเธฒ Depth_From เนเธฅเธฐ Depth_To (เธเนเธญเธเธเธฑเธ TypeError เธเธฒเธเนเธ–เธงเธงเนเธฒเธ)
    df_valid = df.dropna(subset=["Depth_From", "Depth_To"]).copy()
    if len(df_valid) == 0:
        return []   # เธขเธฑเธเนเธกเนเธกเธตเนเธ–เธงเธชเธกเธเธนเธฃเธ“เน โ€” เนเธกเนเนเธชเธ”เธ warning
    df_sorted = df_valid.sort_values("Depth_From").reset_index(drop=True)
    for i in range(len(df_sorted)):
        if df_sorted.loc[i, "Depth_To"] <= df_sorted.loc[i, "Depth_From"]:
            msgs.append(f"โ เนเธ–เธงเธ—เธตเน {i+1}: Depth_To ({df_sorted.loc[i,'Depth_To']:.1f}) เธ•เนเธญเธเธกเธฒเธเธเธงเนเธฒ Depth_From ({df_sorted.loc[i,'Depth_From']:.1f})")
        if i > 0:
            prev_to = df_sorted.loc[i-1, "Depth_To"]
            curr_from = df_sorted.loc[i, "Depth_From"]
            if abs(prev_to - curr_from) > 1e-6:
                if curr_from > prev_to:
                    msgs.append(f"โ ๏ธ เธกเธตเธเนเธญเธเธงเนเธฒเธ (gap) เธฃเธฐเธซเธงเนเธฒเธเนเธ–เธง {i} เธ–เธถเธ {i+1}: {prev_to:.1f} โ’ {curr_from:.1f} m")
                else:
                    msgs.append(f"โ ๏ธ เธเธฑเนเธเธ”เธดเธเธเนเธญเธเธ—เธฑเธ (overlap) เธฃเธฐเธซเธงเนเธฒเธเนเธ–เธง {i} เธ–เธถเธ {i+1}: {curr_from:.1f} < {prev_to:.1f} m")
    return msgs

def autofill_soil_row(row_dict):
    """เธ”เธถเธเธเนเธฒ typical เธเธฒเธ SOIL_DB เธกเธฒเนเธชเนเนเธซเนเธญเธฑเธ•เนเธเธกเธฑเธ•เธด เน€เธกเธทเนเธญเธฃเธนเน Soil_Type + Consistency
    เธเธทเธเธเนเธฒ (filled_dict, did_fill:bool)"""
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
        title_text = f"Square/Rect Pile  Bร—H = {B:.2f}ร—{H:.2f} m"

    # โ”€โ”€ X / Y axes เธ—เธตเนเธเธธเธ” CG โ”€โ”€
    fig.add_annotation(ax=0, ay=0, x=axis_len, y=0, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    fig.add_annotation(x=axis_len * 1.06, y=0, text="<b>X</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')
    fig.add_annotation(ax=0, ay=0, x=0, y=axis_len, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    fig.add_annotation(x=0, y=axis_len * 1.08, text="<b>Y</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')

    # CG marker + label (เธงเธฒเธเน€เธเธตเธขเธเน€เธเธทเนเธญเนเธกเนเธ—เธฑเธเนเธเธ)
    fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers',
                             marker=dict(color='red', size=12, symbol='x'),
                             showlegend=False, name='CG', hoverinfo='skip'))
    fig.add_annotation(x=axis_len * 0.18, y=-axis_len * 0.18, text="<b>CG</b>", showarrow=False,
                       font=dict(size=11, color='red'), xref='x', yref='y')

    props_text = (f"Ap = {Ap:.4f} mยฒ<br>Ix = {Ipx:.5f} mโด<br>Iy = {Ipy:.5f} mโด<br>Ep = {Ep/1000:.0f} MPa")
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

def calculate_rebar_params(df_results, Ap):
    """Calculate rebar design parameters"""
    kh_max_surface = df_results["kh_x [kN/mยณ]"].iloc[1] if len(df_results) > 1 else 0
    kh_min_deep = df_results["kh_x [kN/mยณ]"].iloc[-1] if len(df_results) > 0 else 0
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
                node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta,
                kh_max_surface, kh_min_deep, as_ratio_rec, As_min, use_group, spring_output):
    """Build Excel file with all calculation results"""
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
        fmt_title  = wb.add_format({'bold': True, 'font_size': 12, 'bg_color': '#1a4f8a', 'font_color': 'white', 'border': 1})
        fmt_header = wb.add_format({'bold': True, 'bg_color': '#BDD7EE', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        fmt_num    = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        fmt_bold   = wb.add_format({'bold': True, 'border': 1})
        fmt_info   = wb.add_format({'italic': True, 'font_color': '#555555'})

        # Sheet 1
        ws1 = wb.add_worksheet("Lateral Springs")
        ws1.write(0, 0, f"Lateral Soil Spring Stiffness โ€” Method: {method}", fmt_title)
        ws1.write(1, 0, f"Pile: B={B:.2f}m H={H:.2f}m L={L:.1f}m f'c={fc:.0f}MPa ฮ”L={node_spacing:.2f}m p-mult={Pmult:.3f}", fmt_info)
        headers = list(df_results.columns)
        for ci, h in enumerate(headers):
            ws1.write(3, ci, h, fmt_header)
        for ri, row in df_results.iterrows():
            for ci, val in enumerate(row):
                if isinstance(val, float) and not np.isnan(val):
                    ws1.write(4+ri, ci, val, fmt_num)
                else:
                    ws1.write(4+ri, ci, val if not (isinstance(val, float) and np.isnan(val)) else '', fmt_num)
        ws1.set_column(0, len(headers)-1, 15)

        # Sheet 1B: row-based springs
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
                        ws1b.write(4+ri, ci, val, fmt_num)
                    else:
                        ws1b.write(4+ri, ci, val if not (isinstance(val, float) and np.isnan(val)) else '', fmt_num)
            ws1b.set_column(0, len(row_headers)-1, 15)
            ws1b.set_column(5, 5, 16)
            ws1b.set_column(11, 11, 18)
        else:
            ws1b.write(3, 0, "Row-based table is available when Apply Group Effect is enabled.", fmt_info)
            ws1b.set_column(0, 0, 70)

        # Sheet 2
        ws2 = wb.add_worksheet("Vertical Tip Spring")
        ws2.write(0, 0, "Vertical Tip Spring Stiffness", fmt_title)
        tip_data = [
            ("Parameter", "Value", "Unit"),
            ("N-SPT at pile tip", N_tip, "blow/30cm"),
            ("E0 (at tip)", (2800 if design_stage=="Normal" else 5600)*N_tip, "kN/mยฒ"),
            ("Pile tip area Ap", Ap, "mยฒ"),
            ("Kv_tip (vertical spring)", round(Kv_tip, 1), "kN/m"),
            ("Design Stage", design_stage, "-"),
        ]
        for ri, row in enumerate(tip_data):
            for ci, val in enumerate(row):
                ws2.write(2+ri, ci, val, fmt_bold if ci==0 else (fmt_num if isinstance(val, (int, float)) else fmt_bold))
        ws2.set_column(0, 0, 28); ws2.set_column(1, 1, 18); ws2.set_column(2, 2, 12)

        # Sheet 3
        ws3 = wb.add_worksheet("Summary")
        ws3.write(0, 0, "Project Summary & Pile Properties", fmt_title)
        summary = [
            ("Pile Width B [m]", B, "m"),
            ("Pile Height H [m]", H, "m"),
            ("Pile Length L [m]", L, "m"),
            ("f'c [MPa]", fc, "MPa"),
            ("Ep [kN/mยฒ]", round(Ep, 0), "kN/mยฒ"),
            ("Ap [mยฒ]", round(Ap, 5), "mยฒ"),
            ("Ix (Bending about X) [mโด]", round(Ipx, 6), "mโด"),
            ("Iy (Bending about Y) [mโด]", round(Ipy, 6), "mโด"),
            ("Node Spacing ฮ”L [m]", node_spacing, "m"),
            ("kh Method", method, "-"),
            ("Design Stage", design_stage, "-"),
            ("Water Table [m]", water_table, "m"),
            ("Scour Depth [m]", scour_depth, "m"),
            ("p-multiplier", Pmult, "-"),
            ("Spring Output", spring_output, "-"),
            ("Excel Export", "Global average + row-based sheets", "-"),
            ("ฮฒ (Characteristic Length) [1/m]", round(beta, 4), "1/m"),
            ("Kv_tip [kN/m]", round(Kv_tip, 1), "kN/m"),
        ]
        for ri, (k, v, u) in enumerate(summary):
            ws3.write(2+ri, 0, k, fmt_bold)
            ws3.write(2+ri, 1, v, fmt_num if isinstance(v, float) else fmt_bold)
            ws3.write(2+ri, 2, u, fmt_bold)
        ws3.set_column(0, 0, 34); ws3.set_column(1, 1, 18); ws3.set_column(2, 2, 10)

        # Sheet 4
        df_soil.to_excel(writer, sheet_name="Soil Profile", index=False)
        ws4 = writer.sheets["Soil Profile"]
        ws4.set_column(0, len(df_soil.columns)-1, 15)

        # Sheet 5
        ws5 = wb.add_worksheet("Rebar Design Guide")
        ws5.write(0, 0, "Pile Reinforcement Design Guide (Based on Spring Results)", fmt_title)
        rebar_data = [
            ("Parameter", "Value", "Remark / Reference"),
            ("Surface kh_x [kN/mยณ]", round(kh_max_surface, 1), "Used to evaluate soil stiffness condition"),
            ("Deep kh_x [kN/mยณ]", round(kh_min_deep, 1), "Stiffness at pile tip layer"),
            ("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%", "Based on Crack Control / ACI 318"),
            ("Minimum As [mยฒ]", round(As_min, 4), "As = Ap x Ratio"),
            ("Min. Rebar Requirement", "See ACI 10.5.1 & 21.6", "Max of Code min. or Crack control min."),
        ]
        for ri, row in enumerate(rebar_data):
            for ci, val in enumerate(row):
                fmt_use = fmt_bold if ci==0 else fmt_num if isinstance(val, (int, float)) else fmt_info
                ws5.write(2+ri, ci, val, fmt_use)
        ws5.set_column(0, 0, 32); ws5.set_column(1, 1, 20); ws5.set_column(2, 2, 50)

    buf.seek(0)
    return buf.read()

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  SIDEBAR
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
st.sidebar.title("๐—๏ธ Pile Spring Calculator")
st.sidebar.caption(f"version {VERSION}")
st.sidebar.markdown("---")

# Show post-action messages (set by handlers above)
for _msg_key, _box in (("_just_loaded_msg", st.sidebar.success),
                      ("_just_profile_msg", st.sidebar.success)):
    if _msg_key in st.session_state and st.session_state[_msg_key]:
        _box(st.session_state.pop(_msg_key))

st.sidebar.header("1. Project Settings")
c1, c2 = st.sidebar.columns(2)
design_stage = c1.selectbox("Design Stage", ["Normal", "Seismic"], key="stage",
                            help="Normal = เธเนเธฒเนเธเนเธเธฒเธ, Seismic = E0 ร— 2 (เธเธฃเธ“เธตเนเธเนเธเธ”เธดเธเนเธซเธง)")
method       = c2.selectbox("kh Method", ["JRA", "Terzaghi", "Vesic 1961", "Broms 1964"], key="method",
                            help="เน€เธฅเธทเธญเธเธงเธดเธเธตเธเธณเธเธงเธ“ kh โ€” เนเธเธฐเธเธณ JRA เธชเธณเธซเธฃเธฑเธเธเธฒเธเธ—เธฑเนเธงเนเธ")

_method_tips = {
    "JRA":        ("โ… เนเธเธฐเธเธณเธชเธณเธซเธฃเธฑเธเธญเธญเธเนเธเธ", "success",
                   "Primary method เธชเธณเธซเธฃเธฑเธเธเธฒเธเธชเธฐเธเธฒเธ/highway\nโ€ข เนเธเน N-SPT เนเธ”เธขเธ•เธฃเธ\nโ€ข Calibrated เธชเธณเธซเธฃเธฑเธเธ”เธดเธเน€เธญเน€เธเธตเธข\nโ€ข เธขเธญเธกเธฃเธฑเธเนเธ”เธข DOH, MRTA, เธเธฒเธฃเธฃเธ–เนเธเธฏ"),
    "Terzaghi":   ("โ–๏ธ Cross-check", "info",
                   "Conservative bound โ€” kh เธ•เนเธณเธเธงเนเธฒ JRA\nโ€ข เนเธเนเน€เธ—เธตเธขเธเธเธฑเธ JRA เธ–เนเธฒเธ•เนเธฒเธเธเธฑเธ <50% เธ–เธทเธญเธงเนเธฒเธเธฅเธญเธ”เธ เธฑเธข"),
    "Vesic 1961": ("โ ๏ธ เธ•เนเธญเธเธเธฒเธฃ Es Lab", "warning",
                   "เธ•เนเธญเธเธเธฒเธฃ Es เธเธฒเธ PMT/lab เธเธฃเธดเธเน€เธ—เนเธฒเธเธฑเนเธ\nโ เธซเนเธฒเธกเนเธเน Es เธเธฒเธ N-SPT เธเธฑเธ Soft Clay"),
    "Broms 1964": ("๐ซ เธชเธณเธซเธฃเธฑเธ Capacity", "error",
                   "เนเธซเนเธเนเธฒ kh เธชเธนเธเน€เธเธดเธเธเธฃเธดเธ (เนเธเธฅเน Failure)\nโ เธซเนเธฒเธกเนเธเนเน€เธเนเธ spring เธญเธญเธเนเธเธเน€เธซเธฅเนเธเน€เธชเธฃเธดเธก"),
}
_tip = _method_tips[method]
with st.sidebar.expander(f"{_tip[0]}", expanded=True):
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[_tip[1]](_tip[2])

st.sidebar.header("2. Pile Properties")
pile_type = st.sidebar.selectbox("Pile Type", ["Round", "Square/Rectangular"], key="pile_type")
if pile_type == "Round":
    D = st.sidebar.number_input("Diameter D [m]", 0.1, 5.0, 0.6, 0.05, key="D",
                                help="เน€เธชเนเธเธเนเธฒเธเธจเธนเธเธขเนเธเธฅเธฒเธเน€เธชเธฒเน€เธเนเธกเธเธฅเธก")
    B = H = D
else:
    c3, c4 = st.sidebar.columns(2)
    B = c3.number_input("Width B [m]",  0.1, 5.0, 0.35, 0.05, key="B", help="เธเธเธฒเธ”เธ”เนเธฒเธเธ—เธตเนเธเธเธฒเธเนเธเธ X")
    H = c4.number_input("Height H [m]", 0.1, 5.0, 0.35, 0.05, key="H", help="เธเธเธฒเธ”เธ”เนเธฒเธเธ—เธตเนเธเธเธฒเธเนเธเธ Y")
    D = max(B, H)

L            = st.sidebar.number_input("Pile Length L [m]",     1.0, 120.0, 25.0, 1.0,  key="L",
                                       help="เธเธงเธฒเธกเธขเธฒเธงเน€เธชเธฒเน€เธเนเธกเธ—เธฑเนเธเธซเธกเธ”")
fc           = st.sidebar.number_input("Concrete f'c [MPa]",   15.0, 100.0, 28.0, 1.0,  key="fc",
                                       help="เธเธณเธฅเธฑเธเธญเธฑเธ”เธเธฃเธฐเธฅเธฑเธขเธเธญเธเธเธญเธเธเธฃเธตเธ•")
node_spacing = st.sidebar.number_input("Node Spacing ฮ”L [m]",   0.25,  5.0,  1.0, 0.25, key="dl",
                                       help="เธฃเธฐเธขเธฐเธซเนเธฒเธเธเธญเธ Node เธชเธณเธซเธฃเธฑเธเธชเธฃเนเธฒเธ spring")

if method == "Vesic 1961":
    nu = st.sidebar.number_input("Poisson Ratio ฮฝ", 0.10, 0.50, 0.35, 0.05, key="nu")
else:
    nu = float(st.session_state.get("nu", 0.35))

st.sidebar.header("3. Site Conditions")
water_table = st.sidebar.number_input("Water Table Depth [m]", 0.0, float(L), 1.0,  0.5, key="wt",
                                       help="เธเธงเธฒเธกเธฅเธถเธเธฃเธฐเธ”เธฑเธเธเนเธณเนเธ•เนเธ”เธดเธเธเธฒเธเธเธดเธงเธ”เธดเธ (0 = เธเนเธณเธ—เนเธงเธกเธเธดเธงเธ”เธดเธ)")
scour_depth = st.sidebar.number_input("Scour Depth [m]",       0.0, float(L), 0.0,  0.5, key="scour",
                                       help="เธเธงเธฒเธกเธฅเธถเธเธ—เธตเนเธ–เธนเธเธเธฑเธ”เน€เธเธฒเธฐ โ€” kh = 0 เธ•เธฑเนเธเนเธ•เนเธเธดเธงเธ”เธดเธเธ–เธถเธเธฃเธฐเธ”เธฑเธเธเธตเน")

st.sidebar.header("4. Group Effect")
use_group = st.sidebar.checkbox("Apply Group Effect (p-multiplier)", key="use_group",
                                help="เนเธเนเธเธฑเธเน€เธชเธฒเน€เธเนเธกเธเธฅเธธเนเธก (โฅ 2 เธ•เนเธ)")
if use_group:
    s_D = st.sidebar.number_input("Pile Spacing s/D", 2.0, 12.0, 3.0, 0.5, key="sD",
                                   help="เธญเธฑเธ•เธฃเธฒเธชเนเธงเธเธฃเธฐเธขเธฐเธซเนเธฒเธเธฃเธฐเธซเธงเนเธฒเธเน€เธชเธฒเธ•เนเธญเน€เธชเนเธเธเนเธฒเธเธจเธนเธเธขเนเธเธฅเธฒเธ")
    gc1, gc2 = st.sidebar.columns(2)
    nx = gc1.number_input("Piles in X", 1, 20, 3, 1, key="nx")
    ny = gc2.number_input("Piles in Y", 1, 20, 3, 1, key="ny")
    spring_output = st.sidebar.radio(
        "Spring Output",
        ["Global average spring", "Row-based spring table"],
        key="spring_output",
        help="เน€เธฅเธทเธญเธเธ•เธฒเธฃเธฒเธเธเธฅเธฅเธฑเธเธเนเนเธเธเธเนเธฒเน€เธเธฅเธตเนเธขเธ—เธฑเนเธเธเธฅเธธเนเธก เธซเธฃเธทเธญเนเธเธเนเธขเธเธ•เธฒเธก row เธชเธณเธซเธฃเธฑเธเนเธ•เนเธฅเธฐเธ—เธดเธจเธ—เธฒเธ"
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
        st.sidebar.success("s/D โฅ 6 โ’ fm = 1.00 (no reduction)")
        Pmult = 1.0
        fms_x = [1.0] * int(nx)
        fms_y = [1.0] * int(ny)
    else:
        st.sidebar.info(
            f"**Average fm = {Pmult:.3f}**  (เนเธเนเธเนเธฒเน€เธ”เธตเธขเธงเธ—เธธเธเธ•เนเธ)\n\n"
            f"nx={int(nx)}, ny={int(ny)}, n={n_total} piles\n\n"
            f"Ref: FHWA-NHI-16-009 ยง9.4"
        )
        with st.sidebar.expander("๐“ fm breakdown per row"):
            st.caption("**X-direction rows** (loading โ’ X)")
            for i, fm in enumerate(fms_x):
                lbl = "Lead" if i==0 else ("2nd" if i==1 else "3rd+")
                st.write(f"  Row {i+1} ({lbl}): fm = {fm:.3f}")
            st.caption("**Y-direction rows** (loading โ’ Y)")
            for i, fm in enumerate(fms_y):
                lbl = "Lead" if i==0 else ("2nd" if i==1 else "3rd+")
                st.write(f"  Row {i+1} ({lbl}): fm = {fm:.3f}")
else:
    s_D = float(st.session_state.get("sD", 3.0))
    nx  = int(st.session_state.get("nx", 3))
    ny  = int(st.session_state.get("ny", 3))
    spring_output = "Global average spring"
    fms_x = [1.0]
    fms_y = [1.0]
    Pmult = 1.0

pile_is_round = (pile_type == "Round")
Ap, Ipx, Ipy, Ep, Deq_x, Deq_y = calc_pile_props("Round" if pile_is_round else "Square", D, B, H, fc)

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  TABS
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
st.title("Pile Lateral Soil Spring Stiffness Calculator")
st.caption("Units: kN, m  |  Methods: JRA / Terzaghi 1955 / Vesic 1961 / Broms 1964")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Input & Pile Section", "Results & Profile", "kh & Spring Plots",
    "Pile Design", "N-SPT Reference", "Formulas & References"
])

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 1 โ•โ•โ•โ•โ•โ•โ•โ•
with tab1:
    left_col, right_col = st.columns([3, 2], gap="large")
    with right_col:
        st.subheader("๐“ Pile Cross-Section")
        st.plotly_chart(pile_section_figure("Round" if pile_is_round else "Square",
                                            D, B, H, Ap, Ipx, Ipy, Ep, compact=True),
                        use_container_width=True)
        st.markdown("**Section Properties**")
        mc1, mc2 = st.columns(2)
        mc1.metric("Ap [mยฒ]", f"{Ap:.4f}"); mc2.metric("Ep [MPa]", f"{Ep/1000:.0f}")
        mc3, mc4 = st.columns(2)
        mc3.metric("Ix [mโด]", f"{Ipx:.5f}"); mc4.metric("Iy [mโด]", f"{Ipy:.5f}")

        st.subheader("Pile Group Plan")
        st.plotly_chart(
            pile_group_plan_figure(
                "Round" if pile_is_round else "Square",
                D, B, H, s_D, nx, ny, use_group
            ),
            use_container_width=True
        )

    with left_col:
        st.subheader("๐ชจ Soil Layer Input")

        with st.expander("๐—๏ธ เน€เธฅเธทเธญเธเนเธเธฃเนเธเธฅเนเธ”เธดเธเธ•เธฑเธงเธญเธขเนเธฒเธ (Predefined Profiles)", expanded=False):
            selected_profile = st.selectbox("เน€เธฅเธทเธญเธเนเธเธฃเนเธเธฅเน:", list(SOIL_PROFILES.keys()),
                                            key="_profile_selector")
            st.dataframe(SOIL_PROFILES[selected_profile], use_container_width=True, hide_index=True)
            st.info("**เธญเนเธฒเธเธญเธดเธ:** เนเธเธฃเนเธเธฅเนเธเธฃเธธเธเน€เธ—เธเธฏ เธชเธฃเธธเธเธเธฒเธเธเธฑเนเธเธ”เธดเธเน€เธเธฅเธตเนเธขเธ—เธฒเธเธ เธนเธกเธดเธจเธฒเธชเธ•เธฃเน (เธเธฃเธกเธ—เธฃเธฑเธเธขเธฒเธเธฃเธเธฃเธ“เธต, เธเธธเธฌเธฒเธฏ, เธเธฃเธฃเธกเธจเธฒเธชเธ•เธฃเน) เนเธเนเธชเธณเธซเธฃเธฑเธ Preliminary Design เน€เธ—เนเธฒเธเธฑเนเธ")
            if st.button("โ… เนเธเนเนเธเธฃเนเธเธฅเนเธเธตเน", use_container_width=True, type="primary",
                         key="_use_profile_btn"):
                st.session_state["_pending_profile"] = selected_profile
                st.rerun()

        clay_opts = list(SOIL_DB["Clay"].keys())
        sand_opts = list(SOIL_DB["Sand"].keys())
        all_cons  = clay_opts + sand_opts

        # โ”€โ”€ FIX double-entry issue: เธเธฑเธเธเธฑเธ dtype เนเธซเนเธ•เธฃเธเธเธฑเธ column_config เธเนเธญเธ โ”€โ”€
        # st.data_editor เธเธฐ revert edit เนเธฃเธเธ–เนเธฒ dtype เนเธกเนเธ•เธฃเธ (เน€เธเนเธ int vs float)
        _df_input = st.session_state.soil_layers.copy()
        for _col in ["Depth_From", "Depth_To", "SPT_N", "Es", "cu", "phi", "Gamma"]:
            if _col in _df_input.columns:
                _df_input[_col] = pd.to_numeric(_df_input[_col], errors="coerce").astype(float)

        # โ”€โ”€ เธชเนเธ _df_input เน€เธเนเธฒ editor เนเธ”เธขเนเธกเนเธ•เนเธญเธเน€เธเธตเธขเธเธเธฅเธฑเธเน€เธเนเธฒ soil_layers โ”€โ”€
        # (soil_layers เนเธเนเน€เธเนเธ "base for reset" เน€เธ—เนเธฒเธเธฑเนเธ เนเธกเน update เธ—เธธเธ rerun)
        edited_df = st.data_editor(
            _df_input,
            num_rows="dynamic",
            use_container_width=True,
            key="soil_editor",
            column_config={
                "Depth_From":   st.column_config.NumberColumn("From [m]",   format="%.2f", width="small"),
                "Depth_To":     st.column_config.NumberColumn("To [m]",     format="%.2f", width="small"),
                "Soil_Type":    st.column_config.SelectboxColumn("Type",    options=["Clay","Sand"], width="small"),
                "Consistency":  st.column_config.SelectboxColumn("Consist.", options=all_cons, width="medium"),
                "SPT_N":        st.column_config.NumberColumn("N-SPT",      format="%.0f", width="small"),
                "Es":           st.column_config.NumberColumn("Es [kPa]",   format="%.0f", width="small"),
                "cu":           st.column_config.NumberColumn("cu [kPa]",   format="%.1f", width="small"),
                "phi":          st.column_config.NumberColumn("ฯ [ยฐ]",      format="%.1f", width="small"),
                "Gamma":        st.column_config.NumberColumn("ฮณ [kN/mยณ]",  format="%.1f", width="small"),
            }
        )
        # โ”€โ”€ AUTO-FILL: เธ•เธฃเธงเธเธเธฑเธเธเธฒเธฃเน€เธเธฅเธตเนเธขเธ Soil_Type / Consistency โ’ เธ”เธถเธเธเนเธฒเธเธฒเธ SOIL_DB โ”€โ”€
        prev_tc   = st.session_state.get("_prev_type_cons", {})
        new_tc    = {}
        autofilled = edited_df.copy()
        did_fill  = False

        for idx, row in edited_df.iterrows():
            stype = str(row.get("Soil_Type", "") or "")
            cons  = str(row.get("Consistency", "") or "")
            new_tc[idx] = (stype, cons)

            # เน€เธเธทเนเธญเธเนเธ trigger: (1) Type/Consistency เน€เธเธฅเธตเนเธขเธ เธซเธฃเธทเธญ (2) เน€เธเนเธเนเธ–เธงเนเธซเธกเนเธ—เธตเนเธกเธตเธเนเธฒเธเธฃเธ
            # เนเธฅเธฐ (3) เธเนเธฒเธเธฑเนเธเธกเธตเธญเธขเธนเนเนเธ SOIL_DB
            if (stype and cons
                    and stype in SOIL_DB
                    and cons in SOIL_DB.get(stype, {})
                    and prev_tc.get(idx) != (stype, cons)):
                filled_row, ok = autofill_soil_row(row.to_dict())
                if ok:
                    autofilled.loc[idx] = pd.Series(filled_row)
                    did_fill = True

        st.session_state["_prev_type_cons"] = new_tc

        if did_fill:
            # เธญเธฑเธเน€เธ”เธ• base + เธฅเนเธฒเธ editor state เนเธฅเนเธง rerun เน€เธเธทเนเธญเนเธชเธ”เธเธเนเธฒเธ—เธตเนเน€เธ•เธดเธกเนเธฅเนเธง
            st.session_state.soil_layers = autofilled
            for w in ("soil_editor", "_soil_edited"):
                if w in st.session_state:
                    del st.session_state[w]
            st.toast("โ… เน€เธ•เธดเธกเธเนเธฒเธ”เธดเธเธเธฒเธ SOIL_DB เธญเธฑเธ•เนเธเธกเธฑเธ•เธดเนเธฅเนเธง", icon="๐ชจ")
            st.rerun()
        else:
            # เธเธเธ•เธด โ€” เน€เธเนเธเธเธฅเนเธ key เนเธขเธ เนเธกเนเน€เธเธตเธขเธเธเธฅเธฑเธ soil_layers (เธ•เธฑเธ” feedback loop)
            st.session_state["_soil_edited"] = edited_df

        # Validate soil layers
        _msgs = validate_soil_profile(edited_df)
        if _msgs:
            with st.expander(f"โ ๏ธ เธ•เธฃเธงเธเธเธเธเธฑเธเธซเธฒเนเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธ ({len(_msgs)} เธฃเธฒเธขเธเธฒเธฃ)", expanded=False):
                for m in _msgs:
                    st.write(m)

# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
#  MAIN CALCULATION
# โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€โ”€
df_soil = st.session_state.get("_soil_edited", st.session_state.soil_layers)

# โ”€โ”€ เธ•เธฃเธงเธเธชเธญเธเธเธงเธฒเธกเธชเธกเธเธนเธฃเธ“เนเธเธญเธเธเนเธญเธกเธนเธฅเธ”เธดเธเธเนเธญเธเธเธณเธเธงเธ“ โ”€โ”€
_REQUIRED_COLS = {
    "Depth_From": "เธเธงเธฒเธกเธฅเธถเธเน€เธฃเธดเนเธกเธ•เนเธ (From)",
    "Depth_To":   "เธเธงเธฒเธกเธฅเธถเธเธชเธดเนเธเธชเธธเธ” (To)",
    "Soil_Type":  "เธเธฃเธฐเน€เธ เธ—เธ”เธดเธ (Type)",
    "SPT_N":      "เธเนเธฒ N-SPT",
}
_ready = True

# เธเธฃเธญเธเน€เธเธเธฒเธฐเนเธ–เธงเธ—เธตเนเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฒเธเธชเนเธงเธ (เนเธกเนเนเธเนเนเธ–เธงเธงเนเธฒเธเธ—เธฑเนเธเธซเธกเธ”)
_df_check = df_soil.dropna(how="all").copy()

if len(_df_check) == 0:
    st.warning("โ ๏ธ เธเธฃเธธเธ“เธฒเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเธญเธขเนเธฒเธเธเนเธญเธข 1 เธเธฑเนเธ เธเนเธญเธเธเธณเธเธงเธ“", icon="๐ชจ")
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
            _depth_label = (f"From {_row.get('Depth_From','?')} m"
                            if not pd.isna(_row.get("Depth_From")) else f"เนเธ–เธงเธ—เธตเน {_row_no}")
            _incomplete.append(f"โ€ข **{_depth_label}** โ€” เธเธฒเธ”: {', '.join(_missing)}")

    if _incomplete:
        st.warning(
            "โ ๏ธ **เธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเธขเธฑเธเธเธฃเธญเธเนเธกเนเธเธฃเธ** เธเธฃเธธเธ“เธฒเน€เธ•เธดเธกเธเนเธฒเธ—เธตเนเธเธฒเธ”เธเนเธญเธเธฃเธฐเธเธเธเธฐเธเธณเธเธงเธ“:\n\n"
            + "\n".join(_incomplete),
            icon="๐ชจ"
        )
        _ready = False

    # เธ•เธฃเธงเธเธงเนเธฒ pile เธขเธฒเธงเธเธงเนเธฒเธเธฑเนเธเธ”เธดเธเธ—เธตเนเธเธณเธซเธเธ”เธซเธฃเธทเธญเน€เธเธฅเนเธฒ
    if _ready:
        _df_valid = _df_check.dropna(subset=["Depth_From", "Depth_To"])
        _max_depth = _df_valid["Depth_To"].max() if len(_df_valid) > 0 else 0
        if L > _max_depth + 1e-3:
            st.warning(
                f"โ ๏ธ เธเธงเธฒเธกเธขเธฒเธงเน€เธชเธฒเน€เธเนเธก **L = {L:.1f} m** เน€เธเธดเธเธเธงเนเธฒเธเนเธญเธกเธนเธฅเธ”เธดเธเธ—เธตเนเธเธฃเธญเธ "
                f"(เธฅเธถเธเธชเธธเธ” {_max_depth:.1f} m) โ€” "
                f"เธฃเธฐเธเธเธเธฐเนเธเนเธเธฑเนเธเธ”เธดเธเธฅเนเธฒเธเธชเธธเธ”เนเธ—เธเธชเธณเธซเธฃเธฑเธเธชเนเธงเธเธ—เธตเนเน€เธเธดเธ",
                icon="โ ๏ธ"
            )

depths  = np.arange(0, L + 1e-9, node_spacing)
if len(depths) == 0 or abs(depths[-1] - L) > 1e-6:
    depths = np.append(depths, L)
tributary_lengths = calc_tributary_lengths(depths, L)
results = []

# df_soil_draw: version เธ—เธตเนเธเธฃเธญเธเนเธ–เธงเนเธกเนเธเธฃเธเธญเธญเธเนเธฅเนเธง โ€” เนเธเนเธชเธณเธซเธฃเธฑเธเธงเธฒเธ” UI เธ—เธธเธเธ—เธตเน
_req_draw = ["Depth_From", "Depth_To", "Soil_Type", "SPT_N"]
df_soil_draw = df_soil.dropna(subset=_req_draw).copy()
df_soil_draw = df_soil_draw[
    df_soil_draw["Soil_Type"].astype(str).str.strip().isin(["Clay", "Sand"])
].reset_index(drop=True)

if not _ready:
    df_results = pd.DataFrame()
    df_row_results = pd.DataFrame()
    N_tip = 0.0; Kv_tip = 0.0; kv_tip = 0.0
    beta  = 0.0; kh_avg = 0.0
    kh_max_surface = kh_min_deep = as_ratio_rec = As_min = 0.0
else:
    # เธเธฃเธญเธเน€เธเธเธฒเธฐเนเธ–เธงเธ—เธตเนเธกเธตเธเนเธญเธกเธนเธฅเธเธฃเธเธเนเธญเธเธเธณเธเธงเธ“ โ€” เธ•เธฑเธ”เนเธ–เธงเธ—เธตเนเธเธณเธฅเธฑเธเธเธดเธกเธเนเธเนเธฒเธเธญเธญเธ
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
            "kh_x [kN/mยณ]": round(kh_x, 1),
            "kh_y [kN/mยณ]": round(kh_y, 1),
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
                    "kh [kN/mยณ]":   round(kh_x, 1),
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
                    "kh [kN/mยณ]":   round(kh_y, 1),
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

    # ฮฒ โ€” use Ipy for X-direction (bend about Y-axis)
    Ip_for_beta = Ipy if not pile_is_round else Ipx
    kh_avg = df_results["kh_x [kN/mยณ]"].replace(0, np.nan).mean()
    if pd.isna(kh_avg) or kh_avg <= 0 or Ep * Ip_for_beta <= 0:
        beta = 0.0
    else:
        beta = (kh_avg * Deq_x / (4 * Ep * Ip_for_beta))**0.25

    kh_max_surface, kh_min_deep, as_ratio_rec, As_min = calculate_rebar_params(df_results, Ap)

# โ”€โ”€ Sidebar Export โ”€โ”€
st.sidebar.header("5. Export")
if _ready:
    try:
        excel_data = build_excel(
            df_results, df_row_results, df_soil_draw, N_tip, Kv_tip, Ap, Ep, Ipx, Ipy, B, H, L, fc,
            node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta,
            kh_max_surface, kh_min_deep, as_ratio_rec, As_min, use_group, spring_output
        )
        st.sidebar.download_button(
            "๐“ฅ Download Excel (.xlsx)",
            data=excel_data,
            file_name=f"PileSpring_{method}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except RuntimeError as e:
        st.sidebar.error(str(e))
else:
    st.sidebar.button("๐“ฅ Download Excel (.xlsx)", disabled=True, use_container_width=True,
                      help="เธเธฃเธธเธ“เธฒเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเนเธซเนเธเธฃเธเธเนเธญเธ")

# โ”€โ”€ SAVE / LOAD PROJECT โ”€โ”€
st.sidebar.header("6. Save / Load Project")

project_data = save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, s_D, nx, ny, spring_output,
    st.session_state.get("_soil_edited", st.session_state.soil_layers), VERSION
)
json_str = json.dumps(project_data, indent=2, ensure_ascii=False)
st.sidebar.download_button(
    "๐’พ SAVE Project (.json)",
    data=json_str,
    file_name=f"PileProject_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
    mime="application/json",
    use_container_width=True
)

st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader(
    "๐“ OPEN Project File",
    type=["json"],
    help="เน€เธฅเธทเธญเธเนเธเธฅเน .json เธ—เธตเนเธเธฑเธเธ—เธถเธเนเธงเนเธเธฒเธเธเธธเนเธก SAVE",
    key="_project_uploader",
)

# โ… FIX: เนเธเน pending-load pattern เน€เธเธทเนเธญเธซเธฅเธตเธเน€เธฅเธตเนเธขเธ widget-state error
if uploaded_file is not None:
    file_id = getattr(uploaded_file, "file_id", uploaded_file.name + str(uploaded_file.size))
    last_id = st.session_state.get("_last_loaded_file_id")
    if last_id != file_id:
        try:
            loaded_data = json.load(uploaded_file)
            updates = load_project_from_dict(loaded_data)
            updates["__msg__"] = (
                f"โ… เนเธซเธฅเธ”เนเธเธฃเน€เธเธเธ•เนเธชเธณเน€เธฃเนเธ! "
                f"๐“… เธเธฑเธเธ—เธถเธเน€เธกเธทเนเธญ: {loaded_data.get('saved_timestamp', 'N/A')[:19]}"
            )
            st.session_state["_pending_load"] = updates
            st.session_state["_last_loaded_file_id"] = file_id
            st.rerun()
        except json.JSONDecodeError as e:
            st.sidebar.error(f"โ เนเธเธฅเน JSON เนเธกเนเธ–เธนเธเธ•เนเธญเธ: {e}")
        except Exception as e:
            st.sidebar.error(f"โ เนเธกเนเธชเธฒเธกเธฒเธฃเธ–เนเธซเธฅเธ”เนเธเธฅเนเนเธ”เน: {e}")

# Reset all
st.sidebar.markdown("---")
st.sidebar.caption(f"App Version {VERSION}")

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 2 โ€” RESULTS & PROFILE โ•โ•โ•โ•โ•โ•โ•โ•
with tab2:
    mc = st.columns(5)
    mc[0].metric("Method", method)
    mc[1].metric("ฮฒ [1/m]",       f"{beta:.3f}"   if (_ready and beta > 0) else "โ€”")
    mc[2].metric("Kv_tip [kN/m]", f"{Kv_tip:,.0f}" if _ready else "โ€”")
    if use_group and spring_output == "Row-based spring table":
        mc[3].metric("p-mult", "Row-based")
    else:
        mc[3].metric("Avg p-mult", f"{Pmult:.3f}")
    mc[4].metric("Nodes",         len(depths) if _ready else "โ€”")
    st.divider()

    r_left, r_right = st.columns([2, 3], gap="medium")
    with r_left:
        st.subheader("Calculation Results")
        if not _ready or df_results.empty:
            st.info("โณ เธเธฃเธธเธ“เธฒเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเนเธซเนเธเธฃเธเธเนเธญเธ เธฃเธฐเธเธเธเธฐเนเธชเธ”เธเธเธฅเธฅเธฑเธเธเนเธ—เธตเนเธเธตเน", icon="๐ชจ")
        else:
            if use_group and spring_output == "Row-based spring table" and not df_row_results.empty:
                st.caption("Row-based output: one spring stiffness per depth, direction, and pile row.")
                st.dataframe(df_row_results.style.format({
                    "Depth [m]":      "{:.2f}",
                    "Trib. L [m]":    "{:.3f}",
                    "fm":             "{:.3f}",
                    "N-SPT":          "{:.0f}",
                    "kh [kN/mเธขเธ“]":    "{:,.0f}",
                    "kh [kN/m3]":     "{:,.0f}",
                    "Deq [m]":        "{:.3f}",
                    "Kspring [kN/m]": "{:,.1f}",
                }), use_container_width=True, height=580)
            else:
                st.caption("Global average output: Ksx and Ksy use the average p-multiplier shown in the sidebar.")
                st.dataframe(df_results.style.format({
                "Depth [m]":    "{:.2f}",
                "kh_x [kN/mยณ]": "{:,.0f}",
                "kh_y [kN/mยณ]": "{:,.0f}",
                "Ksx [kN/m]":   "{:,.1f}",
                "Ksy [kN/m]":   "{:,.1f}"
            }), use_container_width=True, height=580)
    with r_right:
        st.subheader("Soil-Pile Profile with Springs (Global Average)")
        SOIL_COLORS = {"Clay": "#8B6354", "Sand": "#D4AA6A"}
        fig_p = go.Figure()
        x_pile = Deq_x / 2
        x_max  = Deq_x * 4.0

        for _, lrow in df_soil_draw.iterrows():
            fig_p.add_shape(type="rect", x0=-x_max, y0=lrow["Depth_From"],
                            x1=x_max, y1=lrow["Depth_To"],
                            fillcolor=SOIL_COLORS.get(lrow["Soil_Type"], "#888"),
                            opacity=0.25, line_width=0, layer="below")
            mid = (lrow["Depth_From"] + lrow["Depth_To"]) / 2
            fig_p.add_annotation(x=x_max*1.02, y=mid,
                                 text=f"<b>{lrow['Soil_Type']}</b> N={lrow['SPT_N']:.0f}",
                                 showarrow=False, xanchor="left", font=dict(size=10))

        # Scour zone
        if scour_depth > 0:
            fig_p.add_shape(type="rect", x0=-x_max, y0=0, x1=x_max, y1=scour_depth,
                            fillcolor="rgba(200,200,200,0.55)", line_width=0, layer="below")
            fig_p.add_annotation(x=-x_max*0.95, y=scour_depth/2,
                                 text=f"<b>SCOUR</b><br>{scour_depth:.1f} m",
                                 showarrow=False, xanchor="left",
                                 font=dict(size=10, color="#555"))

        fig_p.add_shape(type="rect", x0=-x_pile, y0=0, x1=x_pile, y1=L,
                        line=dict(color="#1a4f8a", width=2),
                        fillcolor="rgba(180,210,240,0.6)", layer="above")
        spr_len = Deq_x * 1.2
        if _ready and not df_results.empty:
            for z, ksx in zip(depths, df_results["Ksx [kN/m]"]):
                if ksx > 1e-3:
                    sx, sy = draw_spring(x_pile, x_pile + spr_len, z)
                    fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines',
                                               line=dict(color='#2166ac', width=1.8),
                                               showlegend=False, hoverinfo='skip'))
                    sx, sy = draw_spring(-x_pile - spr_len, -x_pile, z)
                    fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines',
                                               line=dict(color='#2166ac', width=1.8),
                                               showlegend=False, hoverinfo='skip'))
            fig_p.add_trace(go.Scatter(x=[0]*len(depths), y=depths, mode='markers',
                                        marker=dict(color='red', size=7), name="Node",
                                        hovertemplate='z=%{y:.2f}m<br>Ksx=%{customdata[0]:.0f} kN/m<extra></extra>',
                                        customdata=list(zip(df_results["Ksx [kN/m]"]))))
            # Vertical tip spring
            fig_p.add_trace(go.Scatter(x=[0], y=[L], mode='markers+text',
                                        marker=dict(color='#d62728', size=14, symbol='diamond'),
                                        text=[f"  Kv_tip={Kv_tip:,.0f}"], textposition="middle right",
                                        name="Kv_tip", showlegend=False))
        fig_p.add_hline(y=water_table, line_dash="dash", line_color="#2196F3",
                        line_width=1.5,
                        annotation_text=f"โ–ผ WT @ {water_table:.1f} m",
                        annotation_position="right")
        fig_p.update_layout(height=700,
                            yaxis=dict(autorange="reversed", title="Depth [m]"),
                            xaxis=dict(title="Width [m]"),
                            plot_bgcolor="rgba(248,250,255,1)",
                            margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_p, use_container_width=True)

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 3 โ€” PLOTS โ•โ•โ•โ•โ•โ•โ•โ•
with tab3:
    if not _ready or df_results.empty:
        st.info("โณ เธเธฃเธธเธ“เธฒเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเนเธซเนเธเธฃเธเธเนเธญเธ เธฃเธฐเธเธเธเธฐเนเธชเธ”เธเธเธฃเธฒเธเธ—เธตเนเธเธตเน", icon="๐ชจ")
    else:
      p1, p2 = st.columns(2)
      with p1:
        st.subheader("kh vs Depth (Base kh before p-mult)")
        fig_kh = go.Figure()
        fig_kh.add_trace(go.Scatter(x=df_results["kh_x [kN/mยณ]"], y=df_results["Depth [m]"],
                                    mode='lines+markers', name='kh_x',
                                    line=dict(color='#1a4f8a', width=2), marker=dict(size=5)))
        if not pile_is_round:
            fig_kh.add_trace(go.Scatter(x=df_results["kh_y [kN/mยณ]"], y=df_results["Depth [m]"],
                                        mode='lines+markers', name='kh_y',
                                        line=dict(color='#c0392b', width=2, dash='dash'),
                                        marker=dict(size=5)))
        if water_table < L:
            fig_kh.add_hline(y=water_table, line_dash="dot", line_color="#2196F3",
                             annotation_text=f"WT {water_table:.1f}m", annotation_position="right")
        if scour_depth > 0:
            fig_kh.add_hrect(y0=0, y1=scour_depth, fillcolor="rgba(150,150,150,0.25)",
                             line_width=0, annotation_text="Scour",
                             annotation_position="top left")
        fig_kh.update_layout(height=500,
                             yaxis=dict(autorange="reversed", title="Depth [m]"),
                             xaxis=dict(title="kh [kN/mยณ]"),
                             legend=dict(orientation="h", yanchor="bottom",
                                         y=1.02, xanchor="right", x=1,
                                         bgcolor="rgba(255,255,255,0.85)",
                                         bordercolor="#ccc", borderwidth=1),
                             margin=dict(l=10, r=10, t=60, b=10))
        st.plotly_chart(fig_kh, use_container_width=True)

      with p2:
        st.subheader("Spring Stiffness vs Depth (Global Average)")
        fig_ks = go.Figure()
        fig_ks.add_trace(go.Scatter(x=df_results["Ksx [kN/m]"], y=df_results["Depth [m]"],
                                    mode='lines+markers', name='Ksx',
                                    line=dict(color='#1a4f8a', width=2),
                                    fill='tozerox', fillcolor='rgba(26,79,138,0.08)'))
        if not pile_is_round:
            fig_ks.add_trace(go.Scatter(x=df_results["Ksy [kN/m]"], y=df_results["Depth [m]"],
                                        mode='lines+markers', name='Ksy',
                                        line=dict(color='#c0392b', width=2, dash='dash'),
                                        fill='tozerox', fillcolor='rgba(192,57,43,0.06)'))
        fig_ks.add_trace(go.Scatter(x=[Kv_tip], y=[L], mode='markers', name='Kv_tip',
                                    marker=dict(color='#d62728', size=14, symbol='diamond'),
                                    hovertemplate=f'Kv_tip = {Kv_tip:,.0f} kN/m<extra></extra>'))
        fig_ks.add_annotation(x=Kv_tip, y=L, ax=20, ay=-30,
                              xref='x', yref='y', axref='pixel', ayref='pixel',
                              text=f"<b>Kv_tip = {Kv_tip:,.0f}</b>",
                              showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.2,
                              arrowcolor='#d62728',
                              bgcolor="rgba(255,255,255,0.9)", bordercolor="#d62728",
                              borderwidth=1, borderpad=4,
                              font=dict(size=11, color='#d62728'))
        if water_table < L:
            fig_ks.add_hline(y=water_table, line_dash="dot", line_color="#2196F3",
                             annotation_text=f"WT {water_table:.1f}m", annotation_position="right")
        if scour_depth > 0:
            fig_ks.add_hrect(y0=0, y1=scour_depth, fillcolor="rgba(150,150,150,0.25)",
                             line_width=0, annotation_text="Scour",
                             annotation_position="top left")
        fig_ks.update_layout(height=500,
                             yaxis=dict(autorange="reversed", title="Depth [m]"),
                             xaxis=dict(title="Spring Stiffness [kN/m]"),
                             legend=dict(orientation="h", yanchor="bottom",
                                         y=1.02, xanchor="right", x=1,
                                         bgcolor="rgba(255,255,255,0.85)",
                                         bordercolor="#ccc", borderwidth=1),
                             margin=dict(l=10, r=10, t=60, b=10))
        st.plotly_chart(fig_ks, use_container_width=True)

      st.subheader("ฮฒ โ€” Relative Stiffness")
      if beta > 0:
        st.info(
            f"ฮฒ = (khยทD / 4EpIp)^0.25 = **{beta:.4f} mโปยน** | "
            f"1/ฮฒ = **{1/beta:.2f} m** (characteristic length) | "
            f"Leff = 4/ฮฒ = **{4/beta:.2f} m** | "
            f"{'โ… Long pile (L > 4/ฮฒ)' if L > 4/beta else 'โ ๏ธ Short pile (L < 4/ฮฒ)'}"
        )
      else:
        st.warning("ฮฒ cannot be computed โ€” kh เน€เธเธฅเธตเนเธขเน€เธเนเธ 0 (เธ•เธฃเธงเธเธชเธญเธ scour depth, soil profile)")

    st.divider()
    st.subheader("๐“ เธเธณเนเธเธฐเธเธณเธเธฒเธฃเน€เธฅเธทเธญเธ Method โ€” Engineering Guidance")
    with st.expander("๐” เธ—เธณเนเธก kh เนเธ•เนเธฅเธฐ Method เธเธถเธเนเธซเนเธเนเธฒเธ•เนเธฒเธเธเธฑเธ เนเธฅเธฐเธเธงเธฃเนเธเน Method เนเธ”?", expanded=True):
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("""
**เธฅเธณเธ”เธฑเธเธเนเธฒ kh เนเธกเนเธเธเธ—เธตเน โ€” เธเธถเนเธเธเธฑเธ soil type เนเธฅเธฐ depth**

| เธชเธ–เธฒเธเธเธฒเธฃเธ“เน | เธฅเธณเธ”เธฑเธ kh (เธ•เนเธณ โ’ เธชเธนเธ) |
|-----------|----------------------|
| Soft Clay, z < 5m | Terzaghi โช Vesic < JRA โช Broms |
| Stiff Clay, z > 10m | Terzaghi < JRA โ Vesic โช Broms |
| Loose Sand, z < 3m | Terzaghi < Vesic < JRA โช Broms |
| Dense Sand, z > 10m | Vesic < JRA < Terzaghi โช Broms |

**Broms เนเธซเนเธเนเธฒเธชเธนเธเน€เธชเธกเธญ เน€เธเธฃเธฒเธฐ:**
kh = pu / (0.01D ร— D) เธเธณเธเธงเธ“เธเธฒเธ ultimate resistance
เธ—เธตเน displacement = 1%D เธเธถเนเธเนเธเธฅเน failure เนเธฅเนเธง
**เนเธกเนเนเธเน elastic stiffness** โ’ เธซเนเธฒเธกเนเธเนเน€เธเนเธ spring เนเธ FEA
""")
        with col_g2:
            st.markdown("""
**เธเธณเนเธเธฐเธเธณเธชเธณเธซเธฃเธฑเธเธญเธญเธเนเธเธเน€เธซเธฅเนเธเน€เธชเธฃเธดเธกเน€เธชเธฒเน€เธเนเธก**

| Method | เธเธ—เธเธฒเธ— | เน€เธซเธ•เธธเธเธฅ |
|--------|--------|--------|
| โ… **JRA** | Primary design | Calibrated เธชเธณเธซเธฃเธฑเธเธเธฒเธเธชเธฐเธเธฒเธ, เนเธเน N-SPT เนเธ”เธขเธ•เธฃเธ, DOH/MRTA เธขเธญเธกเธฃเธฑเธ |
| โ–๏ธ **Terzaghi** | Cross-check | Conservative bound, เธ–เนเธฒ JRA vs Terzaghi เธ•เนเธฒเธเธเธฑเธ <50% โ’ เธกเธฑเนเธเนเธเนเธ”เน |
| โ ๏ธ **Vesic** | เธเธฒเธเธเธดเน€เธจเธฉ | เนเธเนเนเธ”เนเน€เธเธเธฒเธฐเธกเธต Es เธเธฒเธ PMT/lab เธเธฃเธดเธ เนเธกเนเนเธเนเธเธฒเธ N-SPT correlation |
| ๐ซ **Broms** | Capacity check เน€เธ—เนเธฒเธเธฑเนเธ | เนเธกเนเน€เธซเธกเธฒเธฐเน€เธเนเธ FEA spring โ’ displacement เธเนเธญเธขเธเธงเนเธฒเธเธฃเธดเธ |

**Workflow เนเธเธฐเธเธณ:**
1. เธเธณเธเธงเธ“เธ”เนเธงเธข JRA โ’ เนเธเนเธญเธญเธเนเธเธ
2. Cross-check เธ”เนเธงเธข Terzaghi โ’ เธ•เธฃเธงเธเธชเธญเธเธเธงเธฒเธกเธชเธกเน€เธซเธ•เธธเธชเธกเธเธฅ
3. เธ–เนเธฒเธเธฅเธ•เนเธฒเธเธเธฑเธ > 50% โ’ เธ•เธฃเธงเธเธชเธญเธ N-SPT เธญเธตเธเธเธฃเธฑเนเธ
4. Report เธฃเธฐเธเธธ: *"JRA method, cross-checked with Terzaghi"*

> **เธซเธกเธฒเธขเน€เธซเธ•เธธ:** เธชเธณเธซเธฃเธฑเธเธ”เธดเธ Soft Bangkok Clay (N=1โ€“4) เนเธเธเนเธงเธ 0โ€“15 m
> เธเนเธฒ kh เธ•เนเธณเธกเธฒเธเธ—เธธเธ method โ€” เธเธถเนเธเธ–เธนเธเธ•เนเธญเธเธ•เธฒเธกเธเธคเธ•เธดเธเธฃเธฃเธกเธเธฃเธดเธเธเธญเธเธ”เธดเธ
""")

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 4 โ€” REINFORCEMENT โ•โ•โ•โ•โ•โ•โ•โ•
with tab4:
    st.header("Pile Design")
    st.caption(
        "Preliminary reinforced concrete pile design using the calculated lateral springs. "
        "This section solves pile-head loading on a Winkler beam, then checks main bars and ties "
        "from the resulting axial force, shear, and moment profiles."
    )

    if not _ready or df_results.empty:
        st.info("Please complete the soil profile first. Pile Design uses the calculated spring table.")
    else:
        source_options = ["Global average spring"]
        if use_group and not df_row_results.empty:
            source_options.append("Row-based spring")

        sel1, sel2, sel3 = st.columns([1.2, 1.0, 1.0])
        spring_source = sel1.selectbox(
            "Spring source",
            source_options,
            help="Global average uses Ksx/Ksy from the main results table. Row-based uses one selected pile row."
        )
        design_direction = sel2.selectbox(
            "Loading direction",
            ["X", "Y"],
            help="X loading uses Ksx and bending about the Y-axis. Y loading uses Ksy and bending about the X-axis."
        )

        if spring_source == "Row-based spring":
            row_limit = int(nx) if design_direction == "X" else int(ny)
            design_row = sel3.selectbox(
                "Pile row",
                list(range(1, row_limit + 1)),
                help="Select the pile row to design when using the row-based spring table."
            )
        else:
            design_row = 1
            sel3.metric("Pile row", "Average")

        load_c1, load_c2, load_c3 = st.columns(3)
        Pu_kN = load_c1.number_input(
            "Factored axial compression Pu [kN]",
            min_value=0.0,
            value=1500.0,
            step=100.0,
            help="Compression-positive axial load used along the pile length."
        )
        Hu_kN = load_c2.number_input(
            "Pile-head shear H [kN]",
            min_value=0.0,
            value=200.0,
            step=10.0,
            help="Applied lateral shear at pile head for the selected direction."
        )
        Mu_kNm = load_c3.number_input(
            "Pile-head moment M [kN-m]",
            min_value=0.0,
            value=100.0,
            step=10.0,
            help="Applied bending moment at pile head."
        )

        det1, det2, det3, det4 = st.columns(4)
        cover_mm = det1.number_input("Clear cover [mm]", min_value=40, max_value=150, value=75, step=5)
        main_bar = det2.selectbox("Main bar", list(REBAR_DB.keys()), index=2)
        tie_bar = det3.selectbox("Tie / spiral bar", list(REBAR_DB.keys()), index=1)
        tie_spacing_mm = det4.number_input("Provided tie spacing [mm]", min_value=50, max_value=400, value=150, step=10)

        if pile_type == "Round":
            cfg1, cfg2 = st.columns(2)
            n_main_bars = cfg1.number_input("Number of main bars", min_value=4, max_value=40, value=10, step=1)
            n_tie_legs = cfg2.number_input("Equivalent tie legs", min_value=2, max_value=8, value=2, step=1)
            n_b_face = n_h_face = None
        else:
            cfg1, cfg2, cfg3 = st.columns(3)
            n_b_face = cfg1.number_input("Bars on B face", min_value=2, max_value=20, value=4, step=1)
            n_h_face = cfg2.number_input("Bars on H face", min_value=2, max_value=20, value=4, step=1)
            n_tie_legs = cfg3.number_input("Tie legs", min_value=2, max_value=8, value=2, step=1)
            n_main_bars = None

        if spring_source == "Global average spring":
            spring_df = df_results.copy()
            spring_k = (
                spring_df["Ksx [kN/m]"].to_numpy(dtype=float)
                if design_direction == "X"
                else spring_df["Ksy [kN/m]"].to_numpy(dtype=float)
            )
            spring_note = f"Using {'Ksx' if design_direction == 'X' else 'Ksy'} from the global average spring table."
        else:
            spring_df = df_row_results[
                (df_row_results["Direction"] == design_direction)
                & (df_row_results["Row No."] == int(design_row))
            ].sort_values("Node").copy()
            spring_k = spring_df["Kspring [kN/m]"].to_numpy(dtype=float)
            if spring_df.empty:
                spring_note = "No row-based spring data available."
            else:
                row_pos = spring_df["Row Position"].iloc[0]
                spring_note = f"Using row-based spring for {design_direction} direction, row {design_row} ({row_pos})."

        EI = Ep * (Ipy if design_direction == "X" else Ipx)
        design_ok = len(spring_k) == len(depths) and np.any(np.abs(spring_k) > 1e-9)
        response_error = None
        if design_ok:
            try:
                disp_m, theta_rad, soil_reaction_kN, shear_kN, moment_kNm = solve_pile_lateral_response(
                    depths, spring_k, EI, head_shear=Hu_kN, head_moment=Mu_kNm
                )
            except Exception as exc:
                response_error = str(exc)
                design_ok = False
        else:
            response_error = "The selected spring source is empty or does not align with the pile depth nodes."

        st.info(spring_note)
        if response_error:
            st.error(f"Pile response analysis could not run: {response_error}")
        else:
            axial_kN = np.full(len(depths), float(Pu_kN), dtype=float)
            design_profile = pd.DataFrame({
                "Node": np.arange(1, len(depths) + 1),
                "Depth [m]": depths,
                "Axial P [kN]": axial_kN,
                "Shear V [kN]": shear_kN,
                "Moment M [kN-m]": moment_kNm,
                "Disp. y [mm]": disp_m * 1000.0,
                "Soil Reaction [kN]": soil_reaction_kN,
            })

            Mu_max = float(np.max(np.abs(moment_kNm))) if len(moment_kNm) else 0.0
            Vu_max = float(np.max(np.abs(shear_kN))) if len(shear_kN) else 0.0
            ymax_mm = float(np.max(np.abs(disp_m)) * 1000.0) if len(disp_m) else 0.0
            z_mu = float(depths[np.argmax(np.abs(moment_kNm))]) if len(moment_kNm) else 0.0
            z_vu = float(depths[np.argmax(np.abs(shear_kN))]) if len(shear_kN) else 0.0

            design_summary = calc_pile_design_summary(
                pile_type, D, B, H, fc, cover_mm, main_bar, tie_bar,
                design_direction, Pu_kN, Vu_max, Mu_max, n_main_bars,
                n_b_face, n_h_face, n_tie_legs, as_ratio_rec
            )
            tie_ok = float(tie_spacing_mm) <= float(design_summary["s_rec_mm"]) + 1e-9

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Max |M| [kN-m]", f"{Mu_max:,.1f}", f"at z = {z_mu:.2f} m")
            m2.metric("Max |V| [kN]", f"{Vu_max:,.1f}", f"at z = {z_vu:.2f} m")
            m3.metric("Axial Pu [kN]", f"{Pu_kN:,.1f}")
            m4.metric("Max |y| [mm]", f"{ymax_mm:,.2f}")

            left_design, right_design = st.columns([1.15, 1.0], gap="large")
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
                    ("Main bar", f"{design_summary['total_main_bars']} {main_bar}", f"fy = {design_summary['fy_main']:.0f} MPa"),
                    ("Provided As", f"{design_summary['as_provided_mm2']:,.0f} mm2", f"{design_summary['as_provided_mm2'] / 100.0:,.1f} cm2"),
                    ("Required As", f"{design_summary['as_req_total_mm2']:,.0f} mm2", f"{design_summary['as_req_total_mm2'] / 100.0:,.1f} cm2"),
                    ("Tie bar", tie_bar, f"fy = {design_summary['fy_tie']:.0f} MPa"),
                    ("Recommended tie spacing", f"{design_summary['s_rec_mm']:.0f} mm", f"provided = {tie_spacing_mm:.0f} mm"),
                ]
                st.table(pd.DataFrame(section_info, columns=["Item", "Value", "Note"]))

            with right_design:
                st.subheader("Preliminary Design Check")
                ck1, ck2 = st.columns(2)
                ck1.metric(
                    "Main bars",
                    "OK" if design_summary["main_ok"] else "Increase bars",
                    f"As prov / req = {design_summary['as_provided_mm2'] / max(design_summary['as_req_total_mm2'], 1e-6):.2f}"
                )
                ck2.metric(
                    "Tie spacing",
                    "OK" if tie_ok else "Tighter spacing",
                    f"Rec. <= {design_summary['s_rec_mm']:.0f} mm"
                )
                st.markdown(
                    f"""
                    - **Main bar steel:** `{design_summary['total_main_bars']} {main_bar}`
                    - **Provided main steel:** `{design_summary['as_provided_mm2']:,.0f} mm2`
                    - **Minimum steel from spring guide:** `{design_summary['as_min_mm2']:,.0f} mm2`
                    - **Axial steel demand:** `{design_summary['as_req_axial_mm2']:,.0f} mm2`
                    - **Flexural steel demand:** `{design_summary['as_req_flex_mm2']:,.0f} mm2`
                    - **Effective depth d:** `{design_summary['d_eff_mm']:.0f} mm`
                    - **Concrete shear strength Vc:** `{design_summary['vc_n'] / 1000.0:,.1f} kN`
                    """
                )
                st.caption(design_summary["shear_status"])
                if not design_summary["main_ok"]:
                    st.warning("Provided main reinforcement is below the preliminary requirement. Increase bar size or quantity.")
                if not tie_ok:
                    st.warning("Provided tie spacing is larger than the preliminary recommended spacing.")

            st.subheader("Pile Force Diagrams")
            g1, g2, g3 = st.columns(3)

            fig_axial = go.Figure()
            fig_axial.add_trace(go.Scatter(
                x=design_profile["Axial P [kN]"],
                y=design_profile["Depth [m]"],
                mode="lines+markers",
                line=dict(color="#2c7fb8", width=2),
                marker=dict(size=5),
                name="P"
            ))
            fig_axial.update_layout(
                height=420,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(autorange="reversed", title="Depth [m]"),
                xaxis=dict(title="Axial Compression P [kN]"),
                title=dict(text="Axial Force Along Pile", font=dict(size=14))
            )
            g1.plotly_chart(fig_axial, use_container_width=True)

            fig_m = go.Figure()
            fig_m.add_trace(go.Scatter(
                x=design_profile["Moment M [kN-m]"],
                y=design_profile["Depth [m]"],
                mode="lines+markers",
                line=dict(color="#d95f0e", width=2),
                marker=dict(size=5),
                fill="tozerox",
                fillcolor="rgba(217,95,14,0.10)",
                name="M"
            ))
            fig_m.update_layout(
                height=420,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(autorange="reversed", title="Depth [m]"),
                xaxis=dict(title="Moment M [kN-m]"),
                title=dict(text="Bending Moment Along Pile", font=dict(size=14))
            )
            g2.plotly_chart(fig_m, use_container_width=True)

            fig_v = go.Figure()
            fig_v.add_trace(go.Scatter(
                x=design_profile["Shear V [kN]"],
                y=design_profile["Depth [m]"],
                mode="lines+markers",
                line=dict(color="#31a354", width=2),
                marker=dict(size=5),
                fill="tozerox",
                fillcolor="rgba(49,163,84,0.10)",
                name="V"
            ))
            fig_v.update_layout(
                height=420,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(autorange="reversed", title="Depth [m]"),
                xaxis=dict(title="Shear V [kN]"),
                title=dict(text="Shear Force Along Pile", font=dict(size=14))
            )
            g3.plotly_chart(fig_v, use_container_width=True)

            with st.expander("Detailed pile design table", expanded=False):
                st.dataframe(
                    design_profile.style.format({
                        "Depth [m]": "{:.2f}",
                        "Axial P [kN]": "{:,.1f}",
                        "Shear V [kN]": "{:,.1f}",
                        "Moment M [kN-m]": "{:,.1f}",
                        "Disp. y [mm]": "{:,.3f}",
                        "Soil Reaction [kN]": "{:,.1f}",
                    }),
                    use_container_width=True,
                    height=420
                )

            with st.expander("Design assumptions and workflow", expanded=False):
                st.markdown(
                    """
                    1. This section uses the already-calculated lateral spring profile from the main spring analysis.
                    2. Axial compression is treated as constant along pile length from the applied `Pu`.
                    3. Shear and moment are obtained from a free-head Winkler beam model using the selected spring source.
                    4. Main bar demand is checked with a simplified axial-plus-flexure estimate and the recommended steel ratio from the spring stiffness guide.
                    5. Tie spacing is checked with a preliminary ACI-style shear calculation and confinement spacing limit.
                    6. Final pile design should still be confirmed with project-specific load combinations, interaction checks, detailing rules, and code provisions.
                    """
                )

        st.divider()
        st.caption("Legacy spring-based reinforcement guidance is kept below for reference.")
    st.header("Legacy Spring-Based Reinforcement Guidance")
    st.markdown("""
    เธเธฒเธฃเธญเธญเธเนเธเธเน€เธซเธฅเนเธเน€เธชเธฃเธดเธกเน€เธชเธฒเน€เธเนเธก (Longitudinal เนเธฅเธฐ Shear/Links) เธ เธฒเธขเนเธ•เนเนเธฃเธเธ”เนเธฒเธเธเนเธฒเธเธเธฑเนเธ **Spring Stiffness (kh) เธกเธตเธเธฅเนเธ”เธขเธ•เธฃเธ** เนเธ”เธข:
    - **Shear Force (V):** เธเธถเนเธเธเธฑเธเธเธงเธฒเธกเธเธฑเธเธเธญเธ Bending Moment Diagram เธเธถเนเธเธเธถเนเธเธเธฑเธ **เธเนเธฒ kh เธ”เนเธฒเธเธเธญเธ (Outer Layers)**
    - **Longitudinal Rebar:** เธ•เนเธญเธเธเธงเธเธเธธเธก Crack Width เธเธถเนเธเธเธถเนเธเธเธฑเธ Service Moment เธ—เธตเนเนเธ”เนเธเธฒเธเธเนเธฒ **kh เธ”เนเธฒเธเนเธ (Inner Layers)**
    """)

    st.subheader("1. เธเธฒเธฃเน€เธฅเธทเธญเธ Method เธชเธณเธซเธฃเธฑเธเธญเธญเธเนเธเธเน€เธซเธฅเนเธเน€เธชเธฃเธดเธก (Workflow เนเธเธฐเธเธณ)")
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        st.success("""
        **โ… เนเธเนเธเนเธฒเธเธฒเธ JRA Method เน€เธเนเธเธซเธฅเธฑเธ**
        **เน€เธซเธ•เธธเธเธฅ:**
        1. เธเนเธฒ JRA เธญเธขเธนเนเธฃเธฐเธซเธงเนเธฒเธ Conservative (Terzaghi) เนเธฅเธฐ Unconservative (Broms)
        2. เนเธซเน Moment Envelope เธ—เธตเนเธชเธกเธเธฃเธดเธเธ—เธตเนเธชเธธเธ”เธชเธณเธซเธฃเธฑเธเธ”เธดเธเนเธเนเธ—เธข
        3. เธ–เธนเธเธ•เธฃเธงเธเธชเธญเธเนเธฅเธฐเธขเธทเธเธขเธฑเธเนเธ”เธข MRTA เนเธฅเธฐ DOH เธชเธณเธซเธฃเธฑเธเธเธฒเธเธเธฃเธดเธ
        """)
    with col_w2:
        st.info("""
        **โ–๏ธ เนเธเน Terzaghi Cross-check เน€เธเธทเนเธญเธเธงเธฒเธกเธเธฅเธญเธ”เธ เธฑเธข**
        - เนเธซเนเธเนเธฒ kh เธ•เนเธณ โ’ Moment เธชเธนเธเธเธถเนเธ โ’ เน€เธซเธฅเนเธเน€เธชเธฃเธดเธกเธกเธฒเธเธเธถเนเธ
        - เธซเธฒเธเธเนเธฒเน€เธซเธฅเนเธเธเธฒเธ JRA เนเธเธฅเนเน€เธเธตเธขเธเธเธฑเธ Min. Rebar (ACI) โ’ เนเธกเนเธเธณเน€เธเนเธเธ•เนเธญเธเนเธเน Terzaghi
        - เธซเธฒเธเธเนเธฒเน€เธซเธฅเนเธเธเธฒเธ JRA เธ•เนเธณเธกเธฒเธ โ’ เธเธงเธฃเธ•เธฃเธงเธเธชเธญเธเธ”เนเธงเธข Terzaghi เน€เธเธทเนเธญเธเธงเธฒเธกเธเธฅเธญเธ”เธ เธฑเธข
        """)

    st.divider()
    st.subheader("2. Minimum Longitudinal Reinforcement (เธญเธดเธเธเธฒเธ Crack Control & ACI)")
    st.caption("เธชเธณเธซเธฃเธฑเธเน€เธชเธฒเน€เธเนเธกเธ—เธตเนเธ—เธเนเธฃเธเธ”เนเธฒเธเธเนเธฒเธ เธเนเธฒ Min. As เนเธกเนเนเธเนเน€เธเธตเธขเธ 1% เธเธญเธ Ap เธ•เธฒเธก ACI 10.5.1 เนเธ•เนเธเธงเธฃเธเธงเธเธเธธเธกเธเธฒเธ Serviceability (Crack Width)")

    if not _ready or df_results.empty:
        st.info("โณ เธเธฃเธธเธ“เธฒเธเธฃเธญเธเธเนเธญเธกเธนเธฅเธเธฑเนเธเธ”เธดเธเนเธซเนเธเธฃเธเธเนเธญเธ เธฃเธฐเธเธเธเธฐเนเธชเธ”เธเธเธณเนเธเธฐเธเธณเธ—เธตเนเธเธตเน", icon="๐ชจ")
    else:
        st.write(f"**เธชเธ เธฒเธเธ”เธดเธเธเธฒเธ Input:** kh เธ—เธตเนเธเธดเธงเธ”เธดเธ = {kh_max_surface:,.0f} kN/mยณ | kh เธเธฑเนเธเธฅเธถเธ = {kh_min_deep:,.0f} kN/mยณ")

        if kh_max_surface <= 5000:
            st.warning(f"๐  **Soft Clay / Very Low kh:** เนเธฃเธเธ”เธฑเธเธ”เธดเธเธขเธฑเธเนเธกเนเธชเธฒเธกเธฒเธฃเธ–เธฃเธฑเธเนเธฃเธเธ”เนเธฒเธเธเนเธฒเธเนเธ”เนเธ”เธต เธเธงเธฃเนเธเน As >= **{as_ratio_rec*100:.1f}%** เธเธญเธ Ap เน€เธเธทเนเธญเธเธงเธเธเธธเธกเธฃเธญเธขเธฃเนเธฒเธง")
        elif kh_max_surface <= 15000:
            st.success(f"๐ข **Medium Stiff Clay / Low kh:** เนเธเน As >= **{as_ratio_rec*100:.1f}%** เธเธญเธ Ap (เธ•เธฒเธก ACI 10.5.1 เธ—เธฑเนเธงเนเธ)")
        else:
            st.success(f"๐”ต **Stiff Clay / Sand (High kh):** เธ”เธดเธเธเนเธงเธขเธฃเธฑเธเนเธฃเธเนเธ”เนเธ”เธต เธชเธฒเธกเธฒเธฃเธ–เนเธเน As >= **{as_ratio_rec*100:.1f}%** เธเธญเธ Ap เนเธ”เน")

        c1, c2, c3 = st.columns(3)
        c1.metric("Ap [mยฒ]", f"{Ap:.4f}")
        c2.metric("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%")
        c3.metric("Min. As [mยฒ]", f"{As_min:.4f}", help="เธเนเธฒเธเธทเนเธเธ—เธตเนเน€เธซเธฅเนเธเน€เธชเธฃเธดเธกเธเธฑเนเธเธ•เนเธณเธ—เธตเนเนเธเธฐเธเธณเธชเธณเธซเธฃเธฑเธเธญเธญเธเนเธเธ")

    st.divider()
    st.subheader("3. Shear Reinforcement (Links) Guidance")
    st.markdown("""
    เธเธฒเธฃเธซเธฒเธเธฃเธดเธกเธฒเธ“เน€เธซเธฅเนเธเธฅเธนเธเธ•เธฑเนเธ (Shear Links) เธเธถเนเธเธเธฑเธ **Maximum Shear Force (Vu)** เธ—เธตเนเน€เธเธดเธ”เธเธถเนเธเธ เธฒเธขเนเธเน€เธชเธฒเน€เธเนเธก
    - **Vu เธชเธนเธเธชเธธเธ”เธกเธฑเธเน€เธเธดเธ”เธ—เธตเนเธฃเธฐเธ”เธฑเธเธเธทเนเธเธ”เธดเธ (Ground Level) เธซเธฃเธทเธญเธเนเธงเธ Scour Depth**
    - เธเนเธฒ Vu เธเธถเนเธเธเธฑเธเธเนเธฒ **kh เธ—เธตเนเธฃเธฐเธ”เธฑเธเธเธดเธงเธ”เธดเธเธเธฑเนเธเธเธญเธเธชเธธเธ”** (เน€เธเธฃเธฒเธฐเธ”เธดเธเธเธฑเนเธเธเธญเธเธเธฐเธชเธฃเนเธฒเธเนเธฃเธเธ•เนเธฒเธเธชเธนเธเธชเธธเธ”เธ•เธญเธเน€เธฃเธดเนเธกเน€เธเธฅเธทเนเธญเธเธ—เธตเน)
    - **เธซเธฒเธเนเธเน JRA:** เนเธซเนเธ”เธถเธเธเนเธฒ `Ksx` เธ—เธตเน Node เนเธฃเธเน (เธ เธฒเธขเนเธ•เน Scour) เนเธเนเธชเนเนเธเนเธเธฃเนเธเธฃเธก FEA (SAP2000/ETABS) เน€เธเธทเนเธญเธซเธฒ Diagram เธเธญเธ Vu เนเธฅเนเธงเธเนเธญเธขเธญเธญเธเนเธเธ Links เธ•เธฒเธก ACI 318 Chapter 22
    """)

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 5 โ€” REFERENCE โ•โ•โ•โ•โ•โ•โ•โ•
with tab5:
    st.subheader("๐“ N-SPT Reference Values")
    st.markdown("### ๐”ต Clay")
    clay_ref = [{"Consistency": cons, "Typical N": db["N"], "cu [kPa]": db["cu"],
                 "Es [kPa]": db["Es"], "ฮฑ (Bowles)": db["alpha"]}
                for cons, db in SOIL_DB["Clay"].items()]
    st.dataframe(pd.DataFrame(clay_ref), use_container_width=True, hide_index=True)
    st.markdown("### ๐ก Sand")
    sand_ref = [{"Density": cons, "Typical N": db["N"], "ฯ [ยฐ]": db["phi"],
                 "Es [kPa]": db["Es"], "nh wet": db["nh_wet"]}
                for cons, db in SOIL_DB["Sand"].items()]
    st.dataframe(pd.DataFrame(sand_ref), use_container_width=True, hide_index=True)

# โ•โ•โ•โ•โ•โ•โ•โ• TAB 6 โ€” FORMULAS โ•โ•โ•โ•โ•โ•โ•โ•
with tab6:
    st.subheader("๐“ Formulas & References")
    st.markdown("**1. JRA:** $k_h = \\dfrac{E_0}{B_0} \\left(\\dfrac{D}{B_0}\\right)^{-3/4}$, $B_0=0.3$ m")
    st.markdown("**2. Terzaghi (Sand):** $k_h = \\dfrac{n_h \\cdot z}{D}$  |  **(Clay):** $k_h = \\dfrac{\\alpha \\cdot c_u}{D}$")
    st.markdown("**3. Vesic 1961:** $k_h = 0.65 \\left(\\dfrac{E_s D^4}{E_p I_p}\\right)^{1/12} \\cdot \\dfrac{E_s}{D(1-\\nu^2)}$")
    st.markdown("**4. Broms 1964:** Sand $p_u = 3 K_p \\gamma' z D$  |  Clay $p_u = 9 c_u D$  |  $k_h = p_u / (0.01 D \\cdot D)$")
    st.markdown("**5. Spring:** $K_{sx} = k_{h,x} \\cdot D_x \\cdot \\Delta z \\cdot f_m$")
    st.markdown("**6. Beta:** $\\beta = \\left(\\dfrac{k_h \\cdot D}{4 E_p I_p}\\right)^{1/4}$")
    st.markdown("**7. Vertical tip (JRA):** $K_{v,tip} = \\dfrac{1}{3}\\dfrac{E_0}{B_0}\\left(\\dfrac{D}{B_0}\\right)^{-3/4} A_p$")

    st.divider()
    st.markdown("""
    ### ๐“ Convention Notes
    - **Loading width convention** (this app): X-loading uses $D_x = B$, Y-loading uses $D_y = H$ โ€” JRA-style
    - **For X-direction loading:** pile bends about Y-axis โ’ $I_p = I_y$ (used in $\\beta$ and Vesic)
    - **Global Average spring:** uses average group p-multiplier $P_{mult}$ for $K_{sx}$ and $K_{sy}$ (single global spring per depth)
    - **Row-based spring table:** uses row-specific $f_m$ for each loading direction and row number; $K_{spring}=k_h \\cdot D_{eq} \\cdot L_{trib} \\cdot f_m$
    - **Sand below water table:** $E_0 \\times 0.6$ for JRA (built-in); Vesic uses $E_s \\times 0.6$ likewise

    ### ๐“ References
    1. **JRA (2002, 2017)** โ€” *Specifications for Highway Bridges*, Japan Road Association
    2. **Bowles, J.E. (1997)** โ€” *Foundation Analysis and Design*, 5th ed., McGraw-Hill (Tables 9-1, 9-3)
    3. **Vesic, A.S. (1961)** โ€” *Beams on Elastic Subgrade and the Winkler's Hypothesis*
    4. **Broms, B.B. (1964)** โ€” *Lateral Resistance of Piles in Cohesive/Cohesionless Soils*
    5. **AASHTO LRFD (2020)** โ€” Table 10.7.2.4-1 (p-multiplier)
    6. **FHWA-NHI-16-009** โ€” *Design and Construction of Driven Pile Foundations*, ยง9.4
    7. **Reese, L.C. & Van Impe, W.F. (2011)** โ€” *Single Piles and Pile Groups Under Lateral Loading*
    """)
