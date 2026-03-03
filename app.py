# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# VERSIÓN COMPLETA – MES LABORAL REAL
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Simulación Multi-Agente – Planificación Marzo 2026")

DIAS_MES = 31
HORAS_POR_DIA = 6
HORIZONTE_HORAS = DIAS_MES * HORAS_POR_DIA
FECHA_INICIO = datetime(2026, 3, 1)

st.write(f"Horizonte laboral: {DIAS_MES} días × {HORAS_POR_DIA}h = {HORIZONTE_HORAS} horas")

# ============================================================
# PANEL LATERAL
# ============================================================

with st.sidebar:

    st.header("⚙️ Parámetros")

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

    st.subheader("Opciones")

    activar_balance = st.checkbox("Activar balance de carga diaria", value=True)
    peso_atraso = st.slider("Peso atraso", 1, 50, 10)
    peso_balance = st.slider("Peso balance", 1, 300, 100)
    peso_temprano = st.slider("Peso inicio temprano", 0, 20, 2)

# ============================================================
# FASE 0 – GENERADOR OTs
# ============================================================

def generar_ots(n):

    random.seed(42)

    tipos = ["PREV", "PRED", "CORR"]
    criticidades = ["Alta", "Media", "Baja"]
    disciplinas_posibles = ["MEC", "ELE", "INS", "CIV", "MEC | ELE", "MEC | INS"]

    ots = []

    for i in range(1, n + 1):

        tipo = random.choice(tipos)
        criticidad = random.choice(criticidades)
        disciplina = random.choice(disciplinas_posibles)

        if "|" in disciplina:
            discos = [d.strip() for d in disciplina.split("|")]
            horas_list = [random.choice([4,6,8]) for _ in discos]
            tecnicos_list = [random.randint(1,2) for _ in discos]
            horas_str = " | ".join(map(str, horas_list))
            tecnicos_str = " | ".join(map(str, tecnicos_list))
            duracion_total = sum(horas_list)
        else:
            horas = random.choice([4,6,8,10,12])
            tecnicos = random.randint(1,2)
            horas_str = str(horas)
            tecnicos_str = str(tecnicos)
            duracion_total = horas

        dia_inicio = random.randint(1, DIAS_MES)
        dias_necesarios = (duracion_total + HORAS_POR_DIA - 1) // HORAS_POR_DIA
        dia_limite = min(DIAS_MES, dia_inicio + dias_necesarios + random.randint(0,5))

        ots.append({
            "id": f"OT{i:03}",
            "Tipo": tipo,
            "Criticidad": criticidad,
            "Disciplinas": disciplina,
            "Horas": horas_str,
            "Tecnicos": tecnicos_str,
            "Fecha_Inicial": FECHA_INICIO + timedelta(days=dia_inicio - 1),
            "Fecha_Limite": FECHA_INICIO + timedelta(days=dia_limite - 1),
            "Ubicacion": random.choice(["Planta", "Remota"])
        })

    return ots


raw_ots = generar_ots(num_ots)
df_ots = pd.DataFrame(raw_ots)

st.subheader("📋 Órdenes Generadas")
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
todos_intervalos = []

