import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import json

st.set_page_config(page_title="Pile Soil Spring Calculator", layout="wide", page_icon="🏗️")

VERSION = 8

# ─────────────────────────────────────────────
#  SAVE / LOAD PROJECT FUNCTIONS
# ─────────────────────────────────────────────
def save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, s_D, nx, ny,
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
        "soil_layers": soil_layers.to_dict(orient="records"),
        "saved_timestamp": pd.Timestamp.now().isoformat(),
    }

def load_project_from_dict(data):
    """Load project parameters from dictionary and return session_state updates"""
    updates = {}

    # Map JSON keys to session_state keys
    key_map = {
        "design_stage": "stage",
        "method": "method",
        "pile_type": "pile_type",
        "D": "D",
        "B": "B",
        "H": "H",
        "L": "L",
        "fc": "fc",
        "node_spacing": "dl",
        "nu": "nu",
        "water_table": "wt",
        "scour_depth": "scour",
        "use_group": "use_group",
        "s_D": "sD",
        "nx": "nx",
        "ny": "ny",
    }

    for json_key, st_key in key_map.items():
        if json_key in data:
            updates[st_key] = data[json_key]

    # Rebuild soil layers DataFrame
    if "soil_layers" in data and len(data["soil_layers"]) > 0:
        df = pd.DataFrame(data["soil_layers"])
        # Ensure column types
        for col in ["Depth_From", "Depth_To", "SPT_N", "Es", "cu", "phi", "Gamma"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        updates["soil_layers"] = df

    return updates

# ─────────────────────────────────────────────
#  SESSION STATE & DEFAULTS
# ─────────────────────────────────────────────
if 'version' not in st.session_state or st.session_state.version < VERSION:
    st.session_state.clear()
    st.session_state.version = VERSION

# ─────────────────────────────────────────────
#  REFERENCE DATABASE
# ─────────────────────────────────────────────
SOIL_DB = {
    "Clay": {
        "Very Soft":       {"N": 1,  "cu": 6,   "Es":  1500, "Gamma": 15, "alpha": 12,  "desc": "N<2,  cu<12 kPa, Bangkok Soft Clay"},
        "Soft":            {"N": 3,  "cu": 18,  "Es":  3000, "Gamma": 16, "alpha": 24,  "desc": "N=2–4, cu=12–25 kPa"},
        "Medium Stiff":    {"N": 6,  "cu": 36,  "Es":  8000, "Gamma": 17, "alpha": 48,  "desc": "N=5–8, cu=25–50 kPa"},
        "Stiff":           {"N": 12, "cu": 72,  "Es": 18000, "Gamma": 18, "alpha": 96,  "desc": "N=9–15, cu=50–100 kPa"},
        "Very Stiff":      {"N": 25, "cu": 150, "Es": 40000, "Gamma": 19, "alpha": 150, "desc": "N=16–30, cu=100–200 kPa"},
        "Hard":            {"N": 40, "cu": 250, "Es": 75000, "Gamma": 20, "alpha": 200, "desc": "N>30, cu>200 kPa"},
    },
    "Sand": {
        "Very Loose":  {"N": 2,  "phi": 26, "Es":  8000, "Gamma": 15, "nh_dry": 2200,  "nh_wet": 1300,  "desc": "N<4,   very loose, Dr<20%"},
        "Loose":       {"N": 7,  "phi": 30, "Es": 20000, "Gamma": 17, "nh_dry": 6600,  "nh_wet": 4000,  "desc": "N=4–10, loose, Dr=20–40%"},
        "Medium Dense":{"N": 20, "phi": 33, "Es": 45000, "Gamma": 18, "nh_dry": 17600, "nh_wet": 10500, "desc": "N=11–30, medium, Dr=40–60%"},
        "Dense":       {"N": 40, "phi": 37, "Es": 80000, "Gamma": 19, "nh_dry": 35000, "nh_wet": 21000, "desc": "N=31–50, dense, Dr=60–80%"},
        "Very Dense":  {"N": 55, "phi": 41, "Es":120000, "Gamma": 20, "nh_dry": 56000, "nh_wet": 34000, "desc": "N>50,  very dense, Dr>80%"},
    }
}

# Predefined Soil Profiles for Bangkok Area
SOIL_PROFILES = {
    "กรุงเทพฯ - โปรไฟล์ทั่วไป (General)": pd.DataFrame([
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
    "กรุงเทพฯ - สุขุมวิท/รัชดา (ซอฟต์เคลย์หนา)": pd.DataFrame([
        {"Depth_From": 0.0,  "Depth_To": 3.0,  "Soil_Type": "Clay", "Consistency": "Soft",         "SPT_N": 2,  "Es":  2000, "cu": 12,  "phi": 0, "Gamma": 15.5},
        {"Depth_From": 3.0,  "Depth_To": 12.0, "Soil_Type": "Clay", "Consistency": "Very Soft",    "SPT_N": 1,  "Es":  1200, "cu": 8,   "phi": 0, "Gamma": 14.5},
        {"Depth_From": 12.0, "Depth_To": 18.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 8,  "Es": 10000, "cu": 45,  "phi": 0, "Gamma": 16.5},
        {"Depth_From": 18.0, "Depth_To": 24.0, "Soil_Type": "Sand", "Consistency": "Medium Dense", "SPT_N": 25, "Es": 55000, "cu": 0,   "phi": 33, "Gamma": 19.0},
        {"Depth_From": 24.0, "Depth_To": 30.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 40, "Es": 90000, "cu": 0,   "phi": 36, "Gamma": 20.0},
    ]),
    "กรุงเทพฯ - ธนบุรี/ปิ่นเกล้า (ดินเหนียวแข็งตื้น)": pd.DataFrame([
        {"Depth_From": 0.0,  "Depth_To": 4.0,  "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 8,  "Es": 12000, "cu": 50,  "phi": 0, "Gamma": 17.5},
        {"Depth_From": 4.0,  "Depth_To": 10.0, "Soil_Type": "Clay", "Consistency": "Stiff",        "SPT_N": 14, "Es": 22000, "cu": 85,  "phi": 0, "Gamma": 18.5},
        {"Depth_From": 10.0, "Depth_To": 15.0, "Soil_Type": "Clay", "Consistency": "Very Stiff",   "SPT_N": 22, "Es": 35000, "cu": 130, "phi": 0, "Gamma": 19.0},
        {"Depth_From": 15.0, "Depth_To": 20.0, "Soil_Type": "Sand", "Consistency": "Dense",        "SPT_N": 35, "Es": 80000, "cu": 0,   "phi": 36, "Gamma": 20.0},
    ]),
    "ตารางว่าง (ใส่เอง)": pd.DataFrame([
        {"Depth_From": 0.0, "Depth_To": 10.0, "Soil_Type": "Clay", "Consistency": "Medium Stiff", "SPT_N": 6, "Es": 8000, "cu": 36, "phi": 0, "Gamma": 17.0}
    ])
}

PMULT_TABLE = {
    "Lead Row": {3.0: 0.80, 4.0: 0.90, 5.0: 1.00, 6.0: 1.00},
    "2nd Row":  {3.0: 0.40, 4.0: 0.625, 5.0: 0.85, 6.0: 1.00},
    "3rd Row+": {3.0: 0.30, 4.0: 0.50,  5.0: 0.70, 6.0: 1.00},
}

# ─────────────────────────────────────────────
#  ENGINEERING FUNCTIONS
# ─────────────────────────────────────────────
def get_alpha_clay(N):
    """Get alpha factor for clay based on N-SPT (Bowles 1997)"""
    if N <= 1:   return 12
    elif N <= 4:  return 24
    elif N <= 8:  return 48
    elif N <= 15: return 96
    elif N <= 30: return 150
    else:         return 200

def calc_kh_jra(N, D, design_stage, soil_type, below_water):
    """
    JRA (Japan Road Association) - E0 = 2800N (Normal) or 5600N (Seismic)
    kh = (E0/B0) × (D/B0)^(-3/4), B0 = 0.3 m
    Sand below water: E0 × 0.6
    """
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N
    if soil_type == "Sand" and below_water:
        E0 *= 0.6
    kh = (E0 / B0) * (D / B0) ** (-0.75)
    return kh, E0

def get_nh_terzaghi(N, below_water):
    """Terzaghi (1955) nh values for sand [kN/m³/m]"""
    if N < 10:   return 4000  if below_water else 7000
    elif N < 30: return 12000 if below_water else 21000
    else:        return 34000 if below_water else 56000

def calc_kh_terzaghi(N, soil_type, D, z_mid, below_water, consistency="Medium Stiff"):
    """
    Terzaghi (1955) / Bowles (1997)
    Sand: kh = nh × z / D
    Clay: kh = α × cu / D
    """
    if soil_type == "Sand":
        nh = get_nh_terzaghi(N, below_water)
        z_use = max(z_mid, 0.1)
        kh = nh * z_use / D
    else:
        cu = 6.25 * N
        alpha = get_alpha_clay(N)
        kh = alpha * cu / D
    return kh

def calc_kh_vesic(Es_kPa, D, Ep, Ip, nu=0.35):
    """
    Vesic (1961) - Beam on elastic foundation
    kh = 0.65 × (Es·D⁴/Ep·Ip)^(1/12) × Es/(D·(1-ν²))
    """
    Es = float(Es_kPa)
    if Ep * Ip <= 0 or Es <= 0 or D <= 0:
        return 0.0
    kh = 0.65 * (Es * D**4 / (Ep * Ip))**(1/12) * Es / (D * (1 - nu**2))
    return kh

def calc_kh_broms(soil_type, N, z, D, gamma_eff=8, phi=None, cu=None):
    """
    Broms (1964) - Ultimate lateral resistance method
    Sand: pu = 3·Kp·γ·z·D
    Clay: pu = 9·cu·D
    """
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
    """AASHTO LRFD Table 10.7.2.4-1 p-multiplier by interpolation"""
    t = PMULT_TABLE[row_pos]
    keys = sorted(t.keys())
    if s_D_ratio <= keys[0]:  return t[keys[0]]
    if s_D_ratio >= keys[-1]: return t[keys[-1]]
    return float(np.interp(s_D_ratio, keys, [t[k] for k in keys]))

def calc_pile_props(pile_type, D, B, H, fc):
    """Concrete pile properties. Ep = 4700√fc [MPa] → kN/m²"""
    Ep = 4700 * np.sqrt(fc) * 1000
    if pile_type == "Round":
        Ap = np.pi * D**2 / 4
        Ipx = np.pi * D**4 / 64
        Ipy = Ipx
        Deq_x = D
        Deq_y = D
    else:
        Ap = B * H
        Ipx = B * H**3 / 12  # Bending about X-axis
        Ipy = H * B**3 / 12  # Bending about Y-axis
        Deq_x = B
        Deq_y = H
    return Ap, Ipx, Ipy, Ep, Deq_x, Deq_y

def calc_kv_tip(N_tip, D, Ap, design_stage):
    """Vertical tip spring (JRA-based) - kv = lateral/3"""
    B0 = 0.3
    E0_factor = 5600 if design_stage == "Seismic" else 2800
    E0 = E0_factor * N_tip
    kv = (E0 / B0) * (D / B0)**(-0.75) / 3.0
    Kv_tip = kv * Ap
    return Kv_tip, kv

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

def pile_section_figure(pile_type, D, B, H, Ap, Ipx, Ipy, Ep, compact=False):
    """Pile cross-section figure with dimension annotations and axis labels"""
    fig = go.Figure()
    pad = max(D, B, H) * 0.7
    dim_offset = max(D, B, H) * 0.35
    axis_len = max(D, B, H) * 0.5  # ความยาวของแกน

    if pile_type == "Round":
        theta = np.linspace(0, 2*np.pi, 200)
        r = D / 2
        cx = np.cos(theta) * r
        cy = np.sin(theta) * r
        fig.add_trace(go.Scatter(x=cx, y=cy, fill='toself', fillcolor='rgba(100,160,220,0.35)',
                                 line=dict(color='#1a4f8a', width=2.5), showlegend=False, hoverinfo='skip'))
        ay = -r - dim_offset
        fig.add_annotation(ax=-r, ay=ay, x=r, y=ay, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(ax=r, ay=ay, x=-r, y=ay, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(x=0, y=ay, text=f"<b>D = {D:.2f} m</b>", showarrow=False, yshift=-16, font=dict(size=13, color='#1a4f8a'))
        # CG marker
        fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers', marker=dict(color='red', size=12, symbol='x'), showlegend=False, name='CG'))
        lim = r + pad
        title_text = f"Round Pile  D = {D:.2f} m"
    else:
        x0, x1 = -B/2, B/2
        y0, y1 = -H/2, H/2
        fig.add_trace(go.Scatter(x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0], fill='toself', fillcolor='rgba(100,160,220,0.35)',
                                 line=dict(color='#1a4f8a', width=2.5), showlegend=False, hoverinfo='skip'))
        ay_b = y0 - dim_offset
        fig.add_annotation(ax=x0, ay=ay_b, x=x1, y=ay_b, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(ax=x1, ay=ay_b, x=x0, y=ay_b, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#1a4f8a')
        fig.add_annotation(x=0, y=ay_b, text=f"<b>B = {B:.2f} m</b>", showarrow=False, yshift=-16, font=dict(size=13, color='#1a4f8a'))
        ax_h = x1 + dim_offset
        fig.add_annotation(ax=ax_h, ay=y0, x=ax_h, y=y1, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#c0392b')
        fig.add_annotation(ax=ax_h, ay=y1, x=ax_h, y=y0, xref='x', yref='y', axref='x', ayref='y',
                           arrowhead=2, arrowsize=1.2, arrowwidth=1.5, arrowcolor='#c0392b')
        fig.add_annotation(x=ax_h, y=0, text=f"<b>H = {H:.2f} m</b>", showarrow=False, xshift=22, font=dict(size=13, color='#c0392b'))
        # CG marker
        fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers', marker=dict(color='red', size=12, symbol='x'), showlegend=False, name='CG'))
        lim = max(B, H) / 2 + pad
        title_text = f"Square/Rect Pile  B×H = {B:.2f}×{H:.2f} m"

    # ── เพิ่มแกน X และ Y ที่จุด CG ──
    # แกน X (ลากผ่าน CG ไปทางขวา)
    fig.add_annotation(ax=0, ay=0, x=axis_len, y=0, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    # ป้าย X
    fig.add_annotation(x=axis_len * 0.9, y=axis_len * 0.15, text="<b>X</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')

    # แกน Y (ลากผ่าน CG ไปขึ้นบน)
    fig.add_annotation(ax=0, ay=0, x=0, y=axis_len, xref='x', yref='y', axref='x', ayref='y',
                       arrowhead=2, arrowsize=1.0, arrowwidth=2.0, arrowcolor='#333333', showarrow=True)
    # ป้าย Y
    fig.add_annotation(x=axis_len * 0.15, y=axis_len * 0.85, text="<b>Y</b>", showarrow=False,
                       font=dict(size=14, color='#333333', family='Arial Black'), xref='x', yref='y')

    # CG Label
    fig.add_annotation(x=0, y=-axis_len * 0.2, text="<b>CG</b>", showarrow=False,
                       font=dict(size=10, color='red'), xref='x', yref='y', textangle=0)

    props_text = (f"Ap = {Ap:.4f} m²<br>Ix = {Ipx:.5f} m⁴<br>Iy = {Ipy:.5f} m⁴<br>Ep = {Ep/1000:.0f} MPa")
    fig.add_annotation(x=lim * 0.98, y=lim * 0.72, xref='x', yref='y', text=props_text, showarrow=False, align='left',
                       bgcolor='rgba(255,255,255,0.85)', bordercolor='#aaa', borderwidth=1, borderpad=6, font=dict(size=11, family='monospace'))
    h = 380 if compact else 460
    fig.update_layout(title=dict(text=title_text, font=dict(size=14, color='#1a4f8a')),
                      xaxis=dict(scaleanchor='y', scaleratio=1, range=[-lim, lim], zeroline=False, showgrid=True, gridcolor='rgba(180,180,180,0.3)'),
                      yaxis=dict(range=[-lim, lim], zeroline=False, showgrid=True, gridcolor='rgba(180,180,180,0.3)'),
                      height=h, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor='rgba(245,248,255,0.8)')
    return fig

def calculate_rebar_params(df_results, Ap):
    """Calculate rebar design parameters"""
    kh_max_surface = df_results["kh_x [kN/m³]"].iloc[1] if len(df_results) > 1 else 0
    kh_min_deep = df_results["kh_x [kN/m³]"].iloc[-1] if len(df_results) > 0 else 0

    if kh_max_surface <= 5000:
        as_ratio_rec = 0.015  # 1.5% for Soft Clay
    elif kh_max_surface <= 15000:
        as_ratio_rec = 0.010  # 1.0% for Medium Stiff Clay
    else:
        as_ratio_rec = 0.008  # 0.8% for Stiff Clay / Sand

    As_min = Ap * as_ratio_rec
    return kh_max_surface, kh_min_deep, as_ratio_rec, As_min

def build_excel(df_results, df_soil, N_tip, Kv_tip, Ap, Ep, Ipx, Ipy, B, H, L, fc,
                node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta,
                kh_max_surface, kh_min_deep, as_ratio_rec, As_min):
    """Build Excel file with all calculation results"""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        wb = writer.book
        fmt_title  = wb.add_format({'bold': True, 'font_size': 12, 'bg_color': '#1a4f8a', 'font_color': 'white', 'border': 1})
        fmt_header = wb.add_format({'bold': True, 'bg_color': '#BDD7EE', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        fmt_num    = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        fmt_bold   = wb.add_format({'bold': True, 'border': 1})
        fmt_info   = wb.add_format({'italic': True, 'font_color': '#555555'})

        # ── Sheet 1: Lateral Springs ──
        ws1 = wb.add_worksheet("Lateral Springs")
        ws1.write(0, 0, f"Lateral Soil Spring Stiffness — Method: {method}", fmt_title)
        ws1.write(1, 0, f"Pile: B={B:.2f}m H={H:.2f}m L={L:.1f}m f'c={fc:.0f}MPa ΔL={node_spacing:.2f}m p-mult={Pmult:.3f}", fmt_info)
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

        # ── Sheet 2: Vertical Tip Spring ──
        ws2 = wb.add_worksheet("Vertical Tip Spring")
        ws2.write(0, 0, "Vertical Tip Spring Stiffness", fmt_title)
        tip_data = [
            ("Parameter", "Value", "Unit"),
            ("N-SPT at pile tip", N_tip, "blow/30cm"),
            ("E0 (at tip)", (2800 if design_stage=="Normal" else 5600)*N_tip, "kN/m²"),
            ("Pile tip area Ap", Ap, "m²"),
            ("Kv_tip (vertical spring)", round(Kv_tip, 1), "kN/m"),
            ("Design Stage", design_stage, "-"),
        ]
        for ri, row in enumerate(tip_data):
            for ci, val in enumerate(row):
                ws2.write(2+ri, ci, val, fmt_bold if ci==0 else (fmt_num if isinstance(val, (int, float)) else fmt_bold))
        ws2.set_column(0, 0, 28)
        ws2.set_column(1, 1, 18)
        ws2.set_column(2, 2, 12)

        # ── Sheet 3: Summary ──
        ws3 = wb.add_worksheet("Summary")
        ws3.write(0, 0, "Project Summary & Pile Properties", fmt_title)
        summary = [
            ("Pile Width B [m]", B, "m"),
            ("Pile Height H [m]", H, "m"),
            ("Pile Length L [m]", L, "m"),
            ("f'c [MPa]", fc, "MPa"),
            ("Ep [kN/m²]", round(Ep, 0), "kN/m²"),
            ("Ap [m²]", round(Ap, 5), "m²"),
            ("Ix (Bending about X) [m⁴]", round(Ipx, 6), "m⁴"),
            ("Iy (Bending about Y) [m⁴]", round(Ipy, 6), "m⁴"),
            ("Node Spacing ΔL [m]", node_spacing, "m"),
            ("kh Method", method, "-"),
            ("Design Stage", design_stage, "-"),
            ("Water Table [m]", water_table, "m"),
            ("Scour Depth [m]", scour_depth, "m"),
            ("p-multiplier", Pmult, "-"),
            ("β (Characteristic Length) [1/m]", round(beta, 4), "1/m"),
            ("Kv_tip [kN/m]", round(Kv_tip, 1), "kN/m"),
        ]
        for ri, (k, v, u) in enumerate(summary):
            ws3.write(2+ri, 0, k, fmt_bold)
            ws3.write(2+ri, 1, v, fmt_num if isinstance(v, float) else fmt_bold)
            ws3.write(2+ri, 2, u, fmt_bold)
        ws3.set_column(0, 0, 34)
        ws3.set_column(1, 1, 18)
        ws3.set_column(2, 2, 10)

        # ── Sheet 4: Soil Profile ──
        df_soil.to_excel(writer, sheet_name="Soil Profile", index=False)
        ws4 = writer.sheets["Soil Profile"]
        ws4.set_column(0, len(df_soil.columns)-1, 15)

        # ── Sheet 5: Rebar Design Guide ──
        ws5 = wb.add_worksheet("Rebar Design Guide")
        ws5.write(0, 0, "Pile Reinforcement Design Guide (Based on Spring Results)", fmt_title)
        rebar_data = [
            ("Parameter", "Value", "Remark / Reference"),
            ("Surface kh_x [kN/m³]", round(kh_max_surface, 1), "Used to evaluate soil stiffness condition"),
            ("Deep kh_x [kN/m³]", round(kh_min_deep, 1), "Stiffness at pile tip layer"),
            ("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%", "Based on Crack Control / ACI 318"),
            ("Minimum As [m²]", round(As_min, 4), "As = Ap x Ratio"),
            ("Min. Rebar Requirement", "See ACI 10.5.1 & 21.6", "Max of Code min. or Crack control min."),
        ]
        for ri, row in enumerate(rebar_data):
            for ci, val in enumerate(row):
                fmt_use = fmt_bold if ci==0 else fmt_num if isinstance(val, (int, float)) else fmt_info
                ws5.write(2+ri, ci, val, fmt_use)
        ws5.set_column(0, 0, 32)
        ws5.set_column(1, 1, 20)
        ws5.set_column(2, 2, 50)

    buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────────
#  SESSION STATE & DEFAULTS
# ─────────────────────────────────────────────
if 'soil_layers' not in st.session_state:
    st.session_state.soil_layers = SOIL_PROFILES["กรุงเทพฯ - โปรไฟล์ทั่วไป (General)"].copy()

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
st.sidebar.title("🏗️ Pile Spring Calculator")
st.sidebar.markdown("---")

st.sidebar.header("1. Project Settings")
c1, c2 = st.sidebar.columns(2)
design_stage = c1.selectbox("Design Stage", ["Normal", "Seismic"], key="stage")
method       = c2.selectbox("kh Method",    ["JRA", "Terzaghi", "Vesic 1961", "Broms 1964"], key="method")

_method_tips = {
    "JRA": ("✅ แนะนำสำหรับออกแบบ", "success", "Primary method สำหรับงานสะพาน/highway\n• ใช้ N-SPT โดยตรง\n• Calibrated สำหรับดินเอเชีย\n• ยอมรับโดย DOH, MRTA, การรถไฟฯ"),
    "Terzaghi": ("⚖️ Cross-check", "info", "Conservative bound — kh ต่ำกว่า JRA\n• ใช้เทียบกับ JRA ถ้าต่างกัน <50% ถือว่าปลอดภัย"),
    "Vesic 1961": ("⚠️ ต้องการ Es Lab", "warning", "ต้องการ Es จาก PMT/lab จริงเท่านั้น\n❌ ห้ามใช้ Es จาก N-SPT กับ Soft Clay"),
    "Broms 1964": ("🚫 สำหรับ Capacity", "error", "ให้ค่า kh สูงเกินจริง (ใกล้ Failure)\n❌ ห้ามใช้เป็น spring ออกแบบเหล็กเสริม"),
}
_tip = _method_tips[method]
with st.sidebar.expander(f"{_tip[0]}", expanded=True):
    if _tip[1] == "success": st.success(_tip[2])
    elif _tip[1] == "info": st.info(_tip[2])
    elif _tip[1] == "warning": st.warning(_tip[2])
    else: st.error(_tip[2])

st.sidebar.header("2. Pile Properties")
pile_type = st.sidebar.selectbox("Pile Type", ["Round", "Square/Rectangular"], key="pile_type")
if pile_type == "Round":
    D = st.sidebar.number_input("Diameter D [m]", 0.1, 5.0, 0.6, 0.05, key="D")
    B = H = D
else:
    c3, c4 = st.sidebar.columns(2)
    B = c3.number_input("Width B [m]",  0.1, 5.0, 0.35, 0.05, key="B")
    H = c4.number_input("Height H [m]", 0.1, 5.0, 0.35, 0.05, key="H")
    D = max(B, H)

L            = st.sidebar.number_input("Pile Length L [m]",     1.0, 120.0, 25.0, 1.0,  key="L")
fc           = st.sidebar.number_input("Concrete f'c [MPa]",   15.0, 100.0, 28.0, 1.0,  key="fc")
node_spacing = st.sidebar.number_input("Node Spacing ΔL [m]",   0.25,  5.0,  1.0, 0.25, key="dl")

if method == "Vesic 1961":
    nu = st.sidebar.number_input("Poisson Ratio ν", 0.10, 0.50, 0.35, 0.05, key="nu")
else:
    nu = 0.35

st.sidebar.header("3. Site Conditions")
water_table = st.sidebar.number_input("Water Table Depth [m]", 0.0, float(L), 1.0,  0.5, key="wt")
scour_depth = st.sidebar.number_input("Scour Depth [m]",       0.0, float(L), 0.0,  0.5, key="scour")

st.sidebar.header("4. Group Effect")
use_group = st.sidebar.checkbox("Apply Group Effect (p-multiplier)", key="use_group")
if use_group:
    s_D = st.sidebar.number_input("Pile Spacing s/D", 2.0, 12.0, 3.0, 0.5, key="sD")
    gc1, gc2 = st.sidebar.columns(2)
    nx = gc1.number_input("Piles in X", 1, 20, 3, 1, key="nx")
    ny = gc2.number_input("Piles in Y", 1, 20, 3, 1, key="ny")
    n_total = int(nx * ny)

    def fm_row_list(n_piles, s_over_D):
        fms = []
        for i in range(n_piles):
            pos = "Lead Row" if i == 0 else ("2nd Row" if i == 1 else "3rd Row+")
            fms.append(calc_pmultiplier(s_over_D, pos))
        return fms

    fms_x = fm_row_list(int(nx), s_D)
    fms_y = fm_row_list(int(ny), s_D)
    fm_vals = [min(fms_x[ix], fms_y[iy]) for iy in range(int(ny)) for ix in range(int(nx))]
    Pmult = sum(fm_vals) / n_total if n_total > 0 else 1.0

    if s_D >= 6.0:
        st.sidebar.success("s/D ≥ 6 → fm = 1.00 (no reduction)")
        Pmult = 1.0
    else:
        st.sidebar.info(
            f"**Average fm = {Pmult:.3f}**  (ใช้ค่าเดียวทุกต้น)\n\n"
            f"nx={int(nx)}, ny={int(ny)}, n={n_total} piles\n\n"
            f"Ref: FHWA-NHI-16-009 §9.4"
        )
        with st.sidebar.expander("📋 fm breakdown per row"):
            st.caption("**X-direction rows** (loading → X)")
            for i, fm in enumerate(fms_x):
                lbl = "Lead" if i==0 else ("2nd" if i==1 else "3rd+")
                st.write(f"  Row {i+1} ({lbl}): fm = {fm:.3f}")
            st.caption("**Y-direction rows** (loading → Y)")
            for i, fm in enumerate(fms_y):
                lbl = "Lead" if i==0 else ("2nd" if i==1 else "3rd+")
                st.write(f"  Row {i+1} ({lbl}): fm = {fm:.3f}")
else:
    Pmult = 1.0

pile_is_round = (pile_type == "Round")
Ap, Ipx, Ipy, Ep, Deq_x, Deq_y = calc_pile_props("Round" if pile_is_round else "Square", D, B, H, fc)

# ─────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────
st.title("Pile Lateral Soil Spring Stiffness Calculator")
st.caption("Units: kN, m  |  All kh methods: JRA / Terzaghi 1955 / Vesic 1961 / Broms 1964")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 Input & Pile Section", "📊 Results & Profile", "📈 kh & Spring Plots",
    "🔧 Pile Reinforcement Design", "📚 N-SPT Reference", "📐 Formulas & References"
])

# ══════════════════════════════════════════════
#  TAB 1  —  SOIL INPUT
# ══════════════════════════════════════════════
with tab1:
    left_col, right_col = st.columns([3, 2], gap="large")
    with right_col:
        st.subheader("📐 Pile Cross-Section")
        st.plotly_chart(pile_section_figure("Round" if pile_is_round else "Square", D, B, H, Ap, Ipx, Ipy, Ep, compact=True), use_container_width=True)
        st.markdown("**Section Properties**")
        mc1, mc2 = st.columns(2)
        mc1.metric("Ap [m²]", f"{Ap:.4f}"); mc2.metric("Ep [MPa]", f"{Ep/1000:.0f}")
        mc3, mc4 = st.columns(2)
        mc3.metric("Ix [m⁴]", f"{Ipx:.5f}"); mc4.metric("Iy [m⁴]", f"{Ipy:.5f}")

    with left_col:
        st.subheader("🪨 Soil Layer Input")

        with st.expander("🗂️ เลือกโปรไฟล์ดินตัวอย่าง (Predefined Profiles)", expanded=False):
            selected_profile = st.selectbox("เลือกโปรไฟล์:", list(SOIL_PROFILES.keys()))
            st.dataframe(SOIL_PROFILES[selected_profile], use_container_width=True, hide_index=True)
            st.info("**อ้างอิง:** โปรไฟล์กรุงเทพฯ สรุปจากชั้นดินเฉลี่ยทางภูมิศาสตร์ (กรมทรัพยากรธรณี, จุฬาฯ, ธรรมศาสตร์) ใช้สำหรับ Preliminary Design เท่านั้น")
            if st.button("✅ ใช้โปรไฟล์นี้", use_container_width=True, type="primary"):
                st.session_state.soil_layers = SOIL_PROFILES[selected_profile].copy()
                st.rerun()

        clay_opts = list(SOIL_DB["Clay"].keys())
        sand_opts = list(SOIL_DB["Sand"].keys())
        all_cons  = clay_opts + sand_opts

        edited_df = st.data_editor(
            st.session_state.soil_layers,
            num_rows="dynamic",
            use_container_width=True,
            key="soil_editor",
            column_config={
                "Depth_From":   st.column_config.NumberColumn("From [m]",   format="%.1f", width="small"),
                "Depth_To":     st.column_config.NumberColumn("To [m]",     format="%.1f", width="small"),
                "Soil_Type":    st.column_config.SelectboxColumn("Type",    options=["Clay","Sand"], width="small"),
                "Consistency":  st.column_config.SelectboxColumn("Consist.", options=all_cons, width="medium"),
                "SPT_N":        st.column_config.NumberColumn("N-SPT",      min_value=0, max_value=200, width="small"),
                "Es":           st.column_config.NumberColumn("Es [kPa]",   min_value=100, width="small"),
                "cu":           st.column_config.NumberColumn("cu [kPa]",   min_value=0, width="small"),
                "phi":          st.column_config.NumberColumn("φ [°]",      min_value=0, max_value=50, width="small"),
                "Gamma":        st.column_config.NumberColumn("γ [kN/m³]",  min_value=10, max_value=25, width="small"),
            }
        )
        st.session_state.soil_layers = edited_df.copy()

# ─────────────────────────────────────────────
#  MAIN CALCULATION
# ─────────────────────────────────────────────
df_soil = st.session_state.soil_layers
depths  = np.arange(0, L + 1e-9, node_spacing)
results = []

for z in depths:
    mask  = (df_soil["Depth_From"] <= z) & (df_soil["Depth_To"] > z)
    layer = df_soil[mask].iloc[0] if mask.any() else df_soil.iloc[-1]

    soil_type   = layer["Soil_Type"]
    N_val       = float(layer["SPT_N"])
    below_water = z > water_table
    z_mid       = max(z - node_spacing / 2, 0.05)

    if z < scour_depth:
        kh_x = kh_y = E0 = pu = 0.0
    else:
        pu = np.nan
        if method == "JRA":
            kh_x, E0 = calc_kh_jra(N_val, Deq_x, design_stage, soil_type, below_water)
            kh_y, _  = calc_kh_jra(N_val, Deq_y, design_stage, soil_type, below_water)
        elif method == "Terzaghi":
            kh_x = calc_kh_terzaghi(N_val, soil_type, Deq_x, z_mid, below_water)
            kh_y = calc_kh_terzaghi(N_val, soil_type, Deq_y, z_mid, below_water)
            E0 = 2800 * N_val
        elif method == "Vesic 1961":
            Es_kPa = float(layer.get("Es", 20000))
            # FIXED: Apply water table reduction for Sand (same as JRA)
            if soil_type == "Sand" and below_water:
                Es_kPa *= 0.6
            # FIXED: X-loading uses Ipy (bending about Y-axis), Y-loading uses Ipx
            kh_x = calc_kh_vesic(Es_kPa, Deq_x, Ep, Ipy, nu)
            kh_y = calc_kh_vesic(Es_kPa, Deq_y, Ep, Ipx, nu)
            E0 = Es_kPa
        else:
            gamma_v = float(layer.get("Gamma", 18))
            gamma_eff = gamma_v - 10 if below_water else gamma_v
            cu  = float(layer.get("cu",  6.25*N_val)) if soil_type == "Clay" else None
            phi = float(layer.get("phi", 28)) if soil_type == "Sand" else None
            kh_x, pu = calc_kh_broms(soil_type, N_val, z, Deq_x, gamma_eff, phi, cu)
            kh_y, _  = calc_kh_broms(soil_type, N_val, z, Deq_y, gamma_eff, phi, cu)
            E0 = float(layer.get("Es", 20000))

    Ksx = kh_x * Deq_x * node_spacing * Pmult
    Ksy = kh_y * Deq_y * node_spacing * Pmult

    results.append({
        "Node":       int(round(z / node_spacing)),
        "Depth [m]":  round(z, 3),
        "Soil_Type":  soil_type,
        "N-SPT":      N_val,
        "kh_x [kN/m³]": round(kh_x, 1),
        "kh_y [kN/m³]": round(kh_y, 1),
        "Ksx [kN/m]": round(Ksx, 1),
        "Ksy [kN/m]": round(Ksy, 1),
        "pu [kN/m]":  round(pu, 1) if not np.isnan(pu) else np.nan,
    })

df_results = pd.DataFrame(results)
N_tip    = float(df_soil.iloc[-1]["SPT_N"])
Kv_tip, kv_tip = calc_kv_tip(N_tip, max(Deq_x, Deq_y), Ap, design_stage)

# FIXED: Calculate beta correctly for Rectangular piles
Ip_for_beta = Ipy if not pile_is_round else Ipx
kh_avg = df_results["kh_x [kN/m³]"].replace(0, np.nan).mean()
beta   = (kh_avg * Deq_x / (4 * Ep * Ip_for_beta))**0.25 if (Ep * Ip_for_beta > 0 and kh_avg > 0) else 0

# Calculate rebar parameters
kh_max_surface, kh_min_deep, as_ratio_rec, As_min = calculate_rebar_params(df_results, Ap)

# ── Sidebar Export Button ──
st.sidebar.header("5. Export")
excel_data = build_excel(
    df_results, df_soil, N_tip, Kv_tip, Ap, Ep, Ipx, Ipy, B, H, L, fc,
    node_spacing, method, design_stage, water_table, scour_depth, Pmult, beta,
    kh_max_surface, kh_min_deep, as_ratio_rec, As_min
)
st.sidebar.download_button(
    "📥 Download Excel (.xlsx)",
    data=excel_data,
    file_name=f"PileSpring_{method}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

# ── SAVE / LOAD PROJECT ──
st.sidebar.header("6. Save / Load Project")
st.sidebar.markdown("💾 **SAVE:** บันทึกพารามิเตอร์ทั้งหมดเป็นไฟล์ JSON")
st.sidebar.markdown("📂 **OPEN:** โหลดไฟล์ที่บันทึกไว้กลับมาใช้งาน")

# Default values for group effect if not enabled
_default_s_D = st.session_state.get("sD", 3.0)
_default_nx = st.session_state.get("nx", 3)
_default_ny = st.session_state.get("ny", 3)

# SAVE button
project_data = save_project_to_dict(
    design_stage, method, pile_type, D, B, H, L, fc, node_spacing, nu,
    water_table, scour_depth, use_group, _default_s_D, _default_nx, _default_ny,
    st.session_state.soil_layers, VERSION
)
json_str = json.dumps(project_data, indent=2, ensure_ascii=False)
st.sidebar.download_button(
    "💾 SAVE Project (.json)",
    data=json_str,
    file_name=f"PileProject_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
    mime="application/json",
    use_container_width=True
)

# OPEN button with file uploader
st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader(
    "📂 OPEN Project File",
    type=["json"],
    help="เลือกไฟล์ .json ที่บันทึกไว้จากปุ่ม SAVE ด้านบน"
)

if uploaded_file is not None:
    try:
        loaded_data = json.load(uploaded_file)
        updates = load_project_from_dict(loaded_data)

        # Apply all updates to session_state
        for key, value in updates.items():
            st.session_state[key] = value

        st.sidebar.success(f"✅ โหลดโปรเจกต์สำเร็จ!\n📅 บันทึกเมื่อ: {loaded_data.get('saved_timestamp', 'N/A')[:19]}")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ ไม่สามารถโหลดไฟล์ได้: {str(e)}")

# ══════════════════════════════════════════════
#  TAB 2  —  RESULTS TABLE + PROFILE
# ══════════════════════════════════════════════
with tab2:
    mc = st.columns(5)
    mc[0].metric("Method", method)
    mc[1].metric("β [1/m]", f"{beta:.3f}")
    mc[2].metric("Kv_tip [kN/m]", f"{Kv_tip:,.0f}")
    mc[3].metric("p-mult", f"{Pmult:.3f}")
    mc[4].metric("Nodes", len(depths))
    st.divider()

    r_left, r_right = st.columns([2, 3], gap="medium")
    with r_left:
        st.subheader("Calculation Results")
        st.dataframe(df_results.style.format({"Depth [m]": "{:.2f}", "kh_x [kN/m³]": "{:,.0f}", "kh_y [kN/m³]": "{:,.0f}", "Ksx [kN/m]": "{:,.1f}", "Ksy [kN/m]": "{:,.1f}"}), use_container_width=True, height=580)
    with r_right:
        st.subheader("Soil-Pile Profile with Springs")
        SOIL_COLORS = {"Clay": "#8B6354", "Sand": "#D4AA6A"}
        fig_p = go.Figure()
        x_pile = Deq_x / 2; x_max = Deq_x * 4.0
        for _, lrow in df_soil.iterrows():
            fig_p.add_shape(type="rect", x0=-x_max, y0=lrow["Depth_From"], x1=x_max, y1=lrow["Depth_To"], fillcolor=SOIL_COLORS[lrow["Soil_Type"]], opacity=0.25, line_width=0, layer="below")
            mid = (lrow["Depth_From"] + lrow["Depth_To"]) / 2
            fig_p.add_annotation(x=x_max*1.02, y=mid, text=f"<b>{lrow['Soil_Type']}</b> N={lrow['SPT_N']:.0f}", showarrow=False, xanchor="left", font=dict(size=10))
        fig_p.add_shape(type="rect", x0=-x_pile, y0=0, x1=x_pile, y1=L, line=dict(color="#1a4f8a", width=2), fillcolor="rgba(180,210,240,0.6)", layer="above")
        spr_len = Deq_x * 1.2
        for z, ksx in zip(depths, df_results["Ksx [kN/m]"]):
            if ksx > 1e-3:
                sx, sy = draw_spring(x_pile, x_pile + spr_len, z)
                fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines', line=dict(color='#2166ac', width=1.8), showlegend=False, hoverinfo='skip'))
                sx, sy = draw_spring(-x_pile - spr_len, -x_pile, z)
                fig_p.add_trace(go.Scatter(x=sx, y=sy, mode='lines', line=dict(color='#2166ac', width=1.8), showlegend=False, hoverinfo='skip'))
        fig_p.add_trace(go.Scatter(x=[0]*len(depths), y=depths, mode='markers', marker=dict(color='red', size=7), name="Node", hovertemplate='z=%{y:.2f}m<br>Ksx=%{customdata[0]:.0f} kN/m<extra></extra>', customdata=list(zip(df_results["Ksx [kN/m]"]))))
        fig_p.add_hline(y=water_table, line_dash="dash", line_color="#2196F3", line_width=1.5, annotation_text="▼ WT")
        fig_p.update_layout(height=700, yaxis=dict(autorange="reversed", title="Depth [m]"), xaxis=dict(title="Width [m]"), plot_bgcolor="rgba(248,250,255,1)")
        st.plotly_chart(fig_p, use_container_width=True)

# ══════════════════════════════════════════════
#  TAB 3  —  PLOTS
# ══════════════════════════════════════════════
with tab3:
    p1, p2 = st.columns(2)
    with p1:
        st.subheader("kh vs Depth")
        fig_kh = go.Figure()
        fig_kh.add_trace(go.Scatter(
            x=df_results["kh_x [kN/m³]"], y=df_results["Depth [m]"],
            mode='lines+markers', name='kh_x', line=dict(color='#1a4f8a', width=2),
            marker=dict(size=5)
        ))
        if not pile_is_round:
            fig_kh.add_trace(go.Scatter(
                x=df_results["kh_y [kN/m³]"], y=df_results["Depth [m]"],
                mode='lines+markers', name='kh_y', line=dict(color='#c0392b', width=2, dash='dash'),
                marker=dict(size=5)
            ))
        fig_kh.update_layout(
            height=500, yaxis=dict(autorange="reversed", title="Depth [m]"),
            xaxis=dict(title="kh [kN/m³]"),
            legend=dict(x=0.65, y=0.02)
        )
        st.plotly_chart(fig_kh, use_container_width=True)

    with p2:
        st.subheader("Spring Stiffness vs Depth")
        fig_ks = go.Figure()
        fig_ks.add_trace(go.Scatter(
            x=df_results["Ksx [kN/m]"], y=df_results["Depth [m]"],
            mode='lines+markers', name='Ksx', line=dict(color='#1a4f8a', width=2),
            fill='tozerox', fillcolor='rgba(26,79,138,0.08)'
        ))
        if not pile_is_round:
            fig_ks.add_trace(go.Scatter(
                x=df_results["Ksy [kN/m]"], y=df_results["Depth [m]"],
                mode='lines+markers', name='Ksy', line=dict(color='#c0392b', width=2, dash='dash'),
                fill='tozerox', fillcolor='rgba(192,57,43,0.06)'
            ))
        fig_ks.add_trace(go.Scatter(
            x=[Kv_tip], y=[L], mode='markers+text', name=f'Kv_tip',
            marker=dict(color='#d62728', size=14, symbol='diamond'),
            text=[f"Kv={Kv_tip:,.0f}"], textposition="middle right"
        ))
        fig_ks.update_layout(
            height=500, yaxis=dict(autorange="reversed", title="Depth [m]"),
            xaxis=dict(title="Spring Stiffness [kN/m]"),
            legend=dict(x=0.45, y=0.02)
        )
        st.plotly_chart(fig_ks, use_container_width=True)

    st.subheader("β — Relative Stiffness")
    st.info(
        f"β = (kh·D / 4EpIp)^0.25 = **{beta:.4f} m⁻¹** | "
        f"1/β = **{1/beta:.2f} m** (characteristic length) | "
        f"Leff = 4/β = **{4/beta:.2f} m** | "
        f"{'✅ Long pile (L > 4/β)' if L > 4/beta else '⚠️ Short pile (L < 4/β)'}"
        if beta > 0 else "β cannot be computed (check inputs)"
    )

    st.divider()
    st.subheader("📌 คำแนะนำการเลือก Method — Engineering Guidance")
    with st.expander("🔍 ทำไม kh แต่ละ Method จึงให้ค่าต่างกัน และควรใช้ Method ใด?", expanded=True):
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("""
**ลำดับค่า kh ไม่คงที่ — ขึ้นกับ soil type และ depth**

| สถานการณ์ | ลำดับ kh (ต่ำ → สูง) |
|-----------|----------------------|
| Soft Clay, z < 5m | Terzaghi ≪ Vesic < JRA ≪ Broms |
| Stiff Clay, z > 10m | Terzaghi < JRA ≈ Vesic ≪ Broms |
| Loose Sand, z < 3m | Terzaghi < Vesic < JRA ≪ Broms |
| Dense Sand, z > 10m | Vesic < JRA < Terzaghi ≪ Broms |

**Broms ให้ค่าสูงเสมอ เพราะ:**
kh = pu / (0.01D × D) คำนวณจาก ultimate resistance
ที่ displacement = 1%D ซึ่งใกล้ failure แล้ว
**ไม่ใช่ elastic stiffness** → ห้ามใช้เป็น spring ใน FEA
""")
        with col_g2:
            st.markdown("""
**คำแนะนำสำหรับออกแบบเหล็กเสริมเสาเข็ม**

| Method | บทบาท | เหตุผล |
|--------|--------|--------|
| ✅ **JRA** | Primary design | Calibrated สำหรับงานสะพาน, ใช้ N-SPT โดยตรง, DOH/MRTA ยอมรับ |
| ⚖️ **Terzaghi** | Cross-check | Conservative bound, ถ้า JRA vs Terzaghi ต่างกัน <50% → มั่นใจได้ |
| ⚠️ **Vesic** | งานพิเศษ | ใช้ได้เฉพาะมี Es จาก PMT/lab จริง ไม่ใช่จาก N-SPT correlation |
| 🚫 **Broms** | Capacity check เท่านั้น | ไม่เหมาะเป็น FEA spring → displacement น้อยกว่าจริง |

**Workflow แนะนำ:**
1. คำนวณด้วย JRA → ใช้ออกแบบ
2. Cross-check ด้วย Terzaghi → ตรวจสอบความสมเหตุสมผล
3. ถ้าผลต่างกัน > 50% → ตรวจสอบ N-SPT อีกครั้ง
4. Report ระบุ: *"JRA method, cross-checked with Terzaghi"*

> **หมายเหตุ:** สำหรับดิน Soft Bangkok Clay (N=1–4) ในช่วง 0–15 m
> ค่า kh ต่ำมากทุก method — ซึ่งถูกต้องตามพฤติกรรมจริงของดิน
""")

# ══════════════════════════════════════════════
#  TAB 4  —  PILE REINFORCEMENT DESIGN
# ══════════════════════════════════════════════
with tab4:
    st.header("🔧 Recommend Spring for Pile Reinforcement Design")
    st.markdown("""
    การออกแบบเหล็กเสริมเสาเข็ม (Longitudinal และ Shear/Links) ภายใต้แรงด้านข้างนั้น **Spring Stiffness (kh) มีผลโดยตรง** โดย:
    - **Shear Force (V):** ขึ้นกับความชันของ Bending Moment Diagram ซึ่งขึ้นกับ **ค่า kh ด้านนอก (Outer Layers)**
    - **Longitudinal Rebar:** ต้องควบคุม Crack Width ซึ่งขึ้นกับ Service Moment ที่ได้จากค่า **kh ด้านใน (Inner Layers)**
    """)

    st.subheader("1. การเลือก Method สำหรับออกแบบเหล็กเสริม (Workflow แนะนำ)")

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        st.success("""
        **✅ ใช้ค่าจาก JRA Method เป็นหลัก**
        **เหตุผล:**
        1. ค่า JRA อยู่ระหว่าง Conservative (Terzaghi) และ Unconservative (Broms)
        2. ให้ Moment Envelope ที่สมจริงที่สุดสำหรับดินในไทย
        3. ถูกตรวจสอบและยืนยันโดย MRTA และ DOH สำหรับงานจริง
        """)
    with col_w2:
        st.info("""
        **⚖️ ใช้ Terzaghi Cross-check เพื่อความปลอดภัย**
        - ให้ค่า kh ต่ำ → Moment สูงขึ้น → เหล็กเสริมมากขึ้น
        - หากค่าเหล็กจาก JRA ใกล้เคียงกับ Min. Rebar (ACI) → ไม่จำเป็นต้องใช้ Terzaghi
        - หากค่าเหล็กจาก JRA ต่ำมาก → ควรตรวจสอบด้วย Terzaghi เพื่อความปลอดภัย
        """)

    st.divider()
    st.subheader("2. Minimum Longitudinal Reinforcement (อิงจาก Crack Control & ACI)")
    st.caption("สำหรับเสาเข็มที่ทนแรงด้านข้าง ค่า Min. As ไม่ใช่เพียง 1% ของ Ap ตาม ACI 10.5.1 แต่ควรควบคุมจาก Serviceability (Crack Width)")

    st.write(f"**สภาพดินจาก Input:** kh ที่ผิวดิน = {kh_max_surface:,.0f} kN/m³ | kh ชั้นลึก = {kh_min_deep:,.0f} kN/m³")

    if kh_max_surface <= 5000:
        as_ratio_rec = 0.015
        st.warning(f"🟠 **Soft Clay / Very Low kh:** แรงดันดินยังไม่สามารถรับแรงด้านข้างได้ดี ควรใช้ As >= **{as_ratio_rec*100:.1f}%** ของ Ap เพื่อควบคุมรอยร้าว")
    elif kh_max_surface <= 15000:
        as_ratio_rec = 0.010
        st.success(f"🟢 **Medium Stiff Clay / Low kh:** ใช้ As >= **{as_ratio_rec*100:.1f}%** ของ Ap (ตาม ACI 10.5.1 ทั่วไป)")
    else:
        as_ratio_rec = 0.008
        st.success(f"🔵 **Stiff Clay / Sand (High kh):** ดินช่วยรับแรงได้ดี สามารถใช้ As >= **{as_ratio_rec*100:.1f}%** ของ Ap ได้")

    As_min = Ap * as_ratio_rec
    c1, c2, c3 = st.columns(3)
    c1.metric("Ap [m²]", f"{Ap:.4f}")
    c2.metric("Recommended As Ratio", f"{as_ratio_rec*100:.1f}%")
    c3.metric("Min. As [m²]", f"{As_min:.4f}", help="ค่าพื้นที่เหล็กเสริมขั้นต่ำที่แนะนำสำหรับออกแบบ")

    st.divider()
    st.subheader("3. Shear Reinforcement (Links) Guidance")
    st.markdown("""
    การหาปริมาณเหล็กลูกเสีย (Shear Links) ขึ้นกับ **Maximum Shear Force (Vu)** ที่เกิดขึ้นภายในเสาเข็ม
    - **Vu สูงสุดมักเกิดที่ระดับพื้นดิน (Ground Level) หรือช่วง Scour Depth**
    - ค่า Vu ขึ้นกับค่า **kh ที่ระดับผิวดินชั้นนอกสุด** (เพราะดินชั้นนอกจะสร้างแรงต้านสูงสุดตอนเริ่มเคลื่อนที่)
    - **หากใช้ JRA:** ให้ดึงค่า `Ksx` ที่ Node แรกๆ (ภายใต้ Scour) ไปใส่ในโปรแกรม FEA (SAP2000/ETABS) เพื่อหา Diagram ของ Vu แล้วค่อยออกแบบ Links ตาม ACI 318 Chapter 22
    """)

# ══════════════════════════════════════════════
#  TAB 5 & 6  —  REFERENCE & FORMULAS
# ══════════════════════════════════════════════
with tab5:
    st.subheader("📚 N-SPT Reference Values")
    st.markdown("### 🔵 Clay")
    clay_ref = [{"Consistency": cons, "Typical N": db["N"], "cu [kPa]": db["cu"], "Es [kPa]": db["Es"], "α (Bowles)": db["alpha"]} for cons, db in SOIL_DB["Clay"].items()]
    st.dataframe(pd.DataFrame(clay_ref), use_container_width=True, hide_index=True)
    st.markdown("### 🟡 Sand")
    sand_ref = [{"Density": cons, "Typical N": db["N"], "φ [°]": db["phi"], "Es [kPa]": db["Es"], "nh wet": db["nh_wet"]} for cons, db in SOIL_DB["Sand"].items()]
    st.dataframe(pd.DataFrame(sand_ref), use_container_width=True, hide_index=True)

with tab6:
    st.subheader("📐 Formulas & References")
    st.markdown("**1. JRA:** $k_h = \\frac{E_0}{B_0} \\left(\\frac{D}{B_0}\\right)^{-3/4}$")
    st.markdown("**2. Terzaghi (Sand):** $k_h = \\frac{n_h \\cdot z}{D}$  |  **(Clay):** $k_h = \\frac{\\alpha \\cdot c_u}{D}$")
    st.markdown("**3. Vesic:** $k_h = 0.65 \\left(\\frac{E_s D^4}{E_p I_p}\\right)^{1/12} \\cdot \\frac{E_s}{D(1-\\nu^2)}$")
    st.markdown("**4. Spring:** $K_{sx} = k_{h,x} \\cdot D_x \\cdot \\Delta z \\cdot f_m$")
    st.markdown("**5. Beta:** $\\beta = \\left(\\frac{k_h \\cdot D}{4 E_p I_p}\\right)^{1/4}$")
