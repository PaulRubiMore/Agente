# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# VERSIÓN DISTRIBUCIÓN COMPLETA DEL MES
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (Distribución Mensual)")
st.markdown("Planificación Óptima Marzo 2026")

# ============================================================
# PARÁMETROS
# ============================================================

with st.sidebar:
    st.header("⚙️ Parámetros")

    num_ots = st.slider("Número de OTs", 50, 200, 80, step=10)

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

    peso_atrasos = st.slider("Peso Atrasos", 1, 50, 20)
    peso_balance = st.slider("Peso Balance Mensual", 1, 50, 10)

# ============================================================
# CONSTANTES
# ============================================================

HORAS_POR_DIA = 6
DIAS_MES = 31
HORIZONTE_HORAS = HORAS_POR_DIA * DIAS_MES
FECHA_INICIO = datetime(2026, 3, 1)

# ============================================================
# GENERADOR DE OTs
# ============================================================

def generar_ots(n):
    random.seed(42)
    tipos = ["PREV", "PRED", "CORR"]
    criticidades = ["Alta", "Media", "Baja"]
    disciplinas_posibles = ["MEC", "ELE", "INS", "CIV", "MEC | ELE"]

    ots = []

    for i in range(1, n+1):
        tipo = random.choice(tipos)
        criticidad = random.choice(criticidades)
        disciplina = random.choice(disciplinas_posibles)

        if "|" in disciplina:
            horas = "6 | 6"
            tecnicos = "1 | 1"
        else:
            horas = str(random.choice([4,6,8]))
            tecnicos = str(random.randint(1,2))

        fecha_inicial = FECHA_INICIO + timedelta(days=random.randint(0,20))
        fecha_limite = fecha_inicial + timedelta(days=random.randint(5,15))

        ots.append({
            "id": f"OT{i:03}",
            "Tipo": tipo,
            "Criticidad": criticidad,
            "Fecha_Inicial": fecha_inicial,
            "Fecha_Limite": fecha_limite,
            "Ubicacion": random.choice(["Planta","Remota"]),
            "Disciplinas": disciplina,
            "Horas": horas,
            "Tecnicos": tecnicos
        })

    return ots

raw_ots = generar_ots(num_ots)
df_ots = pd.DataFrame(raw_ots)
st.subheader("📋 OTs Generadas")
st.dataframe(df_ots, use_container_width=True)

# ============================================================
# MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
intervalos_camionetas = []
start_vars = {}
end_vars = {}
todos_intervalos = []

for ot in raw_ots:

    disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
    horas = [int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

    bloques = []

    inicio_min = (ot["Fecha_Inicial"] - FECHA_INICIO).days * HORAS_POR_DIA
    inicio_min = max(0, inicio_min)

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

        bloques.append((start,end))

    # precedencia en serie si hay múltiples disciplinas
    for i in range(len(bloques)-1):
        model.Add(bloques[i+1][0] >= bloques[i][1])

# ============================================================
# RESTRICCIONES
# ============================================================

for disc, intervalos in intervals_por_disciplina.items():
    if intervalos:
        model.AddCumulative(
            [i[0] for i in intervalos],
            [i[1] for i in intervalos],
            capacidad_disciplina[disc]
        )

if intervalos_camionetas:
    model.AddCumulative(
        intervalos_camionetas,
        [1]*len(intervalos_camionetas),
        camionetas
    )

# ============================================================
# FUNCIÓN OBJETIVO CORREGIDA
# ============================================================

atrasos = []
pesos_criticidad = {"Alta":10,"Media":5,"Baja":1}

for nombre, start in start_vars.items():

    ot_id = nombre.split("_")[0]
    ot = next(o for o in raw_ots if o["id"] == ot_id)

    fin = end_vars[nombre]
    limite = (ot["Fecha_Limite"] - FECHA_INICIO).days * HORAS_POR_DIA

    atraso = model.NewIntVar(0,HORIZONTE_HORAS,f"atraso_{nombre}")
    model.Add(atraso >= fin - limite)
    model.Add(atraso >= 0)

    atrasos.append(pesos_criticidad[ot["Criticidad"]] * atraso)

# Balance mensual real
carga_diaria = []

for dia in range(DIAS_MES):

    inicio_dia = dia * HORAS_POR_DIA
    fin_dia = (dia+1) * HORAS_POR_DIA

    contribuciones = []

    for intervalo, dur in todos_intervalos:

        nombre_int = intervalo.Name().replace("interval_","")
        start = start_vars[nombre_int]
        end = end_vars[nombre_int]

        activo = model.NewBoolVar(f"activo_{dia}_{nombre_int}")

        model.Add(start < fin_dia).OnlyEnforceIf(activo)
        model.Add(end > inicio_dia).OnlyEnforceIf(activo)
        model.Add(start >= fin_dia).OnlyEnforceIf(activo.Not())
        model.Add(end <= inicio_dia).OnlyEnforceIf(activo.Not())

        contrib = model.NewIntVar(0,dur,f"contrib_{dia}_{nombre_int}")
        model.Add(contrib == dur).OnlyEnforceIf(activo)
        model.Add(contrib == 0).OnlyEnforceIf(activo.Not())

        contribuciones.append(contrib)

    carga = model.NewIntVar(0,1000,f"carga_{dia}")
    model.Add(carga == sum(contribuciones))
    carga_diaria.append(carga)

total_horas = model.NewIntVar(0,10000,"total_horas")
model.Add(total_horas == sum(carga_diaria))

promedio = model.NewIntVar(0,1000,"promedio")
model.AddDivisionEquality(promedio,total_horas,DIAS_MES)

desviaciones = []

for i,carga in enumerate(carga_diaria):
    diff = model.NewIntVar(-1000,1000,f"diff_{i}")
    model.Add(diff == carga - promedio)

    abs_diff = model.NewIntVar(0,1000,f"abs_{i}")
    model.AddAbsEquality(abs_diff,diff)

    desviaciones.append(abs_diff)

makespan = model.NewIntVar(0,HORIZONTE_HORAS,"makespan")
model.AddMaxEquality(makespan,list(end_vars.values()))

model.Minimize(
    peso_atrasos*sum(atrasos) +
    peso_balance*sum(desviaciones) +
    2*makespan
)

# ============================================================
# RESOLUCIÓN
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
status = solver.Solve(model)

if status in [cp_model.OPTIMAL,cp_model.FEASIBLE]:

    st.success("Solución encontrada ✔")

    resultados = []

    for nombre,start in start_vars.items():

        inicio = solver.Value(start)
        fin = solver.Value(end_vars[nombre])
        ot_id = nombre.split("_")[0]

        resultados.append({
            "OT":ot_id,
            "Inicio":FECHA_INICIO+timedelta(hours=inicio),
            "Fin":FECHA_INICIO+timedelta(hours=fin)
        })

    df = pd.DataFrame(resultados)

    fig = px.timeline(
        df,
        x_start="Inicio",
        x_end="Fin",
        y="OT",
        title="📅 Gantt – Marzo Completo"
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=900)

    st.plotly_chart(fig,use_container_width=True)

else:
    st.error("No se encontró solución factible")