for ot in raw_ots:

    dias_desde_inicio = max(0, (ot["Fecha_Inicial"] - FECHA_INICIO).days)
    inicio_min = dias_desde_inicio * HORAS_POR_DIA

    disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
    horas = [int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

    bloques = []

    for i in range(len(disciplinas)):

        disc = disciplinas[i]
        dur = horas[i]
        demanda = tecnicos[i]

        nombre = f"{ot['id']}_{disc}"

        start = model.NewIntVar(inicio_min, HORIZONTE_HORAS - dur, f"start_{nombre}")
        end = model.NewIntVar(inicio_min + dur, HORIZONTE_HORAS, f"end_{nombre}")
        interval = model.NewIntervalVar(start, dur, end, f"interval_{nombre}")

        start_vars[nombre] = start
        end_vars[nombre] = end

        intervals_por_disciplina[disc].append((interval, demanda))
        todos_intervalos.append((interval, dur))

        if ot["Ubicacion"] == "Remota":
            intervalos_camionetas.append(interval)
            demandas_camionetas.append(1)

        bloques.append(nombre)

    # Precedencia en serie
    for i in range(len(bloques)-1):
        model.Add(start_vars[bloques[i+1]] >= end_vars[bloques[i]])

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
# FASE 3 – FUNCIÓN OBJETIVO
# ============================================================

atrasos = []
bloques_tempranos = []

for nombre in start_vars:

    ot_id = nombre.split("_")[0]
    ot = next(o for o in raw_ots if o["id"] == ot_id)

    fin = end_vars[nombre]

    dias_limite = max(0, (ot["Fecha_Limite"] - FECHA_INICIO).days + 1)
    limite_horas = dias_limite * HORAS_POR_DIA

    atraso = model.NewIntVar(0, HORIZONTE_HORAS, f"atraso_{nombre}")
    model.Add(atraso >= fin - limite_horas)
    model.Add(atraso >= 0)

    atrasos.append(atraso)

    start = start_vars[nombre]
    temprano = model.NewBoolVar(f"temprano_{nombre}")
    model.Add(start < 5 * HORAS_POR_DIA).OnlyEnforceIf(temprano)
    model.Add(start >= 5 * HORAS_POR_DIA).OnlyEnforceIf(temprano.Not())
    bloques_tempranos.append(temprano)

penalizacion_temprana = model.NewIntVar(0, len(bloques_tempranos), "penalizacion_temprana")
model.Add(penalizacion_temprana == sum(bloques_tempranos))

if activar_balance:

    carga_diaria = []

    for dia in range(DIAS_MES):

        inicio_dia = dia * HORAS_POR_DIA
        fin_dia = (dia+1) * HORAS_POR_DIA

        contribuciones = []

        for intervalo, duracion in todos_intervalos:

            base = intervalo.Name().replace("interval_", "")
            start = start_vars[base]
            end = end_vars[base]

            activo = model.NewBoolVar(f"activo_{dia}_{base}")

            model.Add(start < fin_dia).OnlyEnforceIf(activo)
            model.Add(end > inicio_dia).OnlyEnforceIf(activo)
            model.Add(start >= fin_dia).OnlyEnforceIf(activo.Not())
            model.Add(end <= inicio_dia).OnlyEnforceIf(activo.Not())

            contrib = model.NewIntVar(0, duracion, f"contrib_{dia}_{base}")
            model.Add(contrib == duracion).OnlyEnforceIf(activo)
            model.Add(contrib == 0).OnlyEnforceIf(activo.Not())

            contribuciones.append(contrib)

        carga = model.NewIntVar(0, 1000, f"carga_{dia}")
        model.Add(carga == sum(contribuciones))
        carga_diaria.append(carga)

    max_carga = model.NewIntVar(0, 1000, "max_carga")
    model.AddMaxEquality(max_carga, carga_diaria)

    model.Minimize(
        peso_atraso * sum(atrasos)
        + peso_balance * max_carga
        + peso_temprano * penalizacion_temprana
    )

else:

    model.Minimize(
        peso_atraso * sum(atrasos)
        + peso_temprano * penalizacion_temprana
    )

# ============================================================
# FASE 4 – RESOLUCIÓN
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
status = solver.Solve(model)

# ============================================================
# RESULTADOS
# ============================================================

if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:

    resultados = []

    for nombre in start_vars:

        inicio = solver.Value(start_vars[nombre])
        fin = solver.Value(end_vars[nombre])

        dia_inicio = inicio // HORAS_POR_DIA
        dia_fin = fin // HORAS_POR_DIA

        resultados.append({
            "Bloque": nombre,
            "OT": nombre.split("_")[0],
            "Inicio (h)": inicio,
            "Fin (h)": fin,
            "Inicio_dt": FECHA_INICIO + timedelta(days=dia_inicio),
            "Fin_dt": FECHA_INICIO + timedelta(days=dia_fin)
        })

    df = pd.DataFrame(resultados).sort_values("Inicio (h)")

    st.subheader("📊 Programación Final")
    st.dataframe(df, use_container_width=True)

    fig = px.timeline(
        df,
        x_start="Inicio_dt",
        x_end="Fin_dt",
        y="OT",
        color="OT",
        title="📅 Gantt – Mes Completo"
    )

    fig.update_layout(height=1000)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=DIAS_MES)])

    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("No se encontró solución factible.")
