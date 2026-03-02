# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# INTERFAZ EXPLICATIVA STREAMLIT
# SIMULACIÓN MENSUAL – MARZO 2026
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Simulación Multi-Agente – Planificación Óptima Marzo 2026")

# ============================================================
# FASE 0 – GENERADOR AUTOMÁTICO DE OTs
# ============================================================

with st.expander("FASE 0 – Generación Automática de Órdenes de Trabajo", expanded=True):

    HORIZONTE_DIAS = 31
    HORAS_POR_DIA = 8
    HORIZONTE_HORAS = HORIZONTE_DIAS * HORAS_POR_DIA

    FECHA_INICIO = datetime(2026, 3, 1)
    MES_ACTUAL = 3

    capacidad_disciplina = {
        "MEC": 6,
        "ELE": 4,
        "INS": 3,
        "CIV": 3
    }

    def generar_ots(n=50):

        tipos = ["PREV", "PRED", "CORR"]
        criticidades = ["Alta", "Media", "Baja"]
        disciplinas_posibles = [
            "MEC",
            "ELE",
            "INS",
            "CIV",
            "MEC | ELE",
            "MEC | INS"
        ]

        ots = []

        for i in range(1, n+1):

            tipo = random.choice(tipos)
            criticidad = random.choice(criticidades)

            dia_tentativo = random.randint(1, 25)
            dia_limite = min(dia_tentativo + random.randint(3, 8), 31)

            disciplina = random.choice(disciplinas_posibles)

            if "|" in disciplina:
                horas = " | ".join([str(random.choice([4,6,8])) for _ in disciplina.split("|")])
                tecnicos = " | ".join([str(random.randint(1,2)) for _ in disciplina.split("|")])
            else:
                horas = str(random.choice([4,6,8,10,12]))
                tecnicos = str(random.randint(1,2))

            ots.append({
                "id": f"OT{i:03}",
                "Tipo": tipo,
                "Criticidad": criticidad,
                "Fecha_Inicial": FECHA_INICIO + timedelta(days=dia_tentativo - 1),
                "Fecha_Limite": FECHA_INICIO + timedelta(days=dia_limite - 1),
                "Ubicacion": random.choice(["Planta", "Remota"]),
                "Camioneta": random.choice([0, 1]),
                "Disciplinas": disciplina,
                "Horas": horas,
                "Tecnicos": tecnicos,
                "Mes_Origen": random.choice([2,3])
            })

        return ots

    raw_ots = generar_ots(130)

    st.write(f"Total OTs generadas automáticamente: {len(raw_ots)}")

    # ==============================
    # TABLA VISUAL PROFESIONAL
    # ==============================

    df_ots = pd.DataFrame(raw_ots)

    st.subheader("📋 Órdenes de Trabajo Generadas")

    st.dataframe(
        df_ots,
        use_container_width=True,
        height=400
    )

    # ==============================
    # OPCIÓN VER FORMATO JSON
    # ==============================

    with st.expander("Ver formato tipo JSON"):

        for ot in raw_ots[:10]:  # mostramos solo 10 para no saturar
            st.json(ot)

    st.success("Simulación de carga mensual completada.")

# ============================================================
# FASE 1 – REPROGRAMACIÓN DE OTs ATRASADAS
# ============================================================

with st.expander("FASE 1 – Reprogramación Inteligente de OTs Vencidas", expanded=True):

    for ot in raw_ots:

        if ot["Mes_Origen"] < MES_ACTUAL:

            if ot["Tipo"] == "PREV" and ot["Criticidad"] == "Alta":
                # Preventiva Alta → se programa desde su fecha límite
                ot["Fecha_Inicial"] = ot["Fecha_Limite"]

            elif ot["Tipo"] == "PRED":
                # Se mueve dentro del mes actual
                nueva_fecha = FECHA_INICIO + timedelta(days=random.randint(0, 19))
                ot["Fecha_Inicial"] = nueva_fecha

            elif ot["Tipo"] == "CORR" and ot["Criticidad"] == "Alta":
                # Se prioriza al inicio del mes
                ot["Fecha_Inicial"] = FECHA_INICIO

            else:
                nueva_fecha = FECHA_INICIO + timedelta(days=random.randint(0, 24))
                ot["Fecha_Inicial"] = nueva_fecha

    st.success("Reprogramación aplicada según reglas estratégicas.")

# ============================================================
# FASE 2 – ANALISTA DE CONDICIÓN
# ============================================================

