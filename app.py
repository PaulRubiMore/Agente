# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# STREAMLIT + CP-SAT
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Sistema Multi-Agente de Programación Óptima")

# ============================================================
# FASE 0 – GENERACIÓN ALEATORIA DE OTs
# ============================================================

with st.expander("FASE 0 – Carga de Datos", expanded=True):

    HORIZONTE_DIAS = 14
    HORAS_POR_DIA = 8
    HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

    capacidad_disciplina = {
        "MEC": 6,
        "ELE": 4,
        "INS": 3,
        "CIV": 3
    }

    def generar_ots_aleatorias(n, horizonte_dias):

        disciplinas_disponibles = ["MEC", "ELE", "INS", "CIV"]
        tipos = ["PREV", "PRED", "CORR"]
        criticidades = ["Alta", "Media", "Baja"]
        ubicaciones = ["Planta", "Remota"]

        ots = []

        for i in range(1, n + 1):

            tipo = random.choices(tipos, weights=[0.4, 0.3, 0.3])[0]
            criticidad = random.choices(criticidades, weights=[0.3, 0.4, 0.3])[0]
            ubicacion = random.choice(ubicaciones)

            dia_tentativo = random.randint(1, horizonte_dias - 2)
            dia_limite = random.randint(dia_tentativo + 1, horizonte_dias)

            num_disciplinas = random.choices([1, 2], weights=[0.7, 0.3])[0]
            disciplinas = random.sample(disciplinas_disponibles, num_disciplinas)

            horas_list = []
            tecnicos_list = []

            for d in disciplinas:
                horas_list.append(str(random.choice([4, 6, 8, 10, 12])))
                tecnicos_list.append(str(random.choice([1, 2])))

            ot = {
                "id": f"OT{i:03}",
                "Tipo": tipo,
                "Criticidad": criticidad,
                "Dia_Tentativo": dia_tentativo,
                "Dia_Limite": dia_limite,
                "Ubicacion": ubicacion,
                "Camioneta": 1 if ubicacion == "Remota" else 0,
                "Disciplinas": " | ".join(disciplinas),
                "Horas": " | ".join(horas_list),
                "Tecnicos": " | ".join(tecnicos_list)
            }

            ots.append(ot)

        return ots

    cantidad_ots = st.slider("Cantidad de OTs", 10, 150, 50)
    raw_ots = generar_ots_aleatorias(cantidad_ots, HORIZONTE_DIAS)

# ============================================================
# FASE 1 – ANALISTA DE CONDICIÓN
# ============================================================

for ot in raw_ots:
    if ot["Tipo"] == "CORR":
        ot["Indice_Degradacion"] = 0.9
    elif ot["Tipo"] == "PRED":
        ot["Indice_Degradacion"] = 0.6
    else:
        ot["Indice_Degradacion"] = 0.3

# ============================================================
# FASE 2 – PRIORIZACIÓN
# ============================================================

def criticidad_score(c):
    return {"Alta": 3, "Media": 2, "Baja": 1}[c]

def tipo_score(t):
    return {"CORR": 100, "PRED": 60, "PREV": 40}[t]

for ot in raw_ots:
    score = (
        tipo_score(ot["Tipo"])
        + criticidad_score(ot["Criticidad"]) * 10
        + ot["Indice_Degradacion"] * 20
    )
    ot["Score"] = int(score)

# ============================================================
# FASE 3 – MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
start_vars = {}
end_vars = {}

for ot in raw_ots:

    inicio_min = (ot["Dia_Tentativo"] - 1) * HORAS_POR_DIA
    fin_max = ot["Dia_Limite"] * HORAS_POR_DIA

    disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
    horas = [int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos_req = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):

        disc = disciplinas[i]
        dur = horas[i]
        demanda = tecnicos_req[i]

        nombre = f"{ot['id']}_{disc}"

        start = model.NewIntVar(inicio_min, fin_max - dur, f"start_{nombre}")
        end = model.NewIntVar(inicio_min + dur, fin_max, f"end_{nombre}")
        interval = model.NewIntervalVar(start, dur, end, f"interval_{nombre}")

        intervals_por_disciplina[disc].append((interval, demanda))
        start_vars[nombre] = start
        end_vars[nombre] = end

for disc, intervalos in intervals_por_disciplina.items():
    if intervalos:
        model.AddCumulative(
            [i[0] for i in intervalos],
            [i[1] for i in intervalos],
            capacidad_disciplina[disc]
        )

makespan = model.NewIntVar(0, HORIZONTE_HORAS, "makespan")
model.AddMaxEquality(makespan, list(end_vars.values()))
model.Minimize(makespan)

# ============================================================
# RESOLVER
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 20
status = solver.Solve(model)

if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:

    resultados = []

    for nombre, start in start_vars.items():

        inicio = solver.Value(start)
        fin = solver.Value(end_vars[nombre])
        ot_id = nombre.split("_")[0]

        dia_limite = next(
            ot["Dia_Limite"] for ot in raw_ots if ot["id"] == ot_id
        )

        limite_horas = dia_limite * HORAS_POR_DIA
        atraso = max(0, fin - limite_horas)

        resultados.append({
            "Bloque": nombre,
            "Inicio": inicio,
            "Fin": fin,
            "Backlog": "SI" if atraso > 0 else "NO"
        })

    df = pd.DataFrame(resultados)
    st.dataframe(df)

    df["Inicio_dt"] = pd.to_datetime(df["Inicio"], unit="h")
    df["Fin_dt"] = pd.to_datetime(df["Fin"], unit="h")

    fig = px.timeline(
        df,
        x_start="Inicio_dt",
        x_end="Fin_dt",
        y="Bloque",
        color="Backlog"
    )

    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

    st.metric("Duración total (horas)", solver.Value(makespan))