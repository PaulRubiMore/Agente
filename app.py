# ============================================================
# AGENTE 6 – PLANIFICADOR SEMANAL INTELIGENTE
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Planificación Semanal")

# ============================================================
# PARÁMETROS
# ============================================================

HORAS_POR_DIA = 8
DIAS_SEMANA = 5
HORAS_SEMANA = HORAS_POR_DIA * DIAS_SEMANA

capacidad_disciplina = {
    "MEC": 6,
    "ELE": 4,
    "INS": 3,
    "CIV": 3
}

# ============================================================
# GENERAR OTs
# ============================================================

def generar_ots(n):

    disciplinas = ["MEC","ELE","INS","CIV"]
    tipos = ["PREV","PRED","CORR"]
    criticidades = ["Alta","Media","Baja"]

    ots=[]

    for i in range(1,n+1):

        disc=random.sample(disciplinas,
                           random.choice([1,2]))

        horas=[]
        tecnicos=[]

        for d in disc:
            horas.append(str(random.choice([4,6,8])))
            tecnicos.append(str(random.choice([1,2])))

        tipo=random.choice(tipos)

        deg = 0.9 if tipo=="CORR" else 0.6 if tipo=="PRED" else 0.3

        score = (
            {"CORR":100,"PRED":60,"PREV":40}[tipo]
            + random.randint(1,3)*10
            + deg*20
        )

        ots.append({
            "id":f"OT{i:03}",
            "Tipo":tipo,
            "Score":int(score),
            "Disciplinas":" | ".join(disc),
            "Horas":" | ".join(horas),
            "Tecnicos":" | ".join(tecnicos)
        })

    return ots


cantidad = st.slider("Cantidad OTs Backlog",10,150,50)

raw_ots = generar_ots(cantidad)

st.subheader("📋 Backlog Total")
st.dataframe(
    pd.DataFrame(raw_ots)
    .sort_values("Score",ascending=False)
)

# ============================================================
# MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()

intervals_por_disciplina = {d:[] for d in capacidad_disciplina}

start_vars={}
end_vars={}
ejecucion={}
pesos={}

for ot in raw_ots:

    disciplinas=[d.strip() for d in ot["Disciplinas"].split("|")]
    horas=[int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos=[int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):

        disc=disciplinas[i]
        dur=horas[i]
        demanda=tecnicos[i]

        nombre=f"{ot['id']}_{disc}"

        ejecutar=model.NewBoolVar(f"exec_{nombre}")

        start=model.NewIntVar(0,HORAS_SEMANA-dur,
                              f"start_{nombre}")

        end=model.NewIntVar(dur,HORAS_SEMANA,
                            f"end_{nombre}")

        interval=model.NewOptionalIntervalVar(
            start,
            dur,
            end,
            ejecutar,
            f"int_{nombre}"
        )

        # SOLO SI SE EJECUTA
        model.Add(end<=HORAS_SEMANA).OnlyEnforceIf(ejecutar)

        intervals_por_disciplina[disc].append(
            (interval,demanda)
        )

        start_vars[nombre]=start
        end_vars[nombre]=end
        ejecucion[nombre]=ejecutar
        pesos[nombre]=ot["Score"]

# ============================================================
# CAPACIDAD SEMANAL
# ============================================================

for disc,intervalos in intervals_por_disciplina.items():

    if intervalos:

        model.AddCumulative(
            [i[0] for i in intervalos],
            [i[1] for i in intervalos],
            capacidad_disciplina[disc]
        )

# ============================================================
# OBJETIVO
# MAXIMIZAR IMPORTANCIA EJECUTADA
# ============================================================

beneficio=model.NewIntVar(0,10**9,"beneficio")

model.Add(
    beneficio==
    sum(pesos[n]*ejecucion[n]
        for n in ejecucion)
)

model.Maximize(beneficio)

# ============================================================
# SOLVER
# ============================================================

solver=cp_model.CpSolver()
solver.parameters.max_time_in_seconds=15

status=solver.Solve(model)

# ============================================================
# RESULTADOS
# ============================================================

if status in [cp_model.OPTIMAL,cp_model.FEASIBLE]:

    programadas=[]
    pendientes=[]

    for nombre in ejecucion:

        ot_id=nombre.split("_")[0]

        if solver.Value(ejecucion[nombre])==1:

            inicio=solver.Value(start_vars[nombre])

            programadas.append({
                "OT":ot_id,
                "Bloque":nombre,
                "Dia":inicio//HORAS_POR_DIA+1
            })

        else:
            pendientes.append({"OT":ot_id})

    df_prog=pd.DataFrame(programadas)
    df_backlog=pd.DataFrame(pendientes)

    st.subheader("✅ PLAN SEMANAL")
    st.dataframe(df_prog)

    st.subheader("📦 OTs REPROGRAMADAS")
    st.dataframe(df_backlog)

# ============================================================
# GANTT
# ============================================================

    if not df_prog.empty:

        df_prog["Inicio"]=df_prog["Dia"]*8
        df_prog["Fin"]=df_prog["Inicio"]+8

        fig=px.timeline(
            df_prog,
            x_start="Inicio",
            x_end="Fin",
            y="Bloque",
            title="Plan Semanal"
        )

        fig.update_yaxes(autorange="reversed")

        st.plotly_chart(fig,use_container_width=True)
