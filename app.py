# ============================================================
# PLANIFICADOR INDUSTRIAL MENSUAL CON REPROGRAMACIÓN AUTOMÁTICA
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("🧠 Planificador Mensual Inteligente")

# ============================================================
# PARÁMETROS
# ============================================================

HORAS_POR_DIA = 6
DIAS_MES = 30
HORIZONTE = HORAS_POR_DIA * DIAS_MES
FECHA_INICIO = datetime(2026, 3, 1)

with st.sidebar:
    st.header("Capacidad")
    cap_mec = st.number_input("MEC", 1, 20, 4)
    cap_ele = st.number_input("ELE", 1, 20, 3)
    cap_ins = st.number_input("INS", 1, 20, 2)
    cap_civ = st.number_input("CIV", 1, 20, 2)
    camionetas = st.number_input("Camionetas", 1, 10, 2)

    num_ots = st.slider("Número de OTs", 20, 100, 40)

capacidad = {
    "MEC": cap_mec,
    "ELE": cap_ele,
    "INS": cap_ins,
    "CIV": cap_civ
}

# ============================================================
# GENERADOR DE OTs
# ============================================================

def generar_ots(n):
    random.seed(42)
    tipos = ["CORR", "PRED", "PREV"]
    criticidades = ["Alta", "Media", "Baja"]
    disciplinas = ["MEC", "ELE", "INS", "CIV"]

    ots = []

    for i in range(n):
        duracion = random.choice([6, 12, 18])
        ots.append({
            "id": f"OT{i+1:03}",
            "Tipo": random.choice(tipos),
            "Criticidad": random.choice(criticidades),
            "Disciplina": random.choice(disciplinas),
            "Duracion": duracion,
            "Ubicacion": random.choice(["Planta", "Remota"])
        })

    return ots

raw_ots = generar_ots(num_ots)
df_input = pd.DataFrame(raw_ots)
st.subheader("OTs Recibidas")
st.dataframe(df_input, use_container_width=True)

# ============================================================
# MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervalos_por_disciplina = {d: [] for d in capacidad}
intervalos_camionetas = []

start_vars = {}
end_vars = {}
ejecutar_vars = {}

penalizaciones_no_ejecutadas = []

# Pesos por criticidad
peso_reprogramacion = {
    "Alta": 1000,
    "Media": 300,
    "Baja": 50
}

for ot in raw_ots:

    nombre = ot["id"]
    dur = ot["Duracion"]

    start = model.NewIntVar(0, HORIZONTE - dur, f"start_{nombre}")
    end = model.NewIntVar(0, HORIZONTE, f"end_{nombre}")
    ejecutar = model.NewBoolVar(f"ejecutar_{nombre}")

    interval = model.NewOptionalIntervalVar(
        start, dur, end, ejecutar, f"interval_{nombre}"
    )

    start_vars[nombre] = start
    end_vars[nombre] = end
    ejecutar_vars[nombre] = ejecutar

    # Capacidad disciplina
    intervalos_por_disciplina[ot["Disciplina"]].append((interval, 1))

    # Camioneta si es remota
    if ot["Ubicacion"] == "Remota":
        intervalos_camionetas.append(interval)

    # Penalización si NO se ejecuta
    no_ejecutada = model.NewIntVar(0, 1, f"no_exec_{nombre}")
    model.Add(no_ejecutada == 1 - ejecutar)

    penalizaciones_no_ejecutadas.append(
        peso_reprogramacion[ot["Criticidad"]] * no_ejecutada
    )

# ============================================================
# RESTRICCIONES DE CAPACIDAD
# ============================================================

for disc, intervalos in intervalos_por_disciplina.items():
    if intervalos:
        model.AddCumulative(
            [i[0] for i in intervalos],
            [i[1] for i in intervalos],
            capacidad[disc]
        )

if intervalos_camionetas:
    model.AddCumulative(
        intervalos_camionetas,
        [1]*len(intervalos_camionetas),
        camionetas
    )

# ============================================================
# FUNCIÓN OBJETIVO
# ============================================================

model.Minimize(sum(penalizaciones_no_ejecutadas))

# ============================================================
# RESOLVER
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
        ejecutada = solver.Value(ejecutar_vars[nombre])

        if ejecutada == 1:
            inicio = solver.Value(start_vars[nombre])
            fin = solver.Value(end_vars[nombre])
            fecha_inicio = FECHA_INICIO + timedelta(hours=inicio)
            estado = "Programada"
        else:
            fecha_inicio = None
            fin = None
            estado = "Reprogramada"

        resultados.append({
            "OT": nombre,
            "Tipo": ot["Tipo"],
            "Criticidad": ot["Criticidad"],
            "Disciplina": ot["Disciplina"],
            "Estado": estado,
            "Inicio": fecha_inicio
        })

    df = pd.DataFrame(resultados)
    st.subheader("Resultado de Planificación")
    st.dataframe(df, use_container_width=True)

    total = len(df)
    ejecutadas = len(df[df["Estado"] == "Programada"])
    reprogramadas = total - ejecutadas

    col1, col2, col3 = st.columns(3)
    col1.metric("Total OTs", total)
    col2.metric("Programadas", ejecutadas)
    col3.metric("Reprogramadas", reprogramadas)

else:
    st.error("No se encontró solución.")
