# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# INTERFAZ EXPLICATIVA STREAMLIT
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
# FASE 0 – CARGA DE DATOS (Generación + Visualización)
# ============================================================

with st.expander("FASE 0 – Carga de Datos", expanded=True):

    HORIZONTE_DIAS = 14
    HORAS_POR_DIA = 8
    HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

    st.write(f"Horizonte total: {HORIZONTE_HORAS} horas")

    capacidad_disciplina = {
        "MEC": 6,
        "ELE": 4,
        "INS": 3,
        "CIV": 3
    }

    st.write("Capacidad técnica por disciplina:", capacidad_disciplina)

    # --------------------------------------------------------
    # FUNCIÓN GENERADORA
    # --------------------------------------------------------

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
                horas = random.choice([4, 6, 8, 10, 12])
                tecnicos = random.choice([1, 2])

                horas_list.append(str(horas))
                tecnicos_list.append(str(tecnicos))

            ot = {
                "OT": f"OT{i:03}",
                "Tipo": tipo,
                "Criticidad": criticidad,
                "Dia_Tentativo": dia_tentativo,
                "Dia_Limite": dia_limite,
                "Ubicacion": ubicacion,
                "Camioneta": "SI" if ubicacion == "Remota" else "NO",
                "Disciplinas": " | ".join(disciplinas),
                "Horas": " | ".join(horas_list),
                "Tecnicos": " | ".join(tecnicos_list)
            }

            ots.append(ot)

        return ots

    cantidad_ots = st.slider("Cantidad de OTs a generar", 10, 150, 50)

    raw_ots = generar_ots_aleatorias(cantidad_ots, HORIZONTE_DIAS)

    st.success(f"Se generaron {len(raw_ots)} OTs")

    # --------------------------------------------------------
    # VISUALIZACIÓN TABULAR
    # --------------------------------------------------------

    df_ots = pd.DataFrame(raw_ots)

    st.subheader("📋 Órdenes de Trabajo Generadas")

    st.dataframe(df_ots, use_container_width=True)

# ============================================================
# FASE 1 – ANALISTA DE CONDICIÓN
# ============================================================

with st.expander("FASE 1 – Agente Analista de Condición", expanded=True):

    for ot in raw_ots:
        if ot["Tipo"] == "CORR":
            degradacion = 0.9
        elif ot["Tipo"] == "PRED":
            degradacion = 0.6
        else:
            degradacion = 0.3

        ot["Indice_Degradacion"] = degradacion
        st.write(f"{ot['id']} → Índice degradación: {degradacion}")

# ============================================================
# FASE 2 – PRIORIZACIÓN ESTRATÉGICA
# ============================================================

with st.expander("FASE 2 – Agente Priorización", expanded=True):

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
        st.write(f"{ot['id']} → Score estratégico: {ot['Score']}")

# ============================================================
# FASE 3 – CONSTRUCCIÓN MODELO CP-SAT
# ============================================================

with st.expander("FASE 3 – Construcción Modelo Matemático (CP-SAT)", expanded=True):

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

    st.success("Modelo matemático construido correctamente.")

# ============================================================
# FASE 4 – RESTRICCIONES DE CAPACIDAD
# ============================================================

with st.expander("FASE 4 – Restricciones de Capacidad", expanded=True):

    for disc, intervalos in intervals_por_disciplina.items():

        if intervalos:
            model.AddCumulative(
                [i[0] for i in intervalos],
                [i[1] for i in intervalos],
                capacidad_disciplina[disc]
            )

            st.write(f"Restricción aplicada para disciplina {disc}")

# ============================================================
# FASE 5 – FUNCIÓN OBJETIVO
# ============================================================

with st.expander("FASE 5 – Función Objetivo", expanded=True):

    makespan = model.NewIntVar(0, HORIZONTE_HORAS, "makespan")
    model.AddMaxEquality(makespan, list(end_vars.values()))
    model.Minimize(makespan)

    st.write("Objetivo: Minimizar duración total del plan")

# ============================================================
# FASE 6 – RESOLUCIÓN
# ============================================================

with st.expander("FASE 6 – Resolución del Modelo", expanded=True):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:

        st.success("Solución encontrada ✔")

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
                "OT": ot_id,
                "Inicio": inicio,
                "Fin": fin,
                "Día Inicio": inicio // HORAS_POR_DIA + 1,
                "Horas Atraso": atraso,
                "Backlog": "SI" if atraso > 0 else "NO"
            })

        df = pd.DataFrame(resultados)
        df = df.sort_values("Inicio")

        total_bloques = len(df)
        backlog_count = len(df[df["Backlog"] == "SI"])
        cumplimiento = 100 * (1 - backlog_count / total_bloques)

        st.subheader("📊 Indicadores de Cumplimiento")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Bloques", total_bloques)
        col2.metric("Bloques en Backlog", backlog_count)
        col3.metric("% Cumplimiento", f"{cumplimiento:.1f}%")

        st.dataframe(df)

        # GANTT

        df["Inicio_dt"] = pd.to_datetime(df["Inicio"], unit="h")
        df["Fin_dt"] = pd.to_datetime(df["Fin"], unit="h")

        fig = px.timeline(
            df,
            x_start="Inicio_dt",
            x_end="Fin_dt",
            y="Bloque",
            color="Backlog",
            title="📅 Diagrama de Gantt – Programación Óptima"
        )

        fig.update_yaxes(autorange="reversed")

        st.plotly_chart(fig, use_container_width=True)

        st.metric("Duración total (horas)", solver.Value(makespan))