with st.expander("FASE 2 – Agente Analista de Condición", expanded=True):

    for ot in raw_ots:
        if ot["Tipo"] == "CORR":
            degradacion = 0.9
        elif ot["Tipo"] == "PRED":
            degradacion = 0.6
        else:
            degradacion = 0.3

        ot["Indice_Degradacion"] = degradacion

# ============================================================
# FASE 3 – PRIORIZACIÓN ESTRATÉGICA
# ============================================================

with st.expander("FASE 3 – Agente Priorización Estratégica", expanded=True):

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

    st.success("Priorización estratégica calculada.")

# ============================================================
# FASE 4 – CONSTRUCCIÓN MODELO CP-SAT
# ============================================================

with st.expander("FASE 4 – Construcción Modelo Matemático (CP-SAT)", expanded=True):

    model = cp_model.CpModel()

    intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
    start_vars = {}
    end_vars = {}

    intervalos_camionetas = []
    demandas_camionetas = []
    CAMIONETAS = 3

    for ot in raw_ots:

        inicio_min = int((ot["Fecha_Inicial"] - FECHA_INICIO).days) * HORAS_POR_DIA
        fin_max = (int((ot["Fecha_Limite"] - FECHA_INICIO).days) + 1) * HORAS_POR_DIA

        duracion_total_ot = max([int(h.strip()) for h in ot["Horas"].split("|")])

        if fin_max - inicio_min < duracion_total_ot:
            fin_max = inicio_min + duracion_total_ot

        disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
        horas = [int(h.strip()) for h in ot["Horas"].split("|")]
        tecnicos_req = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

        for i in range(len(disciplinas)):

            disc = disciplinas[i]
            dur = horas[i]
            demanda = tecnicos_req[i]

            nombre = f"{ot['id']}_{disc}"

            start = model.NewIntVar(inicio_min, HORIZONTE_HORAS - dur, f"start_{nombre}")
            end = model.NewIntVar(inicio_min + dur, HORIZONTE_HORAS, f"end_{nombre}")
            interval = model.NewIntervalVar(start, dur, end, f"interval_{nombre}")
            # Si la OT es remota, requiere camioneta
            if ot["Ubicacion"] == "Remota":
                intervalos_camionetas.append(interval)
                demandas_camionetas.append(1)

            intervals_por_disciplina[disc].append((interval, demanda))

            start_vars[nombre] = start
            end_vars[nombre] = end
        
        if len(disciplinas) > 1:
                starts_ot = [start_vars[f"{ot['id']}_{d.strip()}"] for d in disciplinas]
                for s in starts_ot[1:]:
                    model.Add(s == starts_ot[0])

    st.success("Modelo matemático construido correctamente.")

# ============================================================
# FASE 5 – RESTRICCIONES DE CAPACIDAD
# ============================================================

with st.expander("FASE 5 – Restricciones de Capacidad", expanded=True):

    for disc, intervalos in intervals_por_disciplina.items():
        if intervalos:
            model.AddCumulative(
                [i[0] for i in intervalos],
                [i[1] for i in intervalos],
                capacidad_disciplina[disc]
            )
        # Restricción de camionetas
        if intervalos_camionetas:
            model.AddCumulative(
                intervalos_camionetas,
                demandas_camionetas,
                CAMIONETAS
            )

    st.success("Restricciones aplicadas por disciplina.")
    st.success("Restricción de camionetas aplicada (3 disponibles).")


# ============================================================
# FASE 6 – FUNCIÓN OBJETIVO INDUSTRIAL
# ============================================================

