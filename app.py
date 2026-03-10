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
    act  = act.drop_duplicates(subset=["actividad"])

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

    df["ejecutor"] = df["ejecutor"].fillna("").str.strip().str.upper()
    df = df[df["ejecutor"].isin(["MASSY ENERGY", "MASSY ENERGY GEN"])]

    # Diccionario de correcciones comunes
    correcciones = {
        "ELÉCTRCIA": "ELÉCTRICA",
        "INSTRUMEMTACIÓN": "INSTRUMENTACIÓN",
        "INSTRUMENTACION": "INSTRUMENTACIÓN",
        "MECÁNICA/INSTRUMENTACIÓN": "MECÁNICA, INSTRUMENTACIÓN",
        "MECÁNICA/INSTRUMEMTACIÓN": "MECÁNICA, INSTRUMENTACIÓN",
    }

    df["especialidad"] = df["especialidad"].replace(correcciones)
    df["especialidad"] = df["especialidad"].str.replace(r"\s*,\s*", ", ", regex=True)
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

def programar(df: pd.DataFrame, horizonte: int, riesgo_thr: 4 ) -> pd.DataFrame:
    
    HORIZONTE = 36
    uso_rec = defaultdict(int)
    uso_cr  = defaultdict(set)
    rows    = []

    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    for _, act in df.iterrows():
        dur    = max(1, int(act["duracion_h"]))
        esp_k  = str(act["especialidad"])[:25]
        cap    = next((v for k, v in CAPACIDAD_RECURSOS.items() if k in esp_k.upper()), 4)
        alto   = act["criticidad_num"] >= riesgo_thr
        centro = act["centro"]
        inicio = None

        # Intentar ubicar la actividad dentro del horizonte
        for t in range(HORIZONTE - dur + 1):
            if any(uso_rec[(esp_k, h)] >= cap for h in range(t, t + dur)):
                continue
            if alto and set(range(t, t + dur)) & uso_cr[centro]:
                continue
            inicio = t
            break

        # Si no se encontró ventana, ubicar en el primer espacio disponible dentro de 36h
        if inicio is None:
            # Buscar ventana mínima que tenga menor saturación
            min_sum = float("inf")
            min_start = 0
            for t in range(HORIZONTE - dur + 1):
                carga = sum(uso_rec[(esp_k, h)] / cap for h in range(t, t + dur))
                if alto:
                    cr_conflict = len(set(range(t, t + dur)) & uso_cr[centro])
                    carga += cr_conflict
                if carga < min_sum:
                    min_sum = carga
                    min_start = t
            inicio = min_start

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
                     "dentro_horizonte": True  # Forzamos 36h
                    })

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
# MÓDULO 3B: CÁLCULO DE TÉCNICOS MÍNIMOS POR ESPECIALIDAD
# ─────────────────────────────────────────────────────────────────────────────
def min_tecnicos(df: pd.DataFrame, horizonte: int = 36, horas_turno: int = 8) -> pd.DataFrame:
    
    import numpy as np
    import pandas as pd

    # porcentajes definidos
    PESOS = {
        "MECÁNICA": 0.5,
        "ELÉCTRICA": 0.3,
        "INSTRUMENTACIÓN": 0.2
    }

    especs = list(PESOS.keys())
    idx_map = {esp: i for i, esp in enumerate(especs)}

    mat = np.zeros((len(especs), horizonte))
    horas_totales = {esp: 0 for esp in especs}

    for _, act in df.iterrows():

        start = int(act["start_sd"])
        end   = int(act["end_sd"])
        dur   = end - start

        # limpiar especialidades
        esp_list = (
            str(act["especialidad"])
            .replace("/", ",")
            .upper()
            .split(",")
        )

        esp_list = [e.strip() for e in esp_list if e.strip() in PESOS]

        if not esp_list:
            continue

        for esp in esp_list:

            peso = PESOS[esp]
            dur_esp = dur * peso
            idx = idx_map[esp]

            # simultaneidad
            for h in range(start, min(end, horizonte)):
                mat[idx, h] += peso

            # horas acumuladas
            horas_totales[esp] += dur_esp

    pico_simultaneo = np.ceil(mat.max(axis=1)).astype(int)

    resultados = []

    for esp in especs:

        horas = horas_totales[esp]
        tecnicos_por_horas = int(np.ceil(horas / horas_turno))
        tecnicos_final = max(pico_simultaneo[idx_map[esp]], tecnicos_por_horas)

        resultados.append({
            "Especialidad": esp,
            "Pico_Simultaneo": int(pico_simultaneo[idx_map[esp]]),
            "Horas_Totales": round(horas, 1),
            "Tecnicos_por_horas": tecnicos_por_horas,
            "Tecnicos_Minimos_Requeridos": tecnicos_final
        })

    return pd.DataFrame(resultados)
    
# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3C: TECNICOS POR ORDEN DE TRABAJO
# ─────────────────────────────────────────────────────────────────────────────
def tecnicos_por_ot(df):

    PESOS = {
        "MECÁNICA": 0.5,
        "ELÉCTRICA": 0.3,
        "INSTRUMENTACIÓN": 0.2
    }

    HORAS_TECNICO = 8

    rows = []

    for _, act in df.iterrows():

        dur = act["duracion_h"]

        esp_list = (
            str(act["especialidad"])
            .replace("/", ",")
            .upper()
            .split(",")
        )

        esp_list = [e.strip() for e in esp_list if e.strip()]

        # CASO 1: UNA SOLA ESPECIALIDAD
        if len(esp_list) == 1:

            horas = dur
            tecnicos = int(np.ceil(horas / HORAS_TECNICO))

            rows.append({
                "Orden": act["orden"],
                "Actividad": act["actividad"],
                "Centro": act["centro"],
                "Especialidad": esp_list[0],
                "Duracion_h": dur,
                "Tecnicos_Requeridos": tecnicos,
            })

        # CASO 2: MULTI ESPECIALIDAD
        else:

            for esp in esp_list:

                peso = PESOS.get(esp, 0)

                horas = dur * peso

                tecnicos = int(np.ceil(horas / HORAS_TECNICO))

                rows.append({
                    "Orden": act["orden"],
                    "Actividad": act["actividad"],
                    "Centro": act["centro"],
                    "Especialidad": esp,
                    "Duracion_h": dur,
                    "Horas_Especialidad": round(horas,2),
                    "Tecnicos_Requeridos": tecnicos,
                })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────
