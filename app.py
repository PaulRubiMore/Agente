# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO – MODELO ESTRATÉGICO
# CON POLÍTICA OPERATIVA + PENALIZACIÓN POR RIESGO
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import datetime
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Programador Estratégico (CP-SAT)")
st.markdown("Optimización basada en política operativa real")

# ============================================================
# FASE 0 – CONFIGURACIÓN GENERAL
# ============================================================

HORIZONTE_DIAS = 30
HORAS_POR_DIA = 8
HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

fecha_inicio = datetime.date.today()

capacidad_disciplina = {
    "MEC": 6,
    "ELE": 4,
    "INS": 3,
    "CIV": 3
}

# ============================================================
# FUNCIÓN POLÍTICA OPERATIVA
# ============================================================

def politica_programacion(ot):

    tipo = ot["Tipo"]
    crit = ot["Criticidad"]

    # 🔴 FECHA FIJA
    if (tipo == "PREV" and crit == "Alta") or \
       (tipo == "CORR" and crit == "Alta"):
        return "FECHA_FIJA"

    # 🟡 DENTRO DEL MES
    if (tipo == "PREV" and crit == "Media") or \
       (tipo == "CORR" and crit == "Media"):
        return "MES_OBLIGATORIO"

    # 🟢 FLEXIBLE CON PENALIZACIÓN
    if (tipo == "PREV" and crit == "Baja") or \
       (tipo == "CORR" and crit == "Baja"):
        return "MES_FLEXIBLE"

    # 🔵 PREDICTIVO SEGÚN DEGRADACIÓN
    if tipo == "PRED":
        if ot["Indice_Degradacion"] >= 0.8:
            return "MES_OBLIGATORIO"
        elif ot["Indice_Degradacion"] >= 0.5:
            return "MES_FLEXIBLE"
        else:
            return "TOTAL_FLEXIBLE"

    return "MES_FLEXIBLE"

# ============================================================
# GENERADOR DE OTs
# ============================================================

def generar_ots_aleatorias(n):

    disciplinas_disponibles = ["MEC", "ELE", "INS", "CIV"]
    tipos = ["PREV", "PRED", "CORR"]
    criticidades = ["Alta", "Media", "Baja"]

    ots = []

    for i in range(1, n + 1):

        tipo = random.choice(tipos)
        criticidad = random.choice(criticidades)

        fecha_tentativa = fecha_inicio + datetime.timedelta(
            days=random.randint(0, 20)
        )

        fecha_limite = fecha_tentativa + datetime.timedelta(
            days=random.randint(1, 10)
        )

        if tipo == "CORR":
            degradacion = 0.9
        elif tipo == "PRED":
            degradacion = random.choice([0.3, 0.6, 0.9])
        else:
            degradacion = 0.3

        disciplinas = random.sample(disciplinas_disponibles, random.choice([1,2]))
        horas_list = []
        tecnicos_list = []

        for d in disciplinas:
            horas_list.append(str(random.choice([4,6,8,10])))
            tecnicos_list.append(str(random.choice([1,2])))

        ot = {
            "id": f"OT{i:03}",
            "Tipo": tipo,
            "Criticidad": criticidad,
            "Fecha_Tentativa": fecha_tentativa,
            "Fecha_Limite": fecha_limite,
            "Indice_Degradacion": degradacion,
            "Disciplinas": " | ".join(disciplinas),
            "Horas": " | ".join(horas_list),
            "Tecnicos": " | ".join(tecnicos_list)
        }

        # Score estratégico
        score = (
            {"CORR":100,"PRED":60,"PREV":40}[tipo]
            + {"Alta":30,"Media":20,"Baja":10}[criticidad]
            + degradacion*20
        )

        ot["Score"] = int(score)

        ots.append(ot)

    return ots

cantidad = st.slider("Cantidad OTs", 10, 100, 40)
raw_ots = generar_ots_aleatorias(cantidad)

df_ots = pd.DataFrame(raw_ots)
st.dataframe(df_ots, use_container_width=True)

# ============================================================
# MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
start_vars = {}
end_vars = {}
penalizaciones = []

for ot in raw_ots:

    politica = politica_programacion(ot)

    inicio_min = (ot["Fecha_Tentativa"] - fecha_inicio).days * HORAS_POR_DIA
    fin_max = (ot["Fecha_Limite"] - fecha_inicio).days * HORAS_POR_DIA

    disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
    horas = [int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):

        disc = disciplinas[i]
        dur = horas[i]
        demanda = tecnicos[i]

        nombre = f"{ot['id']}_{disc}"

        start = model.NewIntVar(0, HORIZONTE_HORAS, f"start_{nombre}")
        end = model.NewIntVar(0, HORIZONTE_HORAS, f"end_{nombre}")

        model.Add(end == start + dur)

        # 🔴 FECHA FIJA
        if politica == "FECHA_FIJA":
            model.Add(start == inicio_min)

        # 🟡 MES OBLIGATORIO
        elif politica == "MES_OBLIGATORIO":
            model.Add(start >= 0)
            model.Add(end <= HORIZONTE_HORAS)

        # resto flexible

        interval = model.NewIntervalVar(start, dur, end, f"interval_{nombre}")
        intervals_por_disciplina[disc].append((interval, demanda))

        # Penalización por atraso
        fecha_limite_horas = fin_max
        atraso = model.NewIntVar(0, HORIZONTE_HORAS, f"atraso_{nombre}")
        model.Add(atraso >= end - fecha_limite_horas)
        model.Add(atraso >= 0)

        penalizaciones.append(atraso * ot["Score"])

        start_vars[nombre] = start
        end_vars[nombre] = end

# Restricciones capacidad
for disc, lista in intervals_por_disciplina.items():
    if lista:
        model.AddCumulative(
            [i[0] for i in lista],
            [i[1] for i in lista],
            capacidad_disciplina[disc]
        )

# FUNCIÓN OBJETIVO ESTRATÉGICA
model.Minimize(sum(penalizaciones))

# ============================================================
# RESOLUCIÓN
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 20
status = solver.Solve(model)

if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:

    resultados = []

    for nombre, start in start_vars.items():

        inicio = solver.Value(start)
        fin = solver.Value(end_vars[nombre])

        resultados.append({
            "Bloque": nombre,
            "Inicio": inicio,
            "Fin": fin,
            "Inicio_dt": fecha_inicio + datetime.timedelta(hours=inicio),
            "Fin_dt": fecha_inicio + datetime.timedelta(hours=fin)
        })

    df = pd.DataFrame(resultados).sort_values("Inicio")

    st.subheader("📊 Programación Óptima")
    st.dataframe(df)

    fig = px.timeline(
        df,
        x_start="Inicio_dt",
        x_end="Fin_dt",
        y="Bloque",
        title="📅 Diagrama de Gantt Estratégico"
    )

    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

    st.success("Optimización estratégica completada ✔")

else:
    st.error("No se encontró solución.")
