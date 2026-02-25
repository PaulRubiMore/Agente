# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO – PROGRAMADOR INTELIGENTE
# CP-SAT con Prioridad Estratégica y Fechas Reales
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
import datetime
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Sistema Multi-Agente de Programación Óptima con fechas reales y priorización estratégica")

# ============================================================
# FASE 0 – CARGA DE DATOS
# ============================================================

HORIZONTE_DIAS = 14
HORAS_POR_DIA = 8
HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

capacidad_disciplina = {"MEC":10,"ELE":10,"INS":10,"CIV":10}
fecha_inicio = datetime.date.today()

st.write(f"Horizonte total: {HORIZONTE_HORAS} horas")
st.write("Capacidad técnica por disciplina:", capacidad_disciplina)

def generar_ots_aleatorias(n, horizonte_dias):
    disciplinas_disponibles = ["MEC","ELE","INS","CIV"]
    tipos = ["PREV","PRED","CORR"]
    criticidades = ["Alta","Media","Baja"]
    ubicaciones = ["Planta","Remota"]
    ots = []

    for i in range(1,n+1):
        tipo = random.choices(tipos, weights=[0.4,0.3,0.3])[0]
        criticidad = random.choices(criticidades, weights=[0.3,0.4,0.3])[0]
        ubicacion = random.choice(ubicaciones)

        # Fechas aleatorias
        fecha_tentativa = fecha_inicio + datetime.timedelta(days=random.randint(0,horizonte_dias-2))
        fecha_limite = fecha_tentativa + datetime.timedelta(days=random.randint(1,horizonte_dias-(fecha_tentativa-fecha_inicio).days))
        fecha_realizacion = fecha_tentativa + datetime.timedelta(days=random.randint(0,(fecha_limite-fecha_tentativa).days))

        num_disciplinas = random.choices([1,2], weights=[0.7,0.3])[0]
        disciplinas = random.sample(disciplinas_disponibles, num_disciplinas)
        horas_list, tecnicos_list = [], []

        for d in disciplinas:
            horas_list.append(str(random.choice([4,6,8,10,12])))
            tecnicos_list.append(str(random.choice([1,2])))

        ot = {
            "id": f"OT{i:03}",
            "Tipo": tipo,
            "Criticidad": criticidad,
            "Fecha_Tentativa": fecha_tentativa,
            "Fecha_Limite": fecha_limite,
            "Fecha_Realizacion": fecha_realizacion,
            "Ubicacion": ubicacion,
            "Camioneta": "SI" if ubicacion=="Remota" else "NO",
            "Disciplinas": " | ".join(disciplinas),
            "Horas": " | ".join(horas_list),
            "Tecnicos": " | ".join(tecnicos_list)
        }
        ots.append(ot)
    return ots

cantidad_ots = st.slider("Cantidad de OTs a generar", 10, 150, 50)
raw_ots = generar_ots_aleatorias(cantidad_ots, HORIZONTE_DIAS)
df_ots = pd.DataFrame(raw_ots)
st.subheader("📋 Órdenes de Trabajo Generadas")
st.dataframe(df_ots,use_container_width=True)

# ============================================================
# FASE 1 – ANALISTA DE CONDICIÓN
# ============================================================

for ot in raw_ots:
    if ot["Tipo"]=="CORR": degradacion=0.9
    elif ot["Tipo"]=="PRED": degradacion=0.6
    else: degradacion=0.3
    ot["Indice_Degradacion"]=degradacion

# ============================================================
# FASE 2 – PRIORIZACIÓN ESTRATÉGICA
# ============================================================

def criticidad_score(c): return {"Alta":3,"Media":2,"Baja":1}[c]
def tipo_score(t): return {"CORR":100,"PRED":60,"PREV":40}[t]

for ot in raw_ots:
    ot["Score"] = tipo_score(ot["Tipo"])+criticidad_score(ot["Criticidad"])*10+ot["Indice_Degradacion"]*20

# ============================================================
# FASE 3 – MODELO CP-SAT
# ============================================================

model = cp_model.CpModel()
intervals_por_disciplina = {d:[] for d in capacidad_disciplina}
start_vars, end_vars, atraso_vars, penalizaciones = {}, {}, {}, []

for ot in raw_ots:
    inicio_min = (ot["Fecha_Tentativa"]-fecha_inicio).days*HORAS_POR_DIA
    fin_max = (ot["Fecha_Limite"]-fecha_inicio).days*HORAS_POR_DIA
    disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
    horas = [int(h.strip()) for h in ot["Horas"].split("|")]
    tecnicos_req = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

    for i in range(len(disciplinas)):
        disc = disciplinas[i]
        dur = horas[i]
        demanda = tecnicos_req[i]
        nombre = f"{ot['id']}_{disc}"

        start = model.NewIntVar(inicio_min, fin_max-dur, f"start_{nombre}")
        end = model.NewIntVar(inicio_min+dur, fin_max, f"end_{nombre}")
        interval = model.NewIntervalVar(start,dur,end,f"interval_{nombre}")
        intervals_por_disciplina[disc].append((interval,demanda))
        start_vars[nombre] = start
        end_vars[nombre] = end

        # Variable de atraso ponderada por score
        atraso = model.NewIntVar(0,HORIZONTE_HORAS,f"atraso_{nombre}")
        model.Add(atraso >= end - fin_max)
        atraso_vars[nombre] = atraso
        penalizaciones.append(atraso*ot["Score"])

# ============================================================
# FASE 4 – RESTRICCIONES DE CAPACIDAD
# ============================================================

for disc, intervalos in intervals_por_disciplina.items():
    if intervalos:
        model.AddCumulative([i[0] for i in intervalos],[i[1] for i in intervalos],capacidad_disciplina[disc])

# ============================================================
# FASE 5 – FUNCIÓN OBJETIVO
# ============================================================

model.Minimize(sum(penalizaciones))

# ============================================================
# FASE 6 – RESOLUCIÓN
# ============================================================

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
status = solver.Solve(model)

if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:

    resultados = []

    for nombre, start_var in start_vars.items():

        inicio_horas = solver.Value(start_var)
        fin_horas = solver.Value(end_vars[nombre])

        ot_id = nombre.split("_")[0]
        ot_data = next(ot for ot in raw_ots if ot["id"] == ot_id)

        atraso = solver.Value(atraso_vars[nombre])

        # 🔥 IMPORTANTE: usar datetime real
        fecha_inicio_ot = fecha_inicio + datetime.timedelta(hours=inicio_horas)
        fecha_fin_ot = fecha_inicio + datetime.timedelta(hours=fin_horas)

        resultados.append({
            "Bloque": nombre,
            "OT": ot_id,
            "Fecha Inicio": fecha_inicio_ot,
            "Fecha Fin": fecha_fin_ot,
            "Horas Atraso": atraso,
            "Backlog": "SI" if atraso > 0 else "NO",
            "Score": ot_data["Score"]
        })

    df_res = pd.DataFrame(resultados).sort_values("Fecha Inicio")

    st.subheader("📊 Resultados")
    st.dataframe(df_res, use_container_width=True)

    # 🔥 GANTT CORRECTO
    fig = px.timeline(
        df_res,
        x_start="Fecha Inicio",
        x_end="Fecha Fin",
        y="Bloque",
        color="Score",  # mejor que backlog
        hover_data=["OT", "Horas Atraso", "Score"],
        title="📅 Diagrama de Gantt – Programación Óptima"
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="Tiempo", yaxis_title="Bloques")

    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("No se encontró solución factible.")