# MÓDULO 3D-A – DIVISIÓN DE ESPECIALIDADES (CORREGIDO)
# ─────────────────────────────────────────────────────────

def dividir_especialidades(cron):

    import pandas as pd

    PESOS = {
        "MECÁNICA": 0.5,
        "ELÉCTRICA": 0.3,
        "INSTRUMENTACIÓN": 0.2
    }

    filas = []

    for _, r in cron.iterrows():

        especialidades = [e.strip() for e in str(r["especialidad"]).split(",")]

        if len(especialidades) == 1:

            filas.append(r.to_dict())

        else:

            for esp in especialidades:

                nuevo = r.to_dict()

                peso = PESOS.get(esp, 1/len(especialidades))

                nuevo["especialidad"] = esp
                nuevo["duracion_h"] = int(round(r["duracion_h"] * peso))

                filas.append(nuevo)

    cron_nuevo = pd.DataFrame(filas)

    return cron_nuevo
    
# ─────────────────────────────────────────────────────────
# MÓDULO 3D – OPTIMIZADOR DE TÉCNICOS (VERSIÓN FINAL)
# ─────────────────────────────────────────────────────────

def optimizar_tecnicos_turnos(cron, horizonte=36):

    import pandas as pd
    import math

    cron = cron.copy()
    cron["hh_restantes"] = cron["duracion_h"]

    TURNOS = [(0,8),(24,32)]
    HORAS_TECNICO = 16

    # calcular demanda por centro y especialidad
    demanda = cron.groupby(["centro","especialidad"])["hh_restantes"].sum().reset_index()

    tecnicos = []

    for _, r in demanda.iterrows():

        n = math.ceil(r["hh_restantes"] / HORAS_TECNICO)

        for i in range(n):

            tecnicos.append({
                "tecnico": f"{r['centro']}_{r['especialidad']}_T{i+1}",
                "centro": r["centro"],
                "especialidad": r["especialidad"]
            })

    tecnicos = pd.DataFrame(tecnicos)

    matriz = pd.DataFrame(
        "",
        index=tecnicos["tecnico"],
        columns=list(range(horizonte))
    )

    # recorrer técnicos
    for _, t in tecnicos.iterrows():

        centro = t["centro"]
        esp = t["especialidad"]

        for inicio, fin in TURNOS:

            horas_turno = fin - inicio
            h = inicio

            while horas_turno > 0:

                ots = cron[
                    (cron["centro"] == centro) &
                    (cron["especialidad"] == esp) &
                    (cron["hh_restantes"] > 0)
                ]

                if ots.empty:
                    break

                ot = ots.sort_values("hh_restantes", ascending=False).iloc[0]

                ot_idx = ot.name
                orden = ot["orden"]

                bloque = min(
                    horas_turno,
                    cron.loc[ot_idx,"hh_restantes"]
                )

                for i in range(bloque):

                    matriz.loc[t["tecnico"], h] = orden
                    h += 1

                cron.loc[ot_idx,"hh_restantes"] -= bloque
                horas_turno -= bloque

    return matriz
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

    av36 = float(np.interp(36, cs["hora_sd"], cs["avance_acum"]))
    t36  = INICIO_SD + timedelta(hours=36)
    fig.add_trace(go.Scatter(
        x=[t36], y=[av36], mode="markers+text",
        marker=dict(color="#FF4444", size=12, symbol="circle"),
        text=[f" {av36:.1f}% @ SD36"], textposition="middle right",
        textfont=dict(color="#FF4444", size=12),
        name=f"@ SD36: {av36:.1f}%",
        hovertemplate=f"<b>Avance @ SD36: {av36:.1f}%</b><extra></extra>",
    ), row=1, col=1)

    for t in range(0, 52, 8):
        av_t = float(np.interp(t, cs["hora_sd"], cs["avance_acum"]))
        ht   = INICIO_SD + timedelta(hours=t)
        fig.add_trace(go.Scatter(
            x=[ht], y=[av_t], mode="markers+text",
            marker=dict(color="#FFD700", size=7, symbol="diamond"),
            text=[f"T{t//8+1} {av_t:.0f}%"], textposition="top center",
            textfont=dict(size=8), showlegend=False,
            hovertemplate=f"SD{t} · {ht.strftime('%d/%m %H:%M')}<br>Avance: {av_t:.1f}%<extra></extra>",
        ), row=1, col=1)

    bins      = list(range(52))
    bins_ext  = bins + [52]
    hs, _     = np.histogram(df["start_sd"].values, bins=bins_ext)
    he, _     = np.histogram(df["end_sd"].values,   bins=bins_ext)
    h_real    = [INICIO_SD + timedelta(hours=h) for h in bins]

    fig.add_trace(go.Bar(
        x=h_real, y=hs, name="Inicios/hora",
        marker_color="rgba(76,175,80,0.7)",
        customdata=bins,
        hovertemplate="SD%{customdata}<br>Inicios: %{y}<extra></extra>",
    ), row=2, col=1)
    fig.add_trace(go.Bar(
        x=h_real, y=he, name="Finalizaciones/hora",
        marker_color="rgba(244,67,54,0.7)",
        customdata=bins,
        hovertemplate="SD%{customdata}<br>Finalizaciones: %{y}<extra></extra>",
    ), row=2, col=1)

    t36_str = (INICIO_SD + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
    # Línea 36H en ambos subplots usando add_shape (compatible con todos los Plotly)
    for xref, yref in [("x1", "y1"), ("x2", "y2")]:
        fig.add_shape(type="line", x0=t36_str, x1=t36_str, y0=0, y1=1,
                      xref=xref, yref="paper",
                      line=dict(color="#FF4444", width=2, dash="dash"))

    fig.update_layout(
        template=T, title="📈 CURVA S — PARADA DE PLANTA SD18MAR26",
        height=700, hovermode="x unified", barmode="group",
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=10, r=10, t=80, b=40),
    )
    fig.update_yaxes(title_text="Avance Acum (%)", range=[0, 105], row=1, col=1)
    fig.update_yaxes(title_text="Cantidad/hora", row=2, col=1)
    return fig


