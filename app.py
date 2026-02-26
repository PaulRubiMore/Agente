# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# AGENTE 6 – PROGRAMADOR INTELIGENTE CP-SAT
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Programador Inteligente")
st.markdown("Programación Óptima basada en Prioridad")

# ============================================================
# FASE 0 — GENERACIÓN DE OTs
# ============================================================

HORIZONTE_DIAS = 14
HORAS_POR_DIA = 8
HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

capacidad_disciplina = {
    "MEC": 6,
    "ELE": 4,
    "INS": 3,
    "CIV": 3
}

def generar_ots(n):

    disciplinas = ["MEC","ELE","INS","CIV"]
    tipos = ["PREV","PRED","CORR"]
    criticidades = ["Alta","Media","Baja"]
    ubicaciones = ["Planta","Remota"]

    ots=[]

    for i in range(1,n+1):

        tipo=random.choices(tipos,[0.4,0.3,0.3])[0]
        criticidad=random.choice(criticidades)
        ubicacion=random.choice(ubicaciones)

        dia_ini=random.randint(1,HORIZONTE_DIAS-2)
        dia_fin=random.randint(dia_ini+1,HORIZONTE_DIAS)

        disc=random.sample(disciplinas,
                           random.choice([1,2]))

        horas=[]
        tecnicos=[]

        for d in disc:
            horas.append(str(random.choice([4,6,8,10])))
            tecnicos.append(str(random.choice([1,2])))

        ots.append({
            "id":f"OT{i:03}",
            "Tipo":tipo,
            "Criticidad":criticidad,
            "Dia_Tentativo":dia_ini,
            "Dia_Limite":dia_fin,
            "Disciplinas":" | ".join(disc),
            "Horas":" | ".join(horas),
            "Tecnicos":" | ".join(tecnicos),
            "Ubicacion":ubicacion
        })

    return ots


cantidad = st.slider("Cantidad OTs",10,150,50)
raw_ots = generar_ots(cantidad)

df_ots=pd.DataFrame(raw_ots)
st.dataframe(df_ots,use_container_width=True)

# ============================================================
# FASE 1 — ANALISTA CONDICIÓN
# ============================================================

for ot in raw_ots:

    if ot["Tipo"]=="CORR":
        deg=0.9
    elif ot["Tipo"]=="PRED":
        deg=0.6
    else:
        deg=0.3

    ot["Indice_Degradacion"]=deg

# ============================================================
# FASE 2 — PRIORIZACIÓN
# ============================================================

def criticidad_score(c):
    return {"Alta":3,"Media":2,"Baja":1}[c]

def tipo_score(t):
    return {"CORR":100,"PRED":60,"PREV":40}[t]

for ot in raw_ots:

    score=(
        tipo_score(ot["Tipo"])
        +criticidad_score(ot["Criticidad"])*10
        +ot["Indice_Degradacion"]*20
    )

    ot["Score"]=int(score)

st.subheader("📊 Lista Prioridad")
st.dataframe(
    pd.DataFrame(raw_ots)
    .sort_values("Score",ascending=False)
)

# ============================================================
# FASE 3 — MODELO CP-SAT
# ============================================================

model=cp_model.CpModel()

intervals_por_disciplina={d:[] for d in capacidad_disciplina}

start_vars={}
end_vars={}
atrasos={}
pesos={}

for ot in raw_ots:

    inicio_min=(ot["Dia_Tentativo"]-1)*HORAS_POR_DIA
    fin_max=ot["Dia_Limite"]*HORAS_POR_DIA

    disciplinas=[d.strip() for d in ot["Disciplinas"].split("|")]
    horas=[int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos=[int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):

        disc=disciplinas[i]
        dur=horas[i]
        demanda=tecnicos[i]

        nombre=f"{ot['id']}_{disc}"

        start=model.NewIntVar(inicio_min,fin_max-dur,
                              f"start_{nombre}")

        end=model.NewIntVar(inicio_min+dur,fin_max,
                            f"end_{nombre}")

        interval=model.NewIntervalVar(start,dur,end,
                                      f"int_{nombre}")

        intervals_por_disciplina[disc].append(
            (interval,demanda)
        )

        atraso=model.NewIntVar(0,HORIZONTE_HORAS,
                               f"delay_{nombre}")

        model.Add(atraso>=end-fin_max)
        model.Add(atraso>=0)

        atrasos[nombre]=atraso
        pesos[nombre]=ot["Score"]

        start_vars[nombre]=start
        end_vars[nombre]=end

# ============================================================
# FASE 4 — CAPACIDAD
# ============================================================

for disc,intervalos in intervals_por_disciplina.items():

    if intervalos:

        model.AddCumulative(
            [i[0] for i in intervalos],
            [i[1] for i in intervalos],
            capacidad_disciplina[disc]
        )

# ============================================================
# FASE 5 — OBJETIVO (PRIORIDAD REAL)
# ============================================================

costo_total=model.NewIntVar(0,10**9,"costo")

model.Add(
    costo_total==
    sum(atrasos[n]*pesos[n] for n in atrasos)
)

model.Minimize(costo_total)

# ============================================================
# FASE 6 — SOLUCIÓN
# ============================================================

solver=cp_model.CpSolver()
solver.parameters.max_time_in_seconds=20

status=solver.Solve(model)

# ============================================================
# RESULTADOS
# ============================================================

if status in [cp_model.OPTIMAL,cp_model.FEASIBLE]:

    resultados=[]

    for nombre,start in start_vars.items():

        inicio=solver.Value(start)
        fin=solver.Value(end_vars[nombre])

        ot_id=nombre.split("_")[0]

        dia_limite=next(
            ot["Dia_Limite"]
            for ot in raw_ots
            if ot["id"]==ot_id
        )

        atraso=max(
            0,
            fin-dia_limite*HORAS_POR_DIA
        )

        resultados.append({
            "Bloque":nombre,
            "OT":ot_id,
            "Inicio":inicio,
            "Fin":fin,
            "Día Inicio":inicio//HORAS_POR_DIA+1,
            "Atraso":atraso,
            "Backlog":"SI" if atraso>0 else "NO"
        })

    df=pd.DataFrame(resultados)

    df_prog=df.sort_values(
        ["Backlog","Inicio"]
    )

    st.subheader("✅ PROGRAMACIÓN FINAL")
    st.dataframe(df_prog,use_container_width=True)

# ============================================================
# GANTT
# ============================================================

    df_prog["Inicio_dt"]=pd.to_datetime(
        df_prog["Inicio"],unit="h")

    df_prog["Fin_dt"]=pd.to_datetime(
        df_prog["Fin"],unit="h")

    fig=px.timeline(
        df_prog,
        x_start="Inicio_dt",
        x_end="Fin_dt",
        y="Bloque",
        color="Backlog",
        title="Programación Óptima"
    )

    fig.update_yaxes(autorange="reversed")

    st.plotly_chart(fig,use_container_width=True)
