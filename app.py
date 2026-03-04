"""
=============================================================================
APP STREAMLIT - SIMULACIÓN PARADA DE PLANTA SD18MAR26
Visualizaciones 100% interactivas con Plotly (zoom, hover, filtros)
=============================================================================
Instalación:
    pip install streamlit pandas openpyxl plotly numpy

Ejecución:
    streamlit run app_paro_planta.py
=============================================================================
"""

import io
import warnings
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

INICIO_SD = datetime(2026, 3, 18, 6, 0)

COLORES_CRITICIDAD = {
    "Muy Alta": "#B71C1C",
    "Alta":     "#E53935",
    "Media":    "#FB8C00",
    "Baja":     "#43A047",
}

COLORES_CENTRO = {
    "CUS": "#2196F3", "EPO": "#4CAF50", "PAE": "#FF9800", "MRF": "#9C27B0",
    "LBE": "#F44336", "VSA": "#00BCD4", "CQO": "#795548", "CCA": "#E91E63",
    "GRA": "#607D8B", "CVA": "#FF5722", "TUN": "#009688", "PBE": "#3F51B5",
    "BOG": "#8BC34A", "DEFAULT": "#9E9E9E",
}

CAPACIDAD_RECURSOS = {
    "MECÁNICA": 8, "ELÉCTRICA": 6, "INSTRUMENTACIÓN": 5,
    "TELECOMUNICACIONES": 3, "ENERGÉTICA": 2, "CIVIL": 4,
    "OPERACIONES": 6, "INSPECCIÓN": 3, "CONTROLES": 2,
    "SER": 2, "VLV": 2, "AMBIENTAL": 2, "DEFAULT": 4,
}


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 1: CARGA Y LIMPIEZA
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def cargar_actividades(b: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(b), sheet_name="Lista de Actividades SD", header=0)
    df.columns = df.columns.str.strip().str.replace("\n", " ")
    return df


@st.cache_data(show_spinner=False)
def cargar_pdt(b: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(b), sheet_name="Actividades", header=0)
    df.columns = df.columns.str.strip().str.replace("\n", " ")
    return df


def limpiar_unificar(df_act: pd.DataFrame, df_pdt: pd.DataFrame) -> pd.DataFrame:
    pdt = df_pdt.rename(columns={
        "Centro planificación": "centro",
        "Actividades":          "actividad",
        "Orden":                "orden",
        "Computación":          "computacion",
        "TIEMPO (Hrs)":         "duracion_h",
        "ESTADO":               "estado",
        "ESPECIALIDAD":         "especialidad",
        "EJECUTOR":             "ejecutor",
        "CRITICIDAD":           "criticidad",
        "ASEGURADOR":           "asegurador",
        "Riesgo del Entorno":   "riesgo_texto",
        "Criticidad":           "criticidad_num",
        "Riesgo Entorno":       "riesgo_num",
        "Avance % Act.":        "avance_pct",
        "Valor Global %.":      "valor_global",
        "% ACUM CENTRO":        "acum_centro",
        "% ACUM TOTAL":         "acum_total",
        "RUTA CRITICA":         "ruta_critica",
    })
    pdt = pdt[pdt["actividad"].notna()].copy()
    pdt = pdt[pd.to_numeric(pdt["duracion_h"], errors="coerce") > 0].copy()

    act = df_act.rename(columns={
        "Actividades": "actividad", "Centro planificación": "centro",
        "CRITICIDAD": "criticidad_act", "HSE OCENSA": "hse",
        "INTERFERENCIA": "interferencia", "COMENTARIOS": "comentarios",
    })
    keep = ["actividad", "criticidad_act", "hse", "interferencia", "comentarios"]
    act  = act[[c for c in keep if c in act.columns]].dropna(subset=["actividad"])

    df = pdt.merge(act, on="actividad", how="left")
    df["duracion_h"]     = pd.to_numeric(df["duracion_h"], errors="coerce").fillna(1).clip(1, 50)
    df["criticidad_num"] = pd.to_numeric(df["criticidad_num"], errors="coerce").fillna(2)
    df["riesgo_num"]     = pd.to_numeric(df["riesgo_num"], errors="coerce").fillna(1)
    df["valor_global"]   = pd.to_numeric(df["valor_global"], errors="coerce").fillna(0)
    df["avance_pct"]     = pd.to_numeric(df["avance_pct"], errors="coerce").fillna(0)
    df["criticidad"]     = df["criticidad"].fillna("Baja").str.strip()
    df["ruta_critica"]   = df["ruta_critica"].fillna("NO").str.upper().str.strip()
    df["centro"]         = df["centro"].fillna("GEN").str.strip().str.upper()
    df["estado"]         = df["estado"].fillna("PROGRAMADO").str.strip().str.upper()
    df["especialidad"]   = df["especialidad"].fillna("DEFAULT").str.strip().str.upper()
    df = df.reset_index(drop=True)
    df["id"] = df.index
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 2: SCORING MULTICRITERIO
# ─────────────────────────────────────────────────────────────────────────────

