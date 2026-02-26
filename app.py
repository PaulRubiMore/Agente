# ============================================================
# AGENTE 6 – PROGRAMADOR INTELIGENTE
# PLANIFICACIÓN HASTA AGOTAR CAPACIDAD
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Planificador con Backlog Inteligente")

# ============================================================
# PARÁMETROS
# ============================================================

HORIZONTE_DIAS = 7        # Semana
HORAS_POR_DIA = 8
HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

capacidad_disciplina = {
    "MEC":6,
    "ELE":4,
    "INS":3,
    "CIV":3
}

# ============================================================
# GENERADOR OTs
# ============================================================

def generar_ots(n):

    disciplinas=["MEC","ELE","INS","CIV"]
    tipos=["PREV","PRED","CORR"]
    criticidades=["Alta","Media","Baja"]

    ots=[]

    for i in range(n):

        disc=random.sample(disciplinas,
                           random.choice([1,2]))

        horas=[]
        tecnicos=[]

        for d in disc:
            horas.append(str(random.choice([4,6,8])))
            tecnicos.append(str(random.choice([1,2])))

        ots.append({
            "id":f"OT{i+1:03}",
            "Tipo":random.choice(tipos),
            "Criticidad":random.choice(criticidades),
            "Dia_Tentativo":1,
            "Dia_Limite":HORIZONTE_DIAS,
            "Disciplinas":" | ".join(disc),
            "Horas":" | ".join(horas),
            "Tecnicos":" | ".join(tecnicos)
        })

    return ots


cantidad=st.slider("Cantidad OTs",10,120,50)
raw_ots=generar_ots(cantidad)

# ============================================================
# PRIORIZACIÓN
# ============================================================

def criticidad_score(c):
    return {"Alta":3,"Media":2,"Baja":1}[c]

def tipo_score(t):
    return {"CORR":100,"PRED":60,"PREV":40}[t]

for ot in raw_ots:

    degradacion={"CORR":0.9,"PRED":0.6,"PREV":0.3}[ot["Tipo"]]

    score=(
        tipo_score(ot["Tipo"])
        +criticidad_score(ot["Criticidad"])*10
        +degradacion*20
    )

    ot["Score"]=int(score)

df_prioridad=pd.DataFrame(raw_ots)\
.sort_values("Score",ascending=False)

st.subheader("📊 Lista Prioridad")
st.dataframe(df_prioridad,use_container_width=True)

# ============================================================
# MODELO CP-SAT
# ============================================================

model=cp_model.CpModel()

intervals={d:[] for d in capacidad_disciplina}

start_vars={}
end_vars={}
exec_vars={}
pesos={}

for ot in raw_ots:

    inicio_min=0
    fin_max=HORIZONTE_HORAS

    disciplinas=[d.strip() for d in ot["Disciplinas"].split("|")]
    horas=[int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos=[int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):

        disc=disciplinas[i]
        dur=horas[i]
        demanda=tecnicos[i]

        nombre=f"{ot['id']}_{disc}"

        start=model.NewIntVar(0,fin_max-dur,
                              f"start_{nombre}")

        end=model.NewIntVar(dur,fin_max,
                            f"end_{nombre}")

        ejecutada=model.NewBoolVar(
            f"exec_{nombre}"
        )

        interval=model.NewOptionalIntervalVar(
            start,
            dur,
            end,
            ejecutada,
            f"int_{nombre}"
        )

        intervals[disc].append(
            (interval,demanda)
        )

        start_vars[nombre]=start
        end_vars[nombre]=end
        exec_vars[nombre]=ejecutada
        pesos[nombre]=ot["Score"]

# ============================================================
# CAPACIDAD
# ============================================================

for disc,vals in intervals.items():

    if vals:

        model.AddCumulative(
            [v[0] for v in vals],
            [v[1] for v in vals],
            capacidad_disciplina[disc]
        )

# ============================================================
# OBJETIVO
# Ejecutar máximas OTs críticas
# ============================================================

costo=model.NewIntVar(0,10**9,"costo")

model.Add(
    costo==
    sum(
        pesos[n]*(1-exec_vars[n])
        for n in exec_vars
    )
)

model.Minimize(costo)

# ============================================================
# SOLVER
# ============================================================

solver=cp_model.CpSolver()
solver.parameters.max_time_in_seconds=20

status=solver.Solve(model)

# ============================================================
# RESULTADOS
# ============================================================

if status in [cp_model.OPTIMAL,cp_model.FEASIBLE]:

    resultados=[]

    for nombre in start_vars:

        ejec=solver.Value(exec_vars[nombre])

        if ejec==1:
            inicio=solver.Value(start_vars[nombre])
            dia=inicio//HORAS_POR_DIA+1
        else:
            dia=None

        resultados.append({
            "Bloque":nombre,
            "OT":nombre.split("_")[0],
            "Día Programado":dia,
            "Estado":
            "PROGRAMADA" if ejec==1 else "PENDIENTE"
        })

    df=pd.DataFrame(resultados)

    programadas=df[df["Estado"]=="PROGRAMADA"]
    pendientes=df[df["Estado"]=="PENDIENTE"]

    st.subheader("✅ PROGRAMADAS")
    st.dataframe(programadas)

    st.subheader("⏳ BACKLOG")
    st.dataframe(pendientes)

# ============================================================
# REPROGRAMACIÓN AUTOMÁTICA
# ============================================================

    if len(pendientes)>0:

        st.subheader("🔁 Reprogramación Semana Siguiente")

        backlog_ids=pendientes["OT"].unique()

        nuevas_ots=[]

        for ot in raw_ots:

            if ot["id"] in backlog_ids:

                nuevo=ot.copy()
                nuevo["Dia_Tentativo"]+=7
                nuevo["Dia_Limite"]+=7
                nuevas_ots.append(nuevo)

        st.write(
            f"{len(nuevas_ots)} OTs pasan a la siguiente semana"
        )

        st.dataframe(pd.DataFrame(nuevas_ots))

# ============================================================
# GANTT
# ============================================================

    if len(programadas)>0:

        programadas["Inicio"]=(
            programadas["Día Programado"]-1
        )*HORAS_POR_DIA

        programadas["Fin"]=programadas["Inicio"]+8

        programadas["Inicio_dt"]=pd.to_datetime(
            programadas["Inicio"],unit="h")

        programadas["Fin_dt"]=pd.to_datetime(
            programadas["Fin"],unit="h")

        fig=px.timeline(
            programadas,
            x_start="Inicio_dt",
            x_end="Fin_dt",
            y="Bloque",
            title="📅 Plan Semanal"
        )

        fig.update_yaxes(autorange="reversed")

        st.plotly_chart(fig,use_container_width=True)
