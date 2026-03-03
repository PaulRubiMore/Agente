import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("🧠 Planificador Mensual con Prioridad y Backlog")

# ==============================
# PARÁMETROS
# ==============================
HORAS_POR_DIA = 6
DIAS_MES = 30
HORIZONTE = HORAS_POR_DIA * DIAS_MES
FECHA_INICIO = datetime(2026, 3, 1)

with st.sidebar:
    st.header("Capacidad y Recursos")
    cap_mec = st.number_input("Técnicos MEC", 1, 10, 3)
    cap_ele = st.number_input("Técnicos ELE", 1, 10, 2)
    camionetas = st.number_input("Camionetas", 1, 5, 2)
    num_ots = st.slider("Número de OTs", 10, 60, 30)

# Lista de técnicos individuales
tecnicos = {
    "MEC": [f"MEC_{i+1}" for i in range(cap_mec)],
    "ELE": [f"ELE_{i+1}" for i in range(cap_ele)]
}

# ==============================
# GENERACIÓN DE OTs
# ==============================
def generar_ots(n):
    random.seed(42)
    ots = []
    tipos = ["CORR","PRED","PREV"]
    criticidades = ["Alta","Media","Baja"]
    for i in range(n):
        tipo = random.choice(tipos)
        crit = random.choice(criticidades)
        disc = random.choice(["MEC","ELE"])
        dur = random.choice([6,12])
        ots.append({
            "id": f"OT{i+1:03}",
            "Disciplina": disc,
            "Duracion": dur,
            "Criticidad": crit,
            "Tipo": tipo,
            "Ubicacion": random.choice(["Planta","Remota"])
        })
    return ots

raw_ots = generar_ots(num_ots)
st.subheader("📥 OTs Recibidas")
st.dataframe(pd.DataFrame(raw_ots), use_container_width=True)

# ==============================
# PRIORIZACIÓN
# ==============================
def score_ot(ot):
    tipo_score = {"CORR":100,"PRED":60,"PREV":40}[ot["Tipo"]]
    crit_score = {"Alta":30,"Media":20,"Baja":10}[ot["Criticidad"]]
    return tipo_score + crit_score

raw_ots.sort(key=lambda x: score_ot(x), reverse=True)

# ==============================
# MODELO CP-SAT
# ==============================
model = cp_model.CpModel()
start_vars = {}
end_vars = {}
ejecutar_vars = {}
asignacion_vars = {}
intervalos_camionetas = []

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

    # Asignación de un técnico por OT
    asignaciones_ot = []
    for tec in tecnicos[ot["Disciplina"]]:
        var = model.NewBoolVar(f"{nombre}_asig_{tec}")
        asignaciones_ot.append(var)
        asignacion_vars[(nombre, tec)] = var

    # Si se ejecuta debe tener exactamente 1 técnico
    model.Add(sum(asignaciones_ot) == ejecutar)

    # Camioneta si es remota
    if ot["Ubicacion"] == "Remota":
        intervalos_camionetas.append(interval)

# ==============================
# LÍMITE DIARIO POR TÉCNICO
# ==============================
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
                model.Add(contrib == dur).OnlyEnforceIf([activo, asignacion_vars[(nombre, tec)]])
                model.Add(contrib == 0).OnlyEnforceIf(activo.Not())
                contribuciones.append(contrib)
            if contribuciones:
                model.Add(sum(contribuciones) <= HORAS_POR_DIA)

# ==============================
# RESTRICCIÓN DE CAMIONETAS
# ==============================
if intervalos_camionetas:
    model.AddCumulative(
        intervalos_camionetas,
        [1]*len(intervalos_camionetas),
        camionetas
    )

# ==============================
# FUNCIÓN OBJETIVO
# Minimizar OTs no ejecutadas (Backlog)
# ==============================
penalizaciones = []
for ot in raw_ots:
    nombre = ot["id"]
    peso = {"Alta":1000,"Media":300,"Baja":50}[ot["Criticidad"]]
    no_exec = model.NewIntVar(0,1,f"noexec_{nombre}")
    model.Add(no_exec == 1 - ejecutar_vars[nombre])
    penalizaciones.append(no_exec * peso)

model.Minimize(sum(penalizaciones))

# ==============================
# RESOLVER
# ==============================
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
status = solver.Solve(model)

# ==============================
# RESULTADOS
# ==============================
resultados = []
if status in [cp_model.FEASIBLE, cp_model.OPTIMAL]:
    for ot in raw_ots:
        nombre = ot["id"]
        ejecutada = solver.Value(ejecutar_vars[nombre])
        if ejecutada:
            inicio = solver.Value(start_vars[nombre])
            fecha_inicio = FECHA_INICIO + timedelta(hours=inicio)
            tecnico_asignado = None
            for tec in tecnicos[ot["Disciplina"]]:
                if solver.Value(asignacion_vars[(nombre, tec)]) == 1:
                    tecnico_asignado = tec
                    break
            estado = "Programada"
        else:
            fecha_inicio = None
            tecnico_asignado = None
            estado = "Backlog"
        resultados.append({
            "OT": nombre,
            "Disciplina": ot["Disciplina"],
            "Criticidad": ot["Criticidad"],
            "Tipo": ot["Tipo"],
            "Estado": estado,
            "Técnico Asignado": tecnico_asignado,
            "Fecha Inicio": fecha_inicio
        })
    df_res = pd.DataFrame(resultados)
    st.subheader("📊 Planificación Mensual Prioritaria")
    st.dataframe(df_res, use_container_width=True)

    total = len(df_res)
    prog = len(df_res[df_res["Estado"]=="Programada"])
    backlog = total - prog
    col1,col2,col3 = st.columns(3)
    col1.metric("Total OTs", total)
    col2.metric("Programadas", prog)
    col3.metric("Backlog", backlog)
else:
    st.error("No se encontró solución factible.")
