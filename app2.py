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
import math
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



def calcular_pesos(especialidades):

    esp = sorted(set(especialidades))

    # 1 especialidad
    if len(esp) == 1:
        return {esp[0]: 1.0}

    # 2 especialidades
    if len(esp) == 2:

        if set(esp) == {"MECÁNICA", "ELÉCTRICA"}:
            return {"MECÁNICA": 0.65, "ELÉCTRICA": 0.35}

        if set(esp) == {"MECÁNICA", "INSTRUMENTACIÓN"}:
            return {"MECÁNICA": 0.70, "INSTRUMENTACIÓN": 0.30}

        if set(esp) == {"ELÉCTRICA", "INSTRUMENTACIÓN"}:
            return {"ELÉCTRICA": 0.60, "INSTRUMENTACIÓN": 0.40}

    # 3 especialidades
    return {
        "MECÁNICA": 0.5,
        "ELÉCTRICA": 0.3,
        "INSTRUMENTACIÓN": 0.2
    }
# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3C: TECNICOS POR ORDEN DE TRABAJO
# ─────────────────────────────────────────────────────────────────────────────
def tecnicos_por_ot(df):

    HORAS_TECNICO = 8

    def redondear_hora(valor):
        entero = int(valor)
        decimal = valor - entero
        if decimal >= 0.5:
            return entero + 1
        else:
            return entero

    rows = []

    for _, act in df.iterrows():

        dur = act["duracion_h"]

        esp_list = (
            str(act["especialidad"])
            .replace("/", ",")
            .replace("INSTRUMENTACION", "INSTRUMENTACIÓN")
            .upper()
            .split(",")
        )

        esp_list = [e.strip() for e in esp_list if e.strip()]

        # NUEVA LÓGICA DE PESOS
        pesos = calcular_pesos(esp_list)

        for esp, peso in pesos.items():

            horas = round(dur * peso, 2)

            horas_redondeadas = redondear_hora(horas)

            tecnicos = int(np.ceil(horas_redondeadas / HORAS_TECNICO))

            rows.append({
                "Orden": act["orden"],
                "Actividad": act["actividad"],
                "Centro": act["centro"],
                "Especialidad": esp,
                "Duracion_h": dur,
                "Horas_Especialidad": horas,
                "Horas_Redondeadas": horas_redondeadas,
                "Tecnicos_Requeridos": tecnicos
            })

    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────
# MÓDULO 3D-A – DIVISIÓN DE ESPECIALIDADES (CORREGIDO)
# ─────────────────────────────────────────────────────────

def dividir_especialidades(cron):

    def redondear_hora(valor):
        entero = int(valor)
        decimal = valor - entero
        if decimal >= 0.5:
            return entero + 1
        else:
            return entero

    filas = []

    for _, r in cron.iterrows():

        especialidades = (
            str(r["especialidad"])
            .replace("/", ",")
            .replace("INSTRUMENTACION", "INSTRUMENTACIÓN")
            .upper()
            .split(",")
        )

        especialidades = [e.strip() for e in especialidades if e.strip()]

        # NUEVA LÓGICA
        pesos = calcular_pesos(especialidades)

        for esp, peso in pesos.items():

            nuevo = r.to_dict()

            horas = round(r["duracion_h"] * peso, 2)

            nuevo["especialidad"] = esp
            nuevo["duracion_h"] = redondear_hora(horas)

            filas.append(nuevo)

    return pd.DataFrame(filas)
    
# ─────────────────────────────────────────────────────────
# MÓDULO 3D – OPTIMIZADOR DE TÉCNICOS (VERSIÓN FINAL)
# ─────────────────────────────────────────────────────────

def optimizar_tecnicos_turnos(cron, horizonte=36):
    import math
    import pandas as pd

    cron = cron.copy()
    cron["hh_restantes"] = cron["duracion_h"]

    TURNOS = [(0,8),(24,32)]  # Turnos diarios
    HORAS_TECNICO = 16        # Capacidad total por técnico

    # Calcular demanda por centro y especialidad
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

    # Crear matriz vacía
    matriz = pd.DataFrame(
        "",
        index=tecnicos["tecnico"],
        columns=list(range(horizonte))
    )

    # Diccionario para guardar OT pendiente por técnico
    actividad_pendiente = {}  # {tecnico: ot_idx}

    # Recorrer técnicos
    for _, t in tecnicos.iterrows():
        centro = t["centro"]
        esp = t["especialidad"]

        for inicio, fin in TURNOS:
            horas_turno = fin - inicio
            h = inicio

            while horas_turno > 0:

                # Priorizar OT pendiente
                ot_idx = actividad_pendiente.get(t["tecnico"], None)

                if ot_idx is None:
                    ots = cron[
                        (cron["centro"] == centro) &
                        (cron["especialidad"] == esp) &
                        (cron["hh_restantes"] > 0)
                    ]
                    if ots.empty:
                        break
                    ot_idx = ots.sort_values("hh_restantes", ascending=False).iloc[0].name

                orden = cron.loc[ot_idx, "orden"]

                # Bloque a asignar: mínimo entre horas del turno y horas restantes de la OT
                bloque = min(horas_turno, cron.loc[ot_idx,"hh_restantes"])

                # Asignar horas consecutivas en la matriz
                for i in range(bloque):
                    matriz.loc[t["tecnico"], h] = orden
                    h += 1

                # Actualizar horas restantes
                cron.loc[ot_idx,"hh_restantes"] -= bloque
                horas_turno -= bloque

                # Si la OT no terminó, guardar pendiente para el próximo turno
                if cron.loc[ot_idx,"hh_restantes"] > 0:
                    actividad_pendiente[t["tecnico"]] = ot_idx
                else:
                    actividad_pendiente.pop(t["tecnico"], None)

    return matriz
    