def plot_kpis_centro(df: pd.DataFrame) -> go.Figure:
    """
    KPIs por centro. NO usa add_hline/add_vline porque falla en subplots
    mixtos (bar + pie). Las líneas de referencia se agregan como scatter
    fantasma, que es 100% compatible con todas las versiones de Plotly.
    """
    res = df.groupby("centro").agg(
        total=("id","count"), dur=("duracion_h","sum"),
        criticas=("es_critica","sum"),
        rc_orig=("ruta_critica", lambda x:(x=="SI").sum()),
        valor=("valor_global_norm", lambda x:round(x.sum()*100,2)),
        makespan=("end_sd","max"),
        dentro36=("dentro_horizonte","sum"),
    ).reset_index()
    res["pct_cumpl"] = (res["dentro36"] / res["total"] * 100).round(1)
    centros = res["centro"].tolist()
    cols    = [COLORES_CENTRO.get(c, "#9E9E9E") for c in centros]

    # Subplots: pie solo en la posición (1,3), el resto son xy
    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=["Total Actividades","Duración Total (h)","% Valor Global",
                        "Actividades Críticas","% Cumplimiento 36H","Makespan (Hora SD fin)"],
        specs=[[{"type":"xy"},{"type":"xy"},{"type":"domain"}],
               [{"type":"xy"},{"type":"xy"},{"type":"xy"}]],
    )

    def ref_line(yval: float, r: int, c: int):
        """Línea de referencia como scatter horizontal — compatible con todos los Plotly."""
        # Calcular el nombre del eje y según posición del subplot
        idx = (r - 1) * 3 + c
        yax = "y" if idx == 1 else f"y{idx}"
        fig.add_trace(go.Scatter(
            x=[centros[0], centros[-1]],
            y=[yval, yval],
            mode="lines",
            line=dict(color="#FF4444", width=1.5, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
            yaxis=yax,
        ), row=r, col=c)

    def bar_tr(x, y, cs, name, ht, r, c, ref=None):
        fig.add_trace(go.Bar(
            x=x, y=y, name=name, marker_color=cs,
            text=[str(v) for v in y], textposition="outside",
            hovertemplate=ht,
        ), row=r, col=c)
        if ref is not None:
            ref_line(ref, r, c)

    bar_tr(centros, res["total"].tolist(), cols,
           "Actividades", "%{x}: %{y} act.<extra></extra>", 1, 1)
    bar_tr(centros, res["dur"].tolist(), cols,
           "Duración (h)", "%{x}: %{y}h<extra></extra>", 1, 2, ref=36)

    # Pie (domain type — sin ejes x/y)
    fig.add_trace(go.Pie(
        labels=centros,
        values=res["valor"].tolist(),
        marker_colors=cols,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.2f}%<extra></extra>",
        hole=0.35,
        name="Valor Global",
        showlegend=False,
    ), row=1, col=3)

    # Barras críticas (doble barra en mismo subplot)
    fig.add_trace(go.Bar(
        x=centros, y=res["criticas"].tolist(),
        name="Críticas calc.", marker_color="#E53935",
        text=[str(v) for v in res["criticas"].tolist()],
        textposition="outside",
        hovertemplate="%{x}: %{y} críticas calc.<extra></extra>",
    ), row=2, col=1)
    fig.add_trace(go.Bar(
        x=centros, y=res["rc_orig"].tolist(),
        name="RC originales", marker_color="#FFD700",
        text=[str(v) for v in res["rc_orig"].tolist()],
        textposition="outside",
        hovertemplate="%{x}: %{y} RC originales<extra></extra>",
    ), row=2, col=1)

    cumpl_c = ["#4CAF50" if p >= 80 else "#FFA726" if p >= 50 else "#EF5350"
               for p in res["pct_cumpl"]]
    bar_tr(centros, res["pct_cumpl"].tolist(), cumpl_c,
           "% Cumplimiento", "%{x}: %{y}%<extra></extra>", 2, 2, ref=100)
    bar_tr(centros, res["makespan"].tolist(), cols,
           "Makespan SD", "SD%{y}<extra></extra>", 2, 3, ref=36)

    fig.update_layout(
        template=T,
        title="📊 KPIs POR CENTRO — PARADA DE PLANTA SD18MAR26",
        height=720,
        showlegend=True,
        barmode="group",
        margin=dict(l=10, r=10, t=80, b=40),
    )
    return fig


def plot_scatter_prioridad(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["actividad_corta"] = df2["actividad"].str[:45]
    df2["marker_size"]     = ((df2["valor_global_norm"] * 10000).clip(3, 40))

    fig = px.scatter(
        df2, x="start_sd", y="score",
        color="criticidad", color_discrete_map=COLORES_CRITICIDAD,
        size="marker_size", size_max=30,
        symbol="es_critica", symbol_map={True:"star", False:"circle"},
        facet_col="centro", facet_col_wrap=4,
        custom_data=["actividad_corta","duracion_h","end_sd","turno",
                     "especialidad","riesgo_texto","dentro_horizonte","valor_global"],
        template=T, title="🎯 MAPA DE PRIORIDAD — Score vs Inicio SD",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "SD%{x} → SD%{customdata[2]} · %{customdata[1]}h<br>"
            "Score: <b>%{y:.3f}</b><br>"
            "Turno: %{customdata[3]}<br>"
            "Especialidad: %{customdata[4]}<br>"
            "Riesgo: %{customdata[5]}<br>"
            "Valor: %{customdata[7]:.5f}<br>"
            "Dentro 36H: %{customdata[6]}<extra></extra>"
        )
    )
    # Línea 36H — add_shape es compatible con todas las versiones de Plotly
    fig.add_shape(type="line", x0=36, x1=36, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="#FF4444", width=1.5, dash="dash"))
    fig.add_annotation(x=36, y=1.01, xref="x", yref="paper",
                       text="SD36", showarrow=False,
                       font=dict(color="#FF4444", size=10))
    fig.update_layout(height=700, margin=dict(l=10, r=10, t=80, b=40))
    return fig