with st.expander("FASE 6 – Función Objetivo Industrial", expanded=True):

    atrasos = []
    adelantos = []
    pesos_criticidad = {"Alta": 10, "Media": 5, "Baja": 1}

    for nombre, start in start_vars.items():

        ot_id = nombre.split("_")[0]
        ot = next(o for o in raw_ots if o["id"] == ot_id)

        fin = end_vars[nombre]

        limite_horas = (ot["Fecha_Limite"] - FECHA_INICIO).days * HORAS_POR_DIA
        inicio_min_horas = (ot["Fecha_Inicial"] - FECHA_INICIO).days * HORAS_POR_DIA

        atraso = model.NewIntVar(0, HORIZONTE_HORAS, f"atraso_{nombre}")
        model.Add(atraso >= fin - limite_horas)
        model.Add(atraso >= 0)

        peso = pesos_criticidad[ot["Criticidad"]]
        atrasos.append(peso * atraso)

        adelanto = model.NewIntVar(0, HORIZONTE_HORAS, f"adelanto_{nombre}")
        model.Add(adelanto >= inicio_min_horas - start)
        model.Add(adelanto >= 0)

        adelantos.append(adelanto)

    penalizacion_temprana = model.NewIntVar(0, 100000, "penalizacion_temprana")

    bloques_tempranos = []

    for nombre, start in start_vars.items():
        es_temprano = model.NewBoolVar(f"temprano_{nombre}")
        model.Add(start < 5 * HORAS_POR_DIA).OnlyEnforceIf(es_temprano)
        model.Add(start >= 5 * HORAS_POR_DIA).OnlyEnforceIf(es_temprano.Not())
        bloques_tempranos.append(es_temprano)

    model.Add(penalizacion_temprana == sum(bloques_tempranos))

    # KPI informativo
    makespan = model.NewIntVar(0, HORIZONTE_HORAS, "makespan")
    model.AddMaxEquality(makespan, list(end_vars.values()))

    model.Minimize(
        100 * sum(atrasos) +
        10 * makespan +
        2 *sum(adelantos)
    )

    st.write("Objetivo: Minimizar atrasos, evitar saturación temprana y distribuir carga.")

# ============================================================
# FASE 7 – RESOLUCIÓN Y RESULTADOS
# ============================================================

with st.expander("FASE 7 – Resolución del Modelo", expanded=True):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20

    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:

        st.success("Solución encontrada ✔")

        resultados = []

        for nombre, start in start_vars.items():

            inicio = solver.Value(start)
            fin = solver.Value(end_vars[nombre])

            ot_id = nombre.split("_")[0]

            fecha_entrada = next(
                ot["Fecha_Inicial"] for ot in raw_ots if ot["id"] == ot_id
            )

            fecha_limite = next(
                ot["Fecha_Limite"] for ot in raw_ots if ot["id"] == ot_id
            )

            fecha_programada = FECHA_INICIO + timedelta(hours=inicio)

            limite_horas = (fecha_limite - FECHA_INICIO).days * HORAS_POR_DIA
            atraso = max(0, fin - limite_horas)

            resultados.append({
                "Bloque": nombre,
                "OT": ot_id,
                "Fecha Entrada": fecha_entrada,
                "Fecha Programada": fecha_programada,
                "Fecha Límite": fecha_limite,
                "Inicio (h)": inicio,
                "Fin (h)": fin,
                "Horas Atraso": atraso,
                "Backlog": "SI" if atraso > 0 else "NO"
            })

        df = pd.DataFrame(resultados).sort_values("Inicio (h)")

        total_bloques = len(df)
        backlog_count = len(df[df["Backlog"] == "SI"])
        cumplimiento = 100 * (1 - backlog_count / total_bloques)

        st.subheader("📊 Indicadores de Cumplimiento")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Bloques", total_bloques)
        col2.metric("Bloques en Backlog", backlog_count)
        col3.metric("% Cumplimiento", f"{cumplimiento:.1f}%")

        st.dataframe(df)

        # ==========================
        # GANTT MEJORADO Y LEGIBLE
        # ==========================

        df["Inicio_dt"] = df["Inicio (h)"].apply(
            lambda h: FECHA_INICIO + timedelta(hours=h)
        )

        df["Fin_dt"] = df["Fin (h)"].apply(
            lambda h: FECHA_INICIO + timedelta(hours=h)
        )

        fig = px.timeline(
            df,
            x_start="Inicio_dt",
            x_end="Fin_dt",
            y="OT",
            color="Backlog",
            title="📅 Diagrama de Gantt – Simulación Marzo 2026"
        )

        fig.update_layout(
            height=1000
        )
        fig.update_xaxes(
            range=[
                FECHA_INICIO,
                FECHA_INICIO + timedelta(days=HORIZONTE_DIAS)
            ],
            dtick="D1",
            tickformat="%d %b"
        )

        fig.update_layout(
            xaxis_title="Calendario Marzo 2026",
            yaxis_title="Ordenes de Trabajo (OTs)",
            height=1000,
        )

        fig.update_yaxes(autorange="reversed")

        st.plotly_chart(fig, width="stretch")

        st.metric("Duración total del plan (horas)", solver.Value(makespan))

    else:
        st.error("No se encontró solución factible.")