# ─────────────────────────────────────────────────────────
# MÓDULO 3E: GANTT POR ORDEN DE TRABAJO
# ─────────────────────────────────────────────────────────
def plot_gantt_ot_simple(matriz):
    import pandas as pd
    import plotly.express as px
    import datetime

    inicio_sd = datetime.datetime(2026,3,18,6,0,0)  # Miércoles 18, 6:00
    bloques = []

    for tec, row in matriz.iterrows():
        prev_ot = None
        start_h = None
        for h, ot in enumerate(row):
            if ot == "":
                if prev_ot is not None:
                    bloques.append({
                        "orden": prev_ot,
                        "tecnico": tec,
                        "start": inicio_sd + datetime.timedelta(hours=start_h),
                        "end": inicio_sd + datetime.timedelta(hours=h)
                    })
                    prev_ot = None
                    start_h = None
                continue

            if ot != prev_ot:
                if prev_ot is not None:
                    bloques.append({
                        "orden": prev_ot,
                        "tecnico": tec,
                        "start": inicio_sd + datetime.timedelta(hours=start_h),
                        "end": inicio_sd + datetime.timedelta(hours=h)
                    })
                prev_ot = ot
                start_h = h

        if prev_ot is not None:
            bloques.append({
                "orden": prev_ot,
                "tecnico": tec,
                "start": inicio_sd + datetime.timedelta(hours=start_h),
                "end": inicio_sd + datetime.timedelta(hours=len(row))
            })

    df_bloques = pd.DataFrame(bloques)

    # 🔹 Aseguramos que todas las OTs aparezcan en el eje Y
    ordenes = sorted(df_bloques["orden"].unique())
    df_bloques["orden"] = pd.Categorical(df_bloques["orden"], categories=ordenes, ordered=True)

    # Gráfico Gantt
    fig = px.timeline(
        df_bloques,
        x_start="start",
        x_end="end",
        y="orden",
        color="tecnico",
        title="📊 Gantt por Orden de Trabajo",
        labels={"orden":"Orden de Trabajo","tecnico":"Técnico"}
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(400, len(df_bloques["orden"].unique())*25))
    return fig
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
                df_tecnicos_ot  = tecnicos_por_ot(cron)
                cron = dividir_especialidades(cron)
                matriz_tecnicos = optimizar_tecnicos_turnos(cron)          
                st.session_state.update({"cron": cron, "cs": cs, "tecnicos_ot": df_tecnicos_ot, "cron":cron, "matriz_tecnicos": matriz_tecnicos})
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.exception(e)
                return
        st.success("✅ Simulación completada")

    cron = st.session_state["cron"]
    cs   = st.session_state["cs"]
    df_tecnicos_ot = st.session_state["tecnicos_ot"]
    cron = st.session_state["cron"]
    matriz_tecnicos = st.session_state["matriz_tecnicos"]


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

    st.subheader("👷 Técnicos requeridos por Orden de Trabajo")
    st.dataframe(df_tecnicos_ot)

    # ── FILTROS EN STREAMLIT PARA MATRIZ DE TÉCNICOS ──
    st.subheader("📅 Planificación de técnicos por hora")
    st.caption("Cada fila es un técnico. Cada columna es una hora SD (0-36).")
    
    centros_disponibles = sorted(matriz_tecnicos.index.str.split("_").str[0].unique())
    filtro_centro = st.multiselect("Filtrar por Centro", centros_disponibles)
    
    ordenes_disponibles = sorted(cron["orden"].dropna().astype(str).unique())
    filtro_orden = st.selectbox("Resaltar Orden de Trabajo", [""] + ordenes_disponibles)

    matriz_filtrada = matriz_tecnicos.copy()
    if filtro_centro:
        matriz_filtrada = matriz_filtrada[
           matriz_filtrada.index.str.split("_").str[0].isin(filtro_centro)
    ]

    def highlight_ot(val):
        val_str = str(val)  # Convertimos todo a string
        if filtro_orden and filtro_orden in val_str:
            return "background-color: #FFD700"
        return ""

    st.dataframe(matriz_filtrada.style.applymap(highlight_ot))

    st.subheader("📊 Gantt por Orden de Trabajo (por horas de técnicos)")
    st.caption("Cada barra = horas trabajadas de una OT por técnico")
    st.plotly_chart(plot_gantt_ot_simple(matriz_tecnicos), use_container_width=True)

    
    # ── TABS ──
    tabs = st.tabs([
        "📅 Gantt Actividades",
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


if __name__ == "__main__":
    main()
