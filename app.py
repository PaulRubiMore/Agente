# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# VERSIÓN CORREGIDA – MES LABORAL COMPLETO
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Simulación Multi-Agente – Planificación Óptima Marzo 2026")

# ============================================================
# PARÁMETROS GENERALES
# ============================================================

DIAS_MES = 31
HORAS_POR_DIA = 6
HORIZONTE_HORAS = DIAS_MES * HORAS_POR_DIA
FECHA_INICIO = datetime(2026, 3, 1)

st.write(f"Horizonte laboral: {DIAS_MES} días x {HORAS_POR_DIA}h = {HORIZONTE_HORAS} horas")

# ============================================================
# PANEL LATERAL
# ============================================================

with st.sidebar:
    st.header("⚙️ Parámetros del Modelo")

    num_ots = st.slider("Número de OTs", 50, 200, 60, step=10)

    st.subheader("Capacidad Técnicos")
    cap_mec = st.number_input("MEC", 1, 20, 6)
    cap_ele = st.number_input("ELE", 1, 20, 4)
    cap_ins = st.number_input("INS", 1, 20, 3)
    cap_civ = st.number_input("CIV", 1, 20, 3)

    capacidad_disciplina = {
        "MEC": cap_mec,
        "ELE": cap_ele,
        "INS": cap_ins,
        "CIV": cap_civ
    }

    camionetas = st.number_input("Camionetas", 1, 20, 3)

# ============================================================
# FASE 0 – GENERACIÓN OTs
# ============================================================

def generar_ots(n):
    random.seed(42)
    tipos = ["PREV", "PRED", "CORR"]
    criticidades = ["Alta", "Media", "Baja"]
    disciplinas = ["MEC", "ELE", "INS", "CIV"]

    ots = []

    for i in range(1, n + 1):

        tipo = random.choice(tipos)
        criticidad = random.choice(criticidades)
        disc = random.choice(disciplinas)

        horas = random.choice([4, 6, 8, 10, 12])
        tecnicos = random.randint(1, 2)

        dia_inicio = random.randint(1, DIAS_MES)
        dias_necesarios = (horas + HORAS_POR_DIA - 1) // HORAS_POR_DIA
        dia_limite = min(DIAS_MES, dia_inicio + dias_necesarios + random.randint(0,5))

        ots.append({
            "id": f"OT{i:03}",
            "Tipo": tipo,
            "Criticidad": criticidad,
            "Disciplina": disc,
            "Horas": horas,
            "Tecnicos": tecnicos,
            "Fecha_Inicial": FECHA_INICIO + timedelta(days=dia_inicio - 1),
            "Fecha_Limite": FECHA_INICIO + timedelta(days=dia_limite - 1),
            "Ubicacion": random.choice(["Planta", "Remota"])
        })

    return ots

raw_ots = generar_ots(num_ots)
df_ots = pd.DataFrame(raw_ots)

st.subheader("📋 OTs Generadas")
st.dataframe(df_ots, use_container_width=True)

# ============================================================
# FASE 1 – MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
intervalos_camionetas = []
demandas_camionetas = []

start_vars = {}
end_vars = {}

for ot in raw_ots:

    dias_desde_inicio = max(0, (ot["Fecha_Inicial"] - FECHA_INICIO).days)
    inicio_min = dias_desde_inicio * HORAS_POR_DIA

    duracion = ot["Horas"]
    demanda = ot["Tecnicos"]
    disc = ot["Disciplina"]

    nombre = ot["id"]

    start = model.NewIntVar(inicio_min, HORIZONTE_HORAS - duracion, f"start_{nombre}")
    end = model.NewIntVar(inicio_min + duracion, HORIZONTE_HORAS, f"end_{nombre}")
    interval = model.NewIntervalVar(start, duracion, end, f"interval_{nombre}")

    start_vars[nombre] = start
    end_vars[nombre] = end

    intervals_por_disciplina[disc].append((interval, demanda))

    if ot["Ubicacion"] == "Remota":
        intervalos_camionetas.append(interval)
        demandas_camionetas.append(1)

# ============================================================
# FASE 2 – RESTRICCIONES
# ============================================================

for disc, lista in intervals_por_disciplina.items():
    if lista:
        model.AddCumulative(
            [i[0] for i in lista],
            [i[1] for i in lista],
            capacidad_disciplina[disc]
        )

if intervalos_camionetas:
    model.AddCumulative(
        intervalos_camionetas,
        demandas_camionetas,
        camionetas
    )

# ============================================================
# FASE 3 – ATRASOS
# ============================================================

atrasos = []

for ot in raw_ots:

    nombre = ot["id"]
    fin = end_vars[nombre]

    dias_hasta_limite = max(0, (ot["Fecha_Limite"] - FECHA_INICIO).days + 1)
    limite_horas = dias_hasta_limite * HORAS_POR_DIA

    atraso = model.NewIntVar(0, HORIZONTE_HORAS, f"atraso_{nombre}")
    model.Add(atraso >= fin - limite_horas)
    model.Add(atraso >= 0)

    atrasos.append(atraso)

model.Minimize(sum(atrasos))

# ============================================================
# FASE 4 – RESOLUCIÓN
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
status = solver.Solve(model)

# ============================================================
# RESULTADOS
# ============================================================

if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:

    resultados = []

    for ot in raw_ots:

        nombre = ot["id"]
        inicio = solver.Value(start_vars[nombre])
        fin = solver.Value(end_vars[nombre])

        dia_inicio = inicio // HORAS_POR_DIA
        dia_fin = fin // HORAS_POR_DIA

        fecha_inicio_prog = FECHA_INICIO + timedelta(days=dia_inicio)
        fecha_fin_prog = FECHA_INICIO + timedelta(days=dia_fin)

        resultados.append({
            "OT": nombre,
            "Disciplina": ot["Disciplina"],
            "Inicio (h)": inicio,
            "Fin (h)": fin,
            "Inicio_dt": fecha_inicio_prog,
            "Fin_dt": fecha_fin_prog
        })

    df = pd.DataFrame(resultados)

    st.subheader("📊 Resultado Programación")
    st.dataframe(df, use_container_width=True)

    # ============================================================
    # GANTT
    # ============================================================

    fig = px.timeline(
        df,
        x_start="Inicio_dt",
        x_end="Fin_dt",
        y="OT",
        color="Disciplina",
        title="📅 Gantt – Mes Completo Marzo 2026"
    )

    fig.update_layout(height=900)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=DIAS_MES)])

    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("No se encontró solución factible.")