def scoring(df: pd.DataFrame, w_crit, w_riesgo, w_valor, w_dur) -> pd.DataFrame:
    def norm(s):
        mn, mx = s.min(), s.max()
        return pd.Series(np.ones(len(s)), index=s.index) if mx == mn else (s - mn) / (mx - mn)
    df = df.copy()
    df["score"] = (w_crit * norm(df["criticidad_num"])
                 + w_riesgo * norm(df["riesgo_num"])
                 + w_valor * norm(df["valor_global"])
                 - w_dur * norm(df["duracion_h"]))
    df.loc[df["ruta_critica"] == "SI", "score"] += 1.0
    df["score"] += df["criticidad"].map({"Muy Alta": 0.8, "Alta": 0.5, "Media": 0.2, "Baja": 0.0}).fillna(0)
    df["prioridad"] = df["score"].rank(ascending=False, method="first").astype(int)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3: PROGRAMACIÓN GREEDY + RESOURCE LEVELING
# ─────────────────────────────────────────────────────────────────────────────

def programar(df: pd.DataFrame, horizonte: int, riesgo_thr: int) -> pd.DataFrame:
    uso_rec = defaultdict(int)
    uso_cr  = defaultdict(set)
    rows    = []

    for _, act in df.iterrows():
        dur    = max(1, int(act["duracion_h"]))
        esp_k  = str(act["especialidad"])[:25]
        cap    = next((v for k, v in CAPACIDAD_RECURSOS.items() if k in esp_k.upper()), 4)
        alto   = act["criticidad_num"] >= riesgo_thr
        centro = act["centro"]
        inicio = 0

        for t in range(horizonte - dur + 1):
            if any(uso_rec[(esp_k, h)] >= cap for h in range(t, t + dur)):
                continue
            if alto and set(range(t, t + dur)) & uso_cr[centro]:
                continue
            inicio = t
            break

        fin = inicio + dur
        for h in range(inicio, fin):
            uso_rec[(esp_k, h)] += 1
        if alto:
            uso_cr[centro].update(range(inicio, fin))

        inicio_real = INICIO_SD + timedelta(hours=inicio)
        fin_real    = INICIO_SD + timedelta(hours=fin)
        turno_n     = (inicio // 8) + 1
        tmap = {1:"T1 (06-14h)", 2:"T2 (14-22h)", 3:"T3 (22-06h)",
                4:"T4 (06-14h)", 5:"T5 (14-22h)", 6:"T6 (22-06h)"}
        rows.append({**act.to_dict(),
                     "start_sd": inicio, "end_sd": fin,
                     "inicio_real": inicio_real, "fin_real": fin_real,
                     "turno": tmap.get(turno_n, f"T{turno_n}"),
                     "dentro_horizonte": fin <= 36})

    df_r = pd.DataFrame(rows)
    total = df_r["valor_global"].sum()
    df_r["valor_global_norm"] = (df_r["valor_global"] / total) if total > 0 else 1 / len(df_r)
    df_r = df_r.sort_values("end_sd")
    df_r["acum_total_calc"]  = (df_r["valor_global_norm"].cumsum() * 100).round(2)
    df_r["acum_centro_calc"] = (
        df_r.groupby("centro")["valor_global_norm"].cumsum()
        .div(df_r.groupby("centro")["valor_global_norm"].transform("sum"))
        .mul(100).round(2)
    )
    mksp   = df_r["end_sd"].max()
    crit1  = df_r["ruta_critica"] == "SI"
    crit2  = df_r["end_sd"] >= (mksp - 2)
    crit3  = (df_r["criticidad_num"] >= 4) & (df_r["duracion_h"] >= 20)
    df_r["es_critica"] = crit1 | crit2 | crit3
    return df_r


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 4: CURVA S
# ─────────────────────────────────────────────────────────────────────────────

def curva_s(df: pd.DataFrame, horizonte: int = 51) -> pd.DataFrame:
    rows = []
    for h in range(horizonte + 1):
        comp = df[df["end_sd"] <= h]
        av   = comp["valor_global_norm"].sum()
        prog = df[(df["start_sd"] <= h) & (df["end_sd"] > h)]
        if len(prog):
            av += prog.apply(
                lambda r: r["valor_global_norm"] * (h - r["start_sd"]) / max(r["duracion_h"], 1), axis=1
            ).sum()
        rows.append({
            "hora_sd": h,
            "hora_real": INICIO_SD + timedelta(hours=h),
            "avance_acum": round(min(av * 100, 100), 2),
            "acts_completas": len(comp),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 5: GRÁFICAS INTERACTIVAS PLOTLY
# ─────────────────────────────────────────────────────────────────────────────

T = "plotly_dark"  # template global


def plot_gantt(df: pd.DataFrame) -> go.Figure:
    df = df.sort_values(["centro", "start_sd"]).copy()
    df["i_str"] = df["inicio_real"].apply(lambda x: x.strftime("%d/%m/%Y %H:%M") if hasattr(x, "strftime") else "")
    df["f_str"] = df["fin_real"].apply(lambda x: x.strftime("%d/%m/%Y %H:%M") if hasattr(x, "strftime") else "")

    fig = px.timeline(
        df, x_start="inicio_real", x_end="fin_real", y="actividad",
        color="criticidad", color_discrete_map=COLORES_CRITICIDAD,
        custom_data=["centro","especialidad","ejecutor","duracion_h","start_sd","end_sd",
                     "turno","ruta_critica","es_critica","score","criticidad_num",
                     "riesgo_texto","valor_global","i_str","f_str","dentro_horizonte"],
        template=T, title="📅 DIAGRAMA DE GANTT — PARADA DE PLANTA SD18MAR26",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Centro: %{customdata[0]}<br>"
            "Especialidad: %{customdata[1]}<br>"
            "Ejecutor: %{customdata[2]}<br>"
            "Duración: <b>%{customdata[3]}h</b><br>"
            "Inicio: SD%{customdata[4]} · %{customdata[13]}<br>"
            "Fin: SD%{customdata[5]} · %{customdata[14]}<br>"
            "Turno: %{customdata[6]}<br>"
            "Criticidad num: %{customdata[10]}<br>"
            "Riesgo: %{customdata[11]}<br>"
            "RC Orig: %{customdata[7]} · RC Calc: %{customdata[8]}<br>"
            "Score: %{customdata[9]:.3f}<br>"
            "Valor Global: %{customdata[12]:.5f}<br>"
            "Dentro 36H: %{customdata[15]}<extra></extra>"
        ),
        marker_line_width=0.8, marker_line_color="rgba(255,255,255,0.4)", opacity=0.88,
    )

    # Estrellas de ruta crítica
    df_rc = df[df["es_critica"] == True]
    if len(df_rc):
        fig.add_trace(go.Scatter(
            x=df_rc["inicio_real"], y=df_rc["actividad"],
            mode="markers",
            marker=dict(symbol="star", size=10, color="#FFD700", line=dict(color="white", width=1)),
            name="⭐ Ruta Crítica", hoverinfo="skip",
        ))

    t36_str = (INICIO_SD + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")

    # Línea 36H — usar add_shape en lugar de add_vline (compatible con todos los Plotly)
    fig.add_shape(type="line", x0=t36_str, x1=t36_str, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="#FF4444", width=2.5, dash="dash"))
    fig.add_annotation(x=t36_str, y=1.02, xref="x", yref="paper",
                       text="← 36H →", showarrow=False,
                       font=dict(color="#FF4444", size=12), xanchor="center")

    # Franjas de turno (8h c/u)
    for t in range(7):
        x0_str = (INICIO_SD + timedelta(hours=t * 8)).strftime("%Y-%m-%d %H:%M:%S")
        x1_str = (INICIO_SD + timedelta(hours=(t + 1) * 8)).strftime("%Y-%m-%d %H:%M:%S")
        fig.add_shape(type="rect", x0=x0_str, x1=x1_str, y0=0, y1=1,
                      xref="x", yref="paper", layer="below",
                      fillcolor=["rgba(255,255,255,0.02)", "rgba(100,180,255,0.04)"][t % 2],
                      line=dict(width=0))
        fig.add_shape(type="line", x0=x0_str, x1=x0_str, y0=0, y1=1,
                      xref="x", yref="paper",
                      line=dict(color="rgba(150,150,150,0.15)", width=0.5))

    fig.update_layout(
        height=max(600, len(df) * 26 + 150),
        xaxis_title="Fecha / Hora Real",
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        legend_title_text="Criticidad",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=10, r=10, t=80, b=40),
        hovermode="closest",
    )
    return fig


def plot_gantt_centro(df: pd.DataFrame) -> go.Figure:
    df = df.copy().sort_values(["centro", "start_sd"])
    df["i_str"] = df["inicio_real"].apply(lambda x: x.strftime("%d/%m %H:%M") if hasattr(x, "strftime") else "")
    df["f_str"] = df["fin_real"].apply(lambda x: x.strftime("%d/%m %H:%M") if hasattr(x, "strftime") else "")

    fig = px.timeline(
        df, x_start="inicio_real", x_end="fin_real", y="centro",
        color="criticidad", color_discrete_map=COLORES_CRITICIDAD,
        custom_data=["actividad","especialidad","duracion_h","start_sd","end_sd",
                     "turno","es_critica","score","i_str","f_str"],
        template=T, title="🏗️ GANTT POR CENTRO — PARADA DE PLANTA SD18MAR26",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>Centro: %{y}</b><br>"
            "Actividad: %{customdata[0]}<br>"
            "Especialidad: %{customdata[1]}<br>"
            "Duración: <b>%{customdata[2]}h</b><br>"
            "SD%{customdata[3]} → SD%{customdata[4]}<br>"
            "%{customdata[8]} → %{customdata[9]}<br>"
            "Turno: %{customdata[5]}<br>"
            "RC Calc: %{customdata[6]} · Score: %{customdata[7]:.3f}<extra></extra>"
        ),
        opacity=0.85,
    )
    t36_str = (INICIO_SD + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
    fig.add_shape(type="line", x0=t36_str, x1=t36_str, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="#FF4444", width=2.5, dash="dash"))
    fig.add_annotation(x=t36_str, y=1.02, xref="x", yref="paper",
                       text="36H", showarrow=False,
                       font=dict(color="#FF4444", size=11), xanchor="center")
    for t in range(7):
        x0_str = (INICIO_SD + timedelta(hours=t * 8)).strftime("%Y-%m-%d %H:%M:%S")
        x1_str = (INICIO_SD + timedelta(hours=(t + 1) * 8)).strftime("%Y-%m-%d %H:%M:%S")
        fig.add_shape(type="rect", x0=x0_str, x1=x1_str, y0=0, y1=1,
                      xref="x", yref="paper", layer="below",
                      fillcolor=["rgba(255,255,255,0.02)", "rgba(100,180,255,0.04)"][t % 2],
                      line=dict(width=0))
    fig.update_layout(
        height=500, xaxis_title="Fecha / Hora",
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=10, r=10, t=80, b=40),
    )
    return fig


def plot_curva_s(df: pd.DataFrame, cs: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("Curva S — Avance Acumulado Planificado (%)",
                        "Flujo de Actividades por Hora SD"),
        row_heights=[0.65, 0.35], shared_xaxes=True, vertical_spacing=0.10,
    )

    fig.add_trace(go.Scatter(
        x=cs["hora_real"], y=cs["avance_acum"],
        mode="lines", name="Avance planificado",
        fill="tozeroy", fillcolor="rgba(0,229,255,0.15)",
        line=dict(color="#00E5FF", width=2.5),
        customdata=np.stack([cs["hora_sd"], cs["acts_completas"]], axis=-1),
        hovertemplate="SD%{customdata[0]}<br>%{x|%d/%m %H:%M}<br><b>Avance: %{y:.1f}%</b><br>Completas: %{customdata[1]}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=cs["hora_real"], y=np.linspace(0, 100, len(cs)),
        mode="lines", name="Ideal lineal",
        line=dict(color="#FFA500", width=1.5, dash="dash"), hoverinfo="skip",
    ), row=1, col=1)