def plot_recursos_hora(df: pd.DataFrame) -> go.Figure:
    especs = sorted(df["especialidad"].str.split(",").explode().str.strip().unique())
    horas  = list(range(51))
    mat    = np.zeros((len(especs), len(horas)))

    for _, act in df.iterrows():
        for h in range(int(act["start_sd"]), int(act["end_sd"])):
            for esp in str(act["especialidad"]).split(","):
                esp = esp.strip()
                if esp in especs and h < len(horas):
                    mat[especs.index(esp), h] += 1

    caps    = [CAPACIDAD_RECURSOS.get(e, 4) for e in especs]
    mat_pct = mat / np.array(caps)[:, None] * 100

    fig = go.Figure(go.Heatmap(
        z=mat_pct, x=[f"SD{h}" for h in horas], y=especs,
        colorscale=[[0,"#1a3a1a"],[0.5,"#FFA500"],[0.8,"#E53935"],[1.0,"#B71C1C"]],
        zmin=0, zmax=110,
        hovertemplate="Hora: %{x}<br>Especialidad: %{y}<br>Carga: %{z:.0f}%<extra></extra>",
        colorbar=dict(title="% Capacidad", ticksuffix="%"),
    ))
    # En heatmap con eje categórico, add_vline no funciona: usar add_shape
    fig.add_shape(type="line", x0="SD35", x1="SD37", y0=-0.5, y1=len(especs)-0.5,
                  line=dict(color="#FF4444", width=2, dash="dash"))
    fig.add_annotation(x="SD36", y=len(especs), text="36H", showarrow=False,
                       font=dict(color="#FF4444", size=11))
    fig.update_layout(
        template=T, title="🔧 CARGA DE RECURSOS POR ESPECIALIDAD Y HORA SD",
        xaxis_title="Hora SD", yaxis_title="Especialidad",
        height=max(350, len(especs) * 38 + 150),
        margin=dict(l=10, r=10, t=80, b=40),
    )
    return fig


def plot_ruta_critica(df: pd.DataFrame) -> go.Figure:
    df_rc = df[df["es_critica"]].sort_values("start_sd").copy()
    df_rc["i_str"] = df_rc["inicio_real"].apply(lambda x: x.strftime("%d/%m %H:%M") if hasattr(x,"strftime") else "")
    df_rc["f_str"] = df_rc["fin_real"].apply(lambda x: x.strftime("%d/%m %H:%M") if hasattr(x,"strftime") else "")
    df_rc["etiq"]  = df_rc["centro"] + " | " + df_rc["actividad"].str[:52]

    fig = px.timeline(
        df_rc, x_start="inicio_real", x_end="fin_real", y="etiq",
        color="criticidad", color_discrete_map=COLORES_CRITICIDAD,
        custom_data=["actividad","centro","especialidad","ejecutor","duracion_h",
                     "start_sd","end_sd","turno","criticidad_num","riesgo_texto",
                     "score","i_str","f_str","ruta_critica"],
        template=T, title="🔴 GANTT — RUTA CRÍTICA DETALLADA",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Centro: %{customdata[1]}<br>"
            "Especialidad: %{customdata[2]}<br>"
            "Ejecutor: %{customdata[3]}<br>"
            "Duración: <b>%{customdata[4]}h</b><br>"
            "SD%{customdata[5]} → SD%{customdata[6]}<br>"
            "%{customdata[11]} → %{customdata[12]}<br>"
            "Turno: %{customdata[7]}<br>"
            "Criticidad num: %{customdata[8]}<br>"
            "Riesgo: %{customdata[9]}<br>"
            "RC Orig: %{customdata[13]}<br>"
            "Score: %{customdata[10]:.3f}<extra></extra>"
        ),
        marker_line_width=1.5, marker_line_color="#FFD700", opacity=0.92,
    )
    t36_str = (INICIO_SD + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
    fig.add_shape(type="line", x0=t36_str, x1=t36_str, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="#FF4444", width=2.5, dash="dash"))
    fig.add_annotation(x=t36_str, y=1.02, xref="x", yref="paper",
                       text="← 36H", showarrow=False,
                       font=dict(color="#FF4444", size=11), xanchor="center")
    fig.update_layout(
        height=max(400, len(df_rc) * 42 + 150),
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=10, r=10, t=80, b=40), hovermode="closest",
    )
    return fig


def plot_distribucion_horas(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["espec_norm"] = df2["especialidad"].str.split(",").str[0].str.strip()
    df2["act_corta"]  = df2["actividad"].str[:40]

    fig = px.treemap(
        df2, path=["centro","espec_norm","act_corta"],
        values="duracion_h",
        color="criticidad_num",
        color_continuous_scale=["#43A047","#FB8C00","#E53935","#B71C1C"],
        color_continuous_midpoint=2.5,
        custom_data=["actividad","duracion_h","criticidad","start_sd","end_sd"],
        template=T, title="🗂️ DISTRIBUCIÓN HORAS: Centro → Especialidad → Actividad",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Horas: %{value:.0f}h<br>"
            "Actividad: %{customdata[0]}<br>"
            "Criticidad: %{customdata[2]}<br>"
            "SD%{customdata[3]} → SD%{customdata[4]}<extra></extra>"
        )
    )
    fig.update_layout(height=600, margin=dict(l=10, r=10, t=80, b=40))
    return fig


