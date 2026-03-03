# ============================================================
# PLANIFICADOR MENSUAL CON ASIGNACIÓN EXPLÍCITA DE TÉCNICOS
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("🧠 Planificador Mensual con Asignación de Técnicos")

# ============================================================
# PARÁMETROS
# ============================================================

HORAS_POR_DIA = 6
DIAS_MES = 30
HORIZONTE = HORAS_POR_DIA * DIAS_MES
FECHA_INICIO = datetime(2026, 3, 1)

with st.sidebar:
    st.header("Capacidad Disponible")
    cap_mec = st.number_input("Técnicos MEC", 1, 10, 3)
    cap_ele = st.number_input("Técnicos ELE", 1, 10, 2)
    camionetas = st.number_input("Camionetas", 1, 5, 2)
    num_ots = st.slider("Número de OTs", 10, 60, 30)

# Crear lista de técnicos individuales
tecnicos = {
    "MEC": [f"MEC_{i+1}" for i in range(cap_mec)],
    "ELE": [f"ELE_{i+1}" for i in range(cap_ele)]
}

# ============================================================
# GENERADOR DE OTs
# ============================================================

def generar_ots(n):
    random.seed(42)
    ots = []
    for i in range(n):
        ots.append({
            "id": f"OT{i+1:03}",
            "Disciplina": random.choice(["MEC","ELE"]),
            "Duracion": random.choice([6, 12]),
            "Criticidad": random.choice(["Alta","Media","Baja"]),
            "Ubicacion": random.choice(["Planta","Remota"])
        })
    return ots

raw_ots = generar_ots(num_ots)
st.subheader("📥 OTs Recibidas")
st.dataframe(pd.DataFrame(raw_ots), use_container_width=True)

# ============================================================
# MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

start_vars = {}
end_vars = {}
ejecutar_vars = {}
asignacion_vars = {}

intervalos_camionetas = []

peso_reprogramacion = {"Alta":1000, "Media":300, "Baja":50}
penalizaciones = []

# ============================================================
# CREACIÓN DE VARIABLES
# ============================================================

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

    # ===== ASIGNACIÓN A UN SOLO TÉCNICO =====
    asignaciones_ot = []

    for tec in tecnicos[ot["Disciplina"]]:
        var = model.NewBoolVar(f"{nombre}_asig_{tec}")
        asignaciones_ot.append(var)
        asignacion_vars[(nombre, tec)] = var

    # Si se ejecuta debe tener exactamente 1 técnico
    model.Add(sum(asignaciones_ot) == ejecutar)

    # Camionetas si es remota
    if ot["Ubicacion"] == "Remota":
        intervalos_camionetas.append(interval)

    # Penalización si no se ejecuta
    no_exec = model.NewIntVar(0,1,f"noexec_{nombre}")
    model.Add(no_exec == 1 - ejecutar)
    penalizaciones.append(peso_reprogramacion[ot["Criticidad"]] * no_exec)

# ============================================================
# LÍMITE DIARIO POR TÉCNICO (6 HORAS)
# ============================================================

for disc in tecnicos:
    for tec in tecnicos[disc]:

        for dia in range(DIAS_MES):

            inicio_dia = dia * HORAS_POR_DIA
            fin_dia = (dia + 1) * HORAS_POR_DIA

            contribuciones = []

            for ot in raw_ots:
                if ot["Disciplina"] != disc:
                    continue

                nombre = ot["id"]
                dur = ot["Duracion"]

                activo = model.NewBoolVar(f"activo_{nombre}_{tec}_{dia}")

                model.Add(start_vars[nombre] < fin_dia).OnlyEnforceIf(activo)
                model.Add(end_vars[nombre] > inicio_dia).OnlyEnforceIf(activo)
                model.Add(start_vars[nombre] >= fin_dia).OnlyEnforceIf(activo.Not())
                model.Add(end_vars[nombre] <= inicio_dia).OnlyEnforceIf(activo.Not())

                contrib = model.NewIntVar(0, dur, f"contrib_{nombre}_{tec}_{dia}")

                model.Add(contrib == dur).OnlyEnforceIf(
                    [activo, asignacion_vars[(nombre, tec)]]
                )
                model.Add(contrib == 0).OnlyEnforceIf(activo.Not())

                contribuciones.append(contrib)

            if contribuciones:
                model.Add(sum(contribuciones) <= HORAS_POR_DIA)

# ============================================================
# CAMIONETAS
# ============================================================

if intervalos_camionetas:
    model.AddCumulative(
        intervalos_camionetas,
        [1]*len(intervalos_camionetas),
        camionetas
    )

# ============================================================
# FUNCIÓN OBJETIVO
# ============================================================

model.Minimize(sum(penalizaciones))

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

        if ejecutada:

            inicio = solver.Value(start_vars[nombre])
            fin = solver.Value(end_vars[nombre])
            fecha_inicio = FECHA_INICIO + timedelta(hours=inicio)

            # Buscar técnico asignado
            tecnico_asignado = None
            for tec in tecnicos[ot["Disciplina"]]:
                if solver.Value(asignacion_vars[(nombre, tec)]) == 1:
                    tecnico_asignado = tec
                    break

            estado = "Programada"

        else:
            fecha_inicio = None
            tecnico_asignado = None
            estado = "Reprogramada"

        resultados.append({
            "OT": nombre,
            "Disciplina": ot["Disciplina"],
            "Criticidad": ot["Criticidad"],
            "Estado": estado,
            "Técnico Asignado": tecnico_asignado,
            "Fecha Inicio": fecha_inicio
        })

    df_resultado = pd.DataFrame(resultados)

    st.subheader("📊 Resultado de Planificación")
    st.dataframe(df_resultado, use_container_width=True)

    total = len(df_resultado)
    programadas = len(df_resultado[df_resultado["Estado"]=="Programada"])
    reprogramadas = total - programadas

    col1, col2, col3 = st.columns(3)
    col1.metric("Total OTs", total)
    col2.metric("Programadas", programadas)
    col3.metric("Reprogramadas", reprogramadas)

else:
    st.error("No se encontró solución.")
