=============================================================================
APP STREAMLIT - SIMULACIÓN PARADA DE PLANTA SD18MAR26
Visualizaciones 100% interactivas con Plotly (zoom, hover, filtros)
=============================================================================
Instalación:
    pip install streamlit pandas openpyxl plotly numpy

Ejecución:
    streamlit run app_paro_planta.py
=============================================================================
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

    import numpy as np
    import pandas as pd

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

    import pandas as pd

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