def plot_matriz_riesgo(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["act_corta"] = df2["actividad"].str[:50]
    rng = np.random.default_rng(42)
    df2["crit_j"]   = df2["criticidad_num"] + rng.uniform(-0.15, 0.15, len(df2))
    df2["riesgo_j"] = df2["riesgo_num"]     + rng.uniform(-0.15, 0.15, len(df2))

    fig = px.scatter(
        df2, x="crit_j", y="riesgo_j",
        size="duracion_h", size_max=45,
        color="criticidad", color_discrete_map=COLORES_CRITICIDAD,
        symbol="dentro_horizonte", symbol_map={True:"circle", False:"x"},
        custom_data=["act_corta","centro","duracion_h","start_sd","end_sd",
                     "criticidad_num","riesgo_num","dentro_horizonte","ruta_critica"],
        template=T, title="⚠️ MATRIZ DE RIESGO vs CRITICIDAD (✕ = fuera de 36H)",
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Centro: %{customdata[1]}<br>"
            "Duración: %{customdata[2]}h<br>"
            "SD%{customdata[3]} → SD%{customdata[4]}<br>"
            "Criticidad num: %{customdata[5]}<br>"
            "Riesgo num: %{customdata[6]}<br>"
            "Dentro 36H: %{customdata[7]}<br>"
            "RC: %{customdata[8]}<extra></extra>"
        )
    )
    for cx, cy, txt, bgc in [
        (1.5,3.5,"⚠️ Alto riesgo / Baja crit.","rgba(255,165,0,0.1)"),
        (3.5,3.5,"🔴 Alto riesgo / Alta crit.","rgba(255,50,50,0.12)"),
        (1.5,1.5,"✅ Bajo riesgo / Baja crit.","rgba(76,175,80,0.08)"),
        (3.5,1.5,"🟡 Bajo riesgo / Alta crit.","rgba(255,215,0,0.08)"),
    ]:
        fig.add_annotation(x=cx, y=cy, text=txt, showarrow=False,
                           font=dict(size=9,color="rgba(255,255,255,0.4)"), bgcolor=bgc)
    # Líneas de cuadrante — add_shape es compatible con todas las versiones de Plotly
    fig.add_shape(type="line", x0=0.5, x1=5.5, y0=2.5, y1=2.5,
                  line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dot"))
    fig.add_shape(type="line", x0=2.5, x1=2.5, y0=0.5, y1=5.5,
                  line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dot"))
    fig.update_layout(
        height=550,
        xaxis=dict(title="Criticidad (num)", tickvals=[1,2,3,4,5]),
        yaxis=dict(title="Riesgo Entorno (num)", tickvals=[1,2,3,4,5]),
        margin=dict(l=10, r=10, t=80, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 6: EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────────────────

def exportar_excel(df: pd.DataFrame) -> bytes:
    buf  = io.BytesIO()
    cols = ["id","centro","actividad","orden","especialidad","ejecutor",
            "criticidad","criticidad_num","riesgo_texto","riesgo_num",
            "duracion_h","start_sd","end_sd","turno",
            "valor_global","valor_global_norm","acum_centro_calc","acum_total_calc",
            "ruta_critica","es_critica","dentro_horizonte","avance_pct","score","prioridad"]
    df_e = df[[c for c in cols if c in df.columns]].copy()
    for col in ["valor_global_norm","acum_centro_calc","acum_total_calc"]:
        if col in df_e.columns:
            df_e[col] = df_e[col].clip(upper=100).round(3)

    ren = {"id":"ID","centro":"Centro","actividad":"Actividad","orden":"Orden SAP",
           "especialidad":"Especialidad","ejecutor":"Ejecutor","criticidad":"Criticidad",
           "criticidad_num":"Crit. Num","riesgo_texto":"Riesgo","riesgo_num":"Riesgo Num",
           "duracion_h":"Duración (h)","start_sd":"Inicio SD","end_sd":"Fin SD","turno":"Turno",
           "valor_global":"Valor Global","valor_global_norm":"Valor Global %",
           "acum_centro_calc":"% Acum Centro","acum_total_calc":"% Acum Total",
           "ruta_critica":"RC Orig","es_critica":"RC Calc",
           "dentro_horizonte":"Dentro 36H","avance_pct":"Avance %",
           "score":"Score","prioridad":"Prioridad"}
    df_e = df_e.rename(columns={k:v for k,v in ren.items() if k in df_e.columns})

    resumen = df.groupby("centro").agg(
        N_Act=("id","count"), Horas=("duracion_h","sum"),
        Criticas=("es_critica","sum"),
        RC_Orig=("ruta_critica",lambda x:(x=="SI").sum()),
        Makespan=("end_sd","max"),
        Dentro_36H=("dentro_horizonte","sum"),
        Valor_Pct=("valor_global_norm",lambda x:round(x.sum()*100,2)),
    ).reset_index()
    resumen["Pct_Cumpl"] = (resumen["Dentro_36H"]/resumen["N_Act"]*100).round(1)

    metricas = pd.DataFrame({
        "Métrica":["Total Actividades","RC (calc)","Makespan SD","Dentro 36H",
                   "% Cumplimiento","Centro mayor carga","Inicio SD","Fin estimado","Horas totales"],
        "Valor":[len(df), int(df["es_critica"].sum()), int(df["end_sd"].max()),
                 int(df["dentro_horizonte"].sum()),
                 f"{df['dentro_horizonte'].mean()*100:.1f}%",
                 df.groupby("centro")["duracion_h"].sum().idxmax(),
                 "18/03/2026 06:00",
                 (INICIO_SD+timedelta(hours=int(df["end_sd"].max()))).strftime("%d/%m/%Y %H:%M"),
                 int(df["duracion_h"].sum())]
    })

    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_e.to_excel(w, sheet_name="Cronograma", index=False)
        resumen.to_excel(w, sheet_name="Resumen Centro", index=False)
        metricas.to_excel(w, sheet_name="Métricas", index=False)
        df_rc = df[df.get("es_critica", pd.Series([False]*len(df))) == True] if "es_critica" in df.columns else pd.DataFrame()
        if not df_rc.empty:
            df_rc[[c for c in cols if c in df_rc.columns]].rename(columns=ren).to_excel(w, sheet_name="Ruta Crítica", index=False)

    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Parada de Planta SD18MAR26",
        page_icon="🏭", layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown("""
    <style>
    .main{background-color:#0D1117;}
    div[data-testid="metric-container"]{background:#1E2D40;border-radius:8px;
        padding:12px;border:1px solid #2a4a6a;}
    h1,h2,h3{color:#00E5FF;}
    .block-container{padding-top:1.2rem;padding-bottom:1rem;}
    .stTabs [data-baseweb="tab"]{color:#AAAAAA;font-size:0.83rem;}
    .stTabs [aria-selected="true"]{color:#00E5FF;border-bottom:2px solid #00E5FF;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style='background:linear-gradient(135deg,#0D47A1,#1a237e);padding:16px 22px;
    border-radius:10px;margin-bottom:14px;border:1px solid #2a4a6a;'>
      <h1 style='color:#00E5FF;margin:0;font-size:1.65rem;'>
        🏭 SIMULACIÓN PARADA DE PLANTA — SD18MAR26
      </h1>
      <p style='color:#90CAF9;margin:4px 0 0;font-size:0.88rem;'>
        18 Marzo 2026 · 06:00 &nbsp;|&nbsp; Horizonte objetivo: 36 horas &nbsp;|&nbsp;
        Modelo CPM Greedy + Resource Leveling · Visualizaciones interactivas con Plotly
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── SIDEBAR ──
    with st.sidebar:
        st.markdown("## ⚙️ Configuración")
        st.markdown("### 📂 Archivos Excel")
        f_act = st.file_uploader("1. Listado de Actividades", type=["xlsx"], key="fa")
        f_pdt = st.file_uploader("2. PDT Paro de Bombeo",     type=["xlsx"], key="fp")
        st.markdown("---")
        st.markdown("### 🎯 Pesos Función Objetivo")
        w_crit   = st.slider("⭐ Criticidad",    0.0, 1.0, 0.40, 0.05)
        w_riesgo = st.slider("⚠️ Riesgo",        0.0, 1.0, 0.30, 0.05)
        w_valor  = st.slider("💰 Valor Global",  0.0, 1.0, 0.20, 0.05)
        w_dur    = st.slider("⏱️ Penaliz. Dur.", 0.0, 0.5, 0.10, 0.05)
        suma = w_crit + w_riesgo + w_valor
        st.caption(f"{'🟢' if abs(suma-1.0)<0.15 else '🟡'} Suma pesos: **{suma:.2f}**")
        st.markdown("---")
        st.markdown("### 🔧 Restricciones")
        riesgo_thr = st.slider("Umbral criticidad no-solapamiento", 2, 5, 3)
        st.markdown("---")
        ejecutar = st.button("▶  EJECUTAR SIMULACIÓN", type="primary", use_container_width=True)

    # ── VALIDACIÓN ──
    if not f_act or not f_pdt:
        st.info("👈 Sube los **dos archivos Excel** en el panel lateral para comenzar.")
        c1, c2 = st.columns(2)
        c1.markdown("**Archivo 1:** `1__Listado_Actividades_1er_SD2026_18032026.xlsx`  \nHoja: `Lista de Actividades SD`")
        c2.markdown("**Archivo 2:** `260318_PDT_Paro_de_Bombeo_SD18MAR26_VF.xlsx`  \nHoja: `Actividades`")
        return

    # ── PROCESAMIENTO ──
    if ejecutar or "cron" not in st.session_state:
        with st.spinner("⚙️ Ejecutando modelo de optimización..."):
            try:
                dfa    = cargar_actividades(f_act.read())
                dfp    = cargar_pdt(f_pdt.read())
                m      = limpiar_unificar(dfa, dfp)
                m      = scoring(m, w_crit, w_riesgo, w_valor, w_dur)
                cron   = programar(m, 51, riesgo_thr)
                cs     = curva_s(cron, 51)
                df_tecnicos = min_tecnicos(cron, horizonte=36, horas_turno=8)
                df_tecnicos_ot  = tecnicos_por_ot(cron)
                cron = dividir_especialidades(cron)
                matriz_tecnicos = optimizar_tecnicos_turnos(cron)          
                st.session_state.update({"cron": cron, "cs": cs, "tecnicos": df_tecnicos, "tecnicos_ot": df_tecnicos_ot, "cron":cron, "matriz_tecnicos": matriz_tecnicos})
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.exception(e)
                return
        st.success("✅ Simulación completada")

    cron = st.session_state["cron"]
    cs   = st.session_state["cs"]
    df_tecnicos = st.session_state["tecnicos"]
    df_tecnicos_ot = st.session_state["tecnicos_ot"]
    cron = st.session_state["cron"]
    matriz_tecnicos = st.session_state["matriz_tecnicos"]
 
    
    # Mostrar tabla de técnicos mínimos
    st.subheader("🛠️ Técnicos mínimos necesarios por especialidad")
    st.dataframe(df_tecnicos)

    st.subheader("👷 Técnicos requeridos por Orden de Trabajo")
    st.dataframe(df_tecnicos_ot)

    st.subheader("📅 Planificación de técnicos por hora")
    st.caption("Cada fila es un técnico. Cada columna es una hora SD (0-36).")
    st.dataframe(matriz_tecnicos)


    # ── KPIs ──
    mksp  = int(cron["end_sd"].max())
    n_tot = len(cron)
    n_cr  = int(cron["es_critica"].sum())
    pct36 = cron["dentro_horizonte"].mean() * 100
    av36  = float(np.interp(36, cs["hora_sd"], cs["avance_acum"]))
    fin_dt = INICIO_SD + timedelta(hours=mksp)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("📋 Actividades", n_tot)
    c2.metric("⏱️ Makespan", f"SD{mksp}", f"{'✅ En 36H' if mksp<=36 else f'⚠️ +{mksp-36}H'}")
    c3.metric("⭐ Ruta Crítica", n_cr)
    c4.metric("🎯 Cumpl. 36H", f"{pct36:.0f}%", f"{int(cron['dentro_horizonte'].sum())}/{n_tot}")
    c5.metric("📈 Avance @SD36", f"{av36:.1f}%")
    c6.metric("🏁 Fin Estimado", fin_dt.strftime("%d/%m %H:%M"))
    st.caption(
        f"📅 **Inicio:** 18/03/2026 06:00 &nbsp;·&nbsp; "
        f"**Fin:** {fin_dt.strftime('%d/%m/%Y %H:%M')} &nbsp;·&nbsp; "
        f"**Centros:** {cron['centro'].nunique()} &nbsp;·&nbsp; "
        f"**Horas acumuladas:** {int(cron['duracion_h'].sum())}h"
    )
    st.markdown("---")

    # ── TABS ──
    tabs = st.tabs([
        "📅 Gantt Actividades",
        "🏗️ Gantt por Centro",
        "📈 Curva S",
        "📊 KPIs Centro",
        "🔴 Ruta Crítica",
        "🎯 Mapa Prioridad",
        "🔧 Recursos",
        "⚠️ Matriz Riesgo",
        "🗂️ Distribución",
        "📋 Tabla Completa",
    ])

    # ── TAB 1 ──
    with tabs[0]:
        st.subheader("Diagrama de Gantt — Todas las Actividades")
        st.caption("🖱️ Rueda del ratón = zoom · Arrastra = desplazar · Click leyenda = filtrar · Hover = detalle completo")
        ca, cb, cc = st.columns(3)
        fc = ca.multiselect("Centro",      sorted(cron["centro"].unique()),       key="t1c")
        fr = cb.multiselect("Criticidad",  ["Muy Alta","Alta","Media","Baja"],    key="t1r")
        so = cc.checkbox("Solo ruta crítica", key="t1s")
        dg = cron.copy()
        if fc: dg = dg[dg["centro"].isin(fc)]
        if fr: dg = dg[dg["criticidad"].isin(fr)]
        if so: dg = dg[dg["es_critica"] == True]
        st.caption(f"Mostrando **{len(dg)}** de {n_tot} actividades")
        st.plotly_chart(plot_gantt(dg), use_container_width=True)

    # ── TAB 2 ──
    with tabs[1]:
        st.subheader("Gantt por Centro — Vista Compacta")
        st.caption("Cada fila = un centro. Hover sobre cada barra para ver el detalle de la actividad.")
        ca, cb = st.columns(2)
        fc2 = ca.multiselect("Centro",     sorted(cron["centro"].unique()),    key="t2c")
        fr2 = cb.multiselect("Criticidad", ["Muy Alta","Alta","Media","Baja"], key="t2r")
        dg2 = cron.copy()
        if fc2: dg2 = dg2[dg2["centro"].isin(fc2)]
        if fr2: dg2 = dg2[dg2["criticidad"].isin(fr2)]
        st.plotly_chart(plot_gantt_centro(dg2), use_container_width=True)

    # ── TAB 3 ──
    with tabs[2]:
        st.subheader("Curva S — Avance Planificado")
        st.caption("Panel superior: avance acumulado con marcadores por turno. Panel inferior: histograma inicios/finalizaciones por hora.")
        st.plotly_chart(plot_curva_s(cron, cs), use_container_width=True)
        st.markdown("#### 📍 Tabla de Hitos por Turno")
        rows_h = []
        for h in [0, 8, 16, 24, 32, 36, 40, 48, 51]:
            av_h = float(np.interp(h, cs["hora_sd"], cs["avance_acum"]))
            comp = int(cs.loc[cs["hora_sd"]==h, "acts_completas"].iloc[0]) if h in cs["hora_sd"].values else 0
            ht   = INICIO_SD + timedelta(hours=h)
            rows_h.append({
                "Hora SD": f"SD{h}",
                "Fecha / Hora": ht.strftime("%d/%m/%Y %H:%M"),
                "Turno": f"T{h//8+1}" if h < 48 else "Cierre",
                "Avance Acum (%)": round(av_h, 1),
                "Actividades Completas": comp,
                "Pendientes": n_tot - comp,
            })
        st.dataframe(pd.DataFrame(rows_h), use_container_width=True, hide_index=True,
                     column_config={"Avance Acum (%)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})

    # ── TAB 4 ──
    with tabs[3]:
        st.subheader("KPIs por Centro de Planificación")
        st.plotly_chart(plot_kpis_centro(cron), use_container_width=True)
        st.markdown("#### Tabla Resumen por Centro")
        rc = cron.groupby("centro").agg(
            Actividades=("id","count"), Horas=("duracion_h","sum"),
            Criticas=("es_critica","sum"),
            RC_Orig=("ruta_critica",lambda x:(x=="SI").sum()),
            Makespan_SD=("end_sd","max"),
            Dentro_36H=("dentro_horizonte","sum"),
            Score_Prom=("score","mean"),
            Valor_Pct=("valor_global_norm",lambda x:round(x.sum()*100,2)),
        ).reset_index()
        rc["% Cumpl."] = (rc["Dentro_36H"]/rc["Actividades"]*100).round(1)
        rc["Score_Prom"] = rc["Score_Prom"].round(3)
        st.dataframe(rc.rename(columns={"centro":"Centro"}), use_container_width=True, hide_index=True)

    # ── TAB 5 ──
    with tabs[4]:
        st.subheader("🔴 Ruta Crítica")
        df_rc = cron[cron["es_critica"]].sort_values("score", ascending=False)
        st.caption(f"**{len(df_rc)} actividades** en ruta crítica · "
                   f"{int((df_rc['ruta_critica']=='SI').sum())} marcadas originalmente")
        st.plotly_chart(plot_ruta_critica(cron), use_container_width=True)
        st.markdown("#### Detalle Ruta Crítica")
        c_rc = ["centro","actividad","especialidad","ejecutor","criticidad","criticidad_num",
                "riesgo_texto","riesgo_num","duracion_h","start_sd","end_sd","turno",
                "ruta_critica","es_critica","score","dentro_horizonte"]
        st.dataframe(
            df_rc[[c for c in c_rc if c in df_rc.columns]].rename(columns={
                "centro":"Centro","actividad":"Actividad","especialidad":"Especialidad",
                "ejecutor":"Ejecutor","criticidad":"Criticidad","criticidad_num":"Crit.",
                "riesgo_texto":"Riesgo","riesgo_num":"Riesgo Num","duracion_h":"Dur.(h)",
                "start_sd":"Inicio SD","end_sd":"Fin SD","turno":"Turno",
                "ruta_critica":"RC Orig","es_critica":"RC Calc","score":"Score",
                "dentro_horizonte":"Dentro 36H",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.NumberColumn(format="%.3f"),
                "Dur.(h)": st.column_config.NumberColumn(format="%d h"),
                "Inicio SD": st.column_config.NumberColumn(format="SD%d"),
                "Fin SD": st.column_config.NumberColumn(format="SD%d"),
            }
        )

    # ── TAB 6 ──
    with tabs[5]:
        st.subheader("Mapa de Prioridad")
        st.caption("Score vs Hora SD · Tamaño = Valor Global · ★ = Ruta Crítica · ✕ = Fuera de 36H")
        ca, cb = st.columns(2)
        fc5 = ca.multiselect("Centro",     sorted(cron["centro"].unique()),    key="t5c")
        fr5 = cb.multiselect("Criticidad", ["Muy Alta","Alta","Media","Baja"], key="t5r")
        dg5 = cron.copy()
        if fc5: dg5 = dg5[dg5["centro"].isin(fc5)]
        if fr5: dg5 = dg5[dg5["criticidad"].isin(fr5)]
        st.plotly_chart(plot_scatter_prioridad(dg5), use_container_width=True)

    # ── TAB 7 ──
    with tabs[6]:
        st.subheader("Carga de Recursos por Especialidad y Hora SD")
        st.caption("Heatmap: 🟢 Libre · 🟠 Medio · 🔴 Saturado. Valor = % de la capacidad máxima configurada.")
        st.plotly_chart(plot_recursos_hora(cron), use_container_width=True)
        st.markdown("#### Capacidades configuradas")
        st.dataframe(
            pd.DataFrame([{"Especialidad":k,"Técnicos":v} for k,v in CAPACIDAD_RECURSOS.items() if k!="DEFAULT"]),
            use_container_width=True, hide_index=True
        )

    # ── TAB 8 ──
    with tabs[7]:
        st.subheader("Matriz de Riesgo vs Criticidad")
        st.caption("Cada burbuja = 1 actividad · Tamaño = Duración · ✕ = Fuera del horizonte 36H")
        st.plotly_chart(plot_matriz_riesgo(cron), use_container_width=True)

    # ── TAB 9 ──
    with tabs[8]:
        st.subheader("Distribución de Horas por Centro → Especialidad → Actividad")
        st.caption("Treemap interactivo: haz clic en cualquier bloque para hacer zoom dentro de esa categoría.")
        st.plotly_chart(plot_distribucion_horas(cron), use_container_width=True)

    # ── TAB 10 ──
    with tabs[9]:
        st.subheader("📋 Cronograma Optimizado Completo")
        ca,cb,cc,cd = st.columns(4)
        fc10 = ca.multiselect("Centro",     sorted(cron["centro"].unique()),    key="t10c")
        fr10 = cb.multiselect("Criticidad", ["Muy Alta","Alta","Media","Baja"], key="t10r")
        rc10 = cc.selectbox("Ruta Crítica", ["Todos","Solo RC","Sin RC"],       key="t10rc")
        h10  = cd.selectbox("Horizonte",    ["Todos","Dentro 36H","Fuera 36H"],  key="t10h")

        dt = cron.copy()
        if fc10: dt = dt[dt["centro"].isin(fc10)]
        if fr10: dt = dt[dt["criticidad"].isin(fr10)]
        if rc10=="Solo RC":    dt = dt[dt["es_critica"]==True]
        elif rc10=="Sin RC":   dt = dt[dt["es_critica"]==False]
        if h10=="Dentro 36H":  dt = dt[dt["dentro_horizonte"]==True]
        elif h10=="Fuera 36H": dt = dt[dt["dentro_horizonte"]==False]

        st.caption(f"Mostrando **{len(dt)}** de {n_tot} actividades")
        cols_t = ["centro","actividad","especialidad","ejecutor","criticidad","duracion_h",
                  "start_sd","end_sd","turno","ruta_critica","es_critica",
                  "dentro_horizonte","score","valor_global","acum_total_calc"]
        st.dataframe(
            dt[[c for c in cols_t if c in dt.columns]].sort_values("start_sd").rename(columns={
                "centro":"Centro","actividad":"Actividad","especialidad":"Especialidad",
                "ejecutor":"Ejecutor","criticidad":"Criticidad","duracion_h":"Dur.(h)",
                "start_sd":"Inicio SD","end_sd":"Fin SD","turno":"Turno",
                "ruta_critica":"RC Orig","es_critica":"RC Calc",
                "dentro_horizonte":"Dentro 36H","score":"Score",
                "valor_global":"Valor Global","acum_total_calc":"% Acum Total",
            }),
            use_container_width=True, hide_index=True, height=520,
            column_config={
                "Score": st.column_config.NumberColumn(format="%.3f"),
                "Dur.(h)": st.column_config.NumberColumn(format="%dh"),
                "Inicio SD": st.column_config.NumberColumn(format="SD%d"),
                "Fin SD": st.column_config.NumberColumn(format="SD%d"),
                "% Acum Total": st.column_config.NumberColumn(format="%.1f%%"),
                "Valor Global": st.column_config.NumberColumn(format="%.5f"),
                "Dentro 36H": st.column_config.CheckboxColumn(),
                "RC Calc": st.column_config.CheckboxColumn(),
            }
        )
        st.markdown("---")
        excel_b = exportar_excel(cron)
        st.download_button(
            "📥 Descargar cronograma completo (Excel · 4 hojas)",
            data=excel_b,
            file_name="cronograma_optimizado_sd2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    st.markdown("---")
    st.caption(
        "🏭 Parada de Planta SD18MAR26 · "
        "CPM Greedy + Resource Leveling · "
        "Optimización Multicriterio · "
        "Plotly Interactive"
    )


if __name__ == "__main__":
    main()









































