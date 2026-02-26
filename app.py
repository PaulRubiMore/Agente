import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random

st.title("🧠 AGENTE 6 — Planificador Semanal Inteligente")

# =====================================================
# PARÁMETROS
# =====================================================

SEMANAS = 4
HORAS_SEMANA = 40

capacidad_disciplina = {
    "MEC":6,
    "ELE":4,
    "INS":3,
    "CIV":3
}

# =====================================================
# GENERAR OTs
# =====================================================

def generar_ots(n):

    tipos=["CORR","PRED","PREV"]
    criticidad=["Alta","Media","Baja"]
    disciplinas=["MEC","ELE","INS","CIV"]

    ots=[]

    for i in range(n):

        disc=random.choice(disciplinas)

        ots.append({
            "id":f"OT{i:03}",
            "Tipo":random.choice(tipos),
            "Criticidad":random.choice(criticidad),
            "Disciplina":disc,
            "Duracion":random.choice([8,16,24]),
        })

    return ots


raw_ots=generar_ots(50)

# =====================================================
# PRIORIDAD
# =====================================================

def score(ot):

    tipo={"CORR":100,"PRED":60,"PREV":40}[ot["Tipo"]]
    crit={"Alta":30,"Media":20,"Baja":10}[ot["Criticidad"]]

    return tipo+crit

for ot in raw_ots:
    ot["Score"]=score(ot)

df_prioridad=pd.DataFrame(raw_ots)\
    .sort_values("Score",ascending=False)

st.subheader("📊 Lista Prioridad")
st.dataframe(df_prioridad)

# =====================================================
# MODELO
# =====================================================

model=cp_model.CpModel()

asignacion={}
programada={}

for ot in raw_ots:

    asignacion[ot["id"]] = model.NewIntVar(
        0,SEMANAS,
        f"semana_{ot['id']}"
    )

    programada[ot["id"]] = model.NewBoolVar(
        f"prog_{ot['id']}"
    )

    model.Add(asignacion[ot["id"]] > 0)\
         .OnlyEnforceIf(programada[ot["id"]])

    model.Add(asignacion[ot["id"]] == 0)\
         .OnlyEnforceIf(programada[ot["id"]].Not())

# =====================================================
# CAPACIDAD SEMANAL
# =====================================================

for s in range(1,SEMANAS+1):

    for disc in capacidad_disciplina:

        tareas=[]
        duraciones=[]

        for ot in raw_ots:

            if ot["Disciplina"]==disc:

                b=model.NewBoolVar(
                    f"{ot['id']}_sem{s}"
                )

                model.Add(
                    asignacion[ot["id"]]==s
                ).OnlyEnforceIf(b)

                model.Add(
                    asignacion[ot["id"]]!=s
                ).OnlyEnforceIf(b.Not())

                tareas.append(b)
                duraciones.append(ot["Duracion"])

        model.Add(
            sum(
                tareas[i]*duraciones[i]
                for i in range(len(tareas))
            )
            <= capacidad_disciplina[disc]*HORAS_SEMANA
        )

# =====================================================
# OBJETIVO
# =====================================================

model.Maximize(
    sum(
        programada[ot["id"]]*ot["Score"]
        for ot in raw_ots
    )
)

# =====================================================
# SOLVER
# =====================================================

solver=cp_model.CpSolver()
solver.parameters.max_time_in_seconds=10

solver.Solve(model)

# =====================================================
# RESULTADOS
# =====================================================

resultado=[]

for ot in raw_ots:

    semana=solver.Value(asignacion[ot["id"]])

    resultado.append({
        "OT":ot["id"],
        "Tipo":ot["Tipo"],
        "Criticidad":ot["Criticidad"],
        "Score":ot["Score"],
        "Semana":
            "BACKLOG"
            if semana==0
            else f"Semana {semana}"
    })

df=pd.DataFrame(resultado)

st.subheader("📅 PLAN SEMANAL")

for s in range(1,SEMANAS+1):

    st.write(f"### ✅ Semana {s}")
    st.dataframe(
        df[df["Semana"]==f"Semana {s}"]
        .sort_values("Score",ascending=False)
    )

st.write("### ⚠️ Backlog / Mes siguiente")
st.dataframe(
    df[df["Semana"]=="BACKLOG"]
)
