# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO
# VERSIÓN CON AJUSTE AUTOMÁTICO DE FECHAS LÍMITE
# Y VISUALIZACIÓN DE CAMIONETAS + PERSONAL
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px
from collections import defaultdict

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown("Simulación Multi-Agente – Planificación Óptima Marzo 2026")

# ============================================================
# PANEL LATERAL DE CONTROL
# ============================================================
with st.sidebar:
    st.header("⚙️ Parámetros del Modelo")
    num_ots = st.slider("Número de OTs a generar", 50, 200, 60, step=10)
    
    st.subheader("Capacidad de técnicos por disciplina")
    cap_mec = st.number_input("MEC", min_value=1, max_value=20, value=6)
    cap_ele = st.number_input("ELE", min_value=1, max_value=20, value=4)
    cap_ins = st.number_input("INS", min_value=1, max_value=20, value=3)
    cap_civ = st.number_input("CIV", min_value=1, max_value=20, value=3)
    capacidad_disciplina = {"MEC": cap_mec, "ELE": cap_ele, "INS": cap_ins, "CIV": cap_civ}
    
    st.subheader("Camionetas")
    camionetas = st.number_input("Número de camionetas", min_value=1, max_value=20, value=3)
    
    st.subheader("Opciones de flexibilidad")
    ignorar_fechas_iniciales = st.checkbox("Ignorar fechas iniciales (todas pueden empezar el día 1)", value=False)
    desactivar_balance_carga = st.checkbox("Desactivar balance de carga (solo atrasos)", value=False)
    st.subheader("Horizonte de Planificación")

    dias_horizonte = st.slider(
    "Días a planificar",
    min_value=3,
    max_value=30,
    value=30,
    step=1
    )
    st.subheader("Pesos de la función objetivo")
    peso_atrasos = st.slider("Peso atrasos", 0, 100, 10)
    peso_carga = st.slider("Peso balance de carga", 0, 500, 100)
    peso_temprano = st.slider("Peso inicio temprano", 0, 50, 1)

# ============================================================
# FASE 0 – GENERADOR AUTOMÁTICO DE OTs
# ============================================================

with st.expander("FASE 0 – Generación Automática de Órdenes de Trabajo", expanded=True):

    HORAS_POR_DIA = 6
    FECHA_INICIO = datetime(2026, 3, 1)
    MES_ACTUAL = 3

    def generar_ots(n=num_ots):
        random.seed(42)
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
            disciplina = random.choice(disciplinas_posibles)

            if "|" in disciplina:
                num_disc = len(disciplina.split("|"))
                horas_list = [random.choice([4,6,8]) for _ in range(num_disc)]
                tecnicos_list = [random.randint(1,2) for _ in range(num_disc)]
                horas_str = " | ".join(map(str, horas_list))
                tecnicos_str = " | ".join(map(str, tecnicos_list))
                duracion_total = sum(horas_list)
            else:
                horas = random.choice([4,6,8,10,12])
                tecnicos = random.randint(1,2)
                horas_str = str(horas)
                tecnicos_str = str(tecnicos)
                duracion_total = horas

            dia_tentativo = random.randint(1, 28)
            dias_necesarios = (duracion_total + HORAS_POR_DIA - 1) // HORAS_POR_DIA
            dia_limite_min = dia_tentativo + dias_necesarios
            dia_limite = random.randint(dia_limite_min, 31)

            ots.append({
                "id": f"OT{i:03}",
                "Tipo": tipo,
                "Criticidad": criticidad,
                "Fecha_Inicial": FECHA_INICIO + timedelta(days=dia_tentativo - 1),
                "Fecha_Limite": FECHA_INICIO + timedelta(days=dia_limite - 1),
                "Ubicacion": random.choice(["Planta", "Remota"]),
                "Camioneta": random.choice([0, 1]),
                "Disciplinas": disciplina,
                "Horas": horas_str,
                "Tecnicos": tecnicos_str,
                "Mes_Origen": random.choice([2,3])
            })
        return ots

    raw_ots = generar_ots()
    st.write(f"Total OTs generadas automáticamente: {len(raw_ots)}")
    df_ots = pd.DataFrame(raw_ots)
    st.subheader("📋 Órdenes de Trabajo Generadas")
    st.dataframe(df_ots, width='stretch', height=400)

    with st.expander("Ver formato tipo JSON"):
        for ot in raw_ots[:10]:
            st.json(ot)
    st.success("Simulación de carga mensual completada.")

# ============================================================
# FASE 1 – REPROGRAMACIÓN DE OTs ATRASADAS + AJUSTE DE VENTANAS
# ============================================================

with st.expander("FASE 1 – Reprogramación Inteligente de OTs Vencidas", expanded=True):
    for ot in raw_ots:
        if ot["Mes_Origen"] < MES_ACTUAL:
            if ot["Tipo"] == "PREV" and ot["Criticidad"] == "Alta":
                pass
            elif ot["Tipo"] == "PRED":
                nueva_fecha = FECHA_INICIO + timedelta(days=random.randint(0, 30))
                ot["Fecha_Inicial"] = nueva_fecha
            elif ot["Tipo"] == "CORR" and ot["Criticidad"] == "Alta":
                if random.random() < 0.3:
                    ot["Fecha_Inicial"] = FECHA_INICIO
                else:
                    nueva_fecha = FECHA_INICIO + timedelta(days=random.randint(1, 15))
                    ot["Fecha_Inicial"] = nueva_fecha
            else:
                nueva_fecha = FECHA_INICIO + timedelta(days=random.randint(0, 30))
                ot["Fecha_Inicial"] = nueva_fecha

    # Ajustar fechas límite para garantizar ventana suficiente
    for ot in raw_ots:
        horas_totales = sum([int(h.strip()) for h in ot["Horas"].split("|")])
        dias_necesarios = (horas_totales + HORAS_POR_DIA - 1) // HORAS_POR_DIA
        fecha_limite_min = ot["Fecha_Inicial"] + timedelta(days=dias_necesarios - 1)
        if ot["Fecha_Limite"] < fecha_limite_min:
            ot["Fecha_Limite"] = fecha_limite_min
            st.write(f"OT {ot['id']}: fecha límite ajustada a {fecha_limite_min.strftime('%d/%m')} para garantizar factibilidad.")

    st.success("Reprogramación aplicada y ventanas de tiempo ajustadas.")

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

fecha_fin_horizonte = FECHA_INICIO + timedelta(days=dias_horizonte)

ots_filtradas = [
    ot for ot in raw_ots
    if ot["Fecha_Inicial"] < fecha_fin_horizonte
]

# ============================================================
# FASE 4 – CONSTRUCCIÓN MODELO CP-SAT (HORIZONTE FIJO)
# ============================================================

with st.expander("FASE 4 – Construcción Modelo Matemático (CP-SAT)", expanded=True):

    HORIZONTE_HORAS = dias_horizonte * HORAS_POR_DIA
    st.write(f"Horizonte fijo: {HORIZONTE_HORAS} horas")

    model = cp_model.CpModel()
    intervals_por_disciplina = {d: [] for d in capacidad_disciplina}
    start_vars = {}
    end_vars = {}
    intervalos_camionetas = []
    demandas_camionetas = []
    todos_intervalos = []
    nombres_remotos = []  # Para guardar los nombres de bloques que usan camioneta
    info_bloques = []     # Para guardar (nombre, disc, duracion, tecnicos_req) para post-procesamiento

    for ot in ots_filtradas:
        inicio_min = (ot["Fecha_Inicial"] - FECHA_INICIO).days * HORAS_POR_DIA
        if ignorar_fechas_iniciales:
            inicio_min = 0
        else:
            inicio_min = max(0, inicio_min)

        disciplinas = [d.strip() for d in ot["Disciplinas"].split("|")]
        horas = [int(h.strip()) for h in ot["Horas"].split("|")]
        tecnicos_req = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

        bloques = []
        for i in range(len(disciplinas)):
            disc = disciplinas[i]
            dur = horas[i]
            demanda = tecnicos_req[i]
            nombre = f"{ot['id']}_{disc}"
            interval_nombre = f"interval_{nombre}"

            start = model.NewIntVar(inicio_min, HORIZONTE_HORAS - dur, f"start_{nombre}")
            end = model.NewIntVar(inicio_min + dur, HORIZONTE_HORAS, f"end_{nombre}")
            interval = model.NewIntervalVar(start, dur, end, interval_nombre)

            start_vars[nombre] = start
            end_vars[nombre] = end
            bloques.append((nombre, disc, demanda, interval, dur))

            if ot["Ubicacion"] == "Remota":
                intervalos_camionetas.append(interval)
                demandas_camionetas.append(1)
                nombres_remotos.append(nombre)

            todos_intervalos.append((interval, dur))
            info_bloques.append((nombre, disc, dur, demanda))  # Guardamos info para asignación de técnicos

        # Precedencia en serie
        for i in range(len(bloques) - 1):
            model.Add(start_vars[bloques[i+1][0]] >= end_vars[bloques[i][0]])

        for (nombre, disc, demanda, interval, dur) in bloques:
            intervals_por_disciplina[disc].append((interval, demanda))

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
    if intervalos_camionetas:
        model.AddCumulative(
            intervalos_camionetas,
            demandas_camionetas,
            camionetas
        )
    st.success("Restricciones aplicadas correctamente.")

# ============================================================
# FASE 6 – FUNCIÓN OBJETIVO ESTRATÉGICA (USO COMPLETO DEL HORIZONTE)
# ============================================================

with st.expander("FASE 6 – Función Objetivo Estratégica", expanded=True):

    atrasos = []
    pesos_criticidad = {"Alta": 10, "Media": 5, "Baja": 1}

    # -------------------------------------------------
    # 1️⃣ CÁLCULO DE ATRASOS SEGÚN FECHA LÍMITE
    # -------------------------------------------------
    for nombre, start in start_vars.items():

        ot_id = nombre.split("_")[0]
        ot = next(o for o in raw_ots if o["id"] == ot_id)
        fin = end_vars[nombre]

        limite_horas = (ot["Fecha_Limite"] - FECHA_INICIO).days * HORAS_POR_DIA

        atraso = model.NewIntVar(0, HORIZONTE_HORAS, f"atraso_{nombre}")
        model.Add(atraso >= fin - limite_horas)
        model.Add(atraso >= 0)

        peso = pesos_criticidad[ot["Criticidad"]]
        atrasos.append(peso * atraso)

    # -------------------------------------------------
    # 2️⃣ BALANCE DE CARGA DIARIA (CLAVE PARA DISTRIBUIR)
    # -------------------------------------------------
    carga_diaria_horas = []

    for dia in range(dias_horizonte):

        inicio_dia = dia * HORAS_POR_DIA
        fin_dia = (dia + 1) * HORAS_POR_DIA
        contribuciones = []

        for intervalo, duracion in todos_intervalos:

            nombre_intervalo = intervalo.Name()
            base_name = nombre_intervalo.replace("interval_", "", 1)
            start = start_vars[base_name]
            end = end_vars[base_name]

            activo = model.NewBoolVar(f"activo_{dia}_{nombre_intervalo}")

            model.Add(start < fin_dia).OnlyEnforceIf(activo)
            model.Add(end > inicio_dia).OnlyEnforceIf(activo)
            model.Add(start >= fin_dia).OnlyEnforceIf(activo.Not())
            model.Add(end <= inicio_dia).OnlyEnforceIf(activo.Not())

            contrib = model.NewIntVar(0, duracion, f"contrib_{dia}_{nombre_intervalo}")
            model.Add(contrib == duracion).OnlyEnforceIf(activo)
            model.Add(contrib == 0).OnlyEnforceIf(activo.Not())

            contribuciones.append(contrib)

        carga_dia = model.NewIntVar(0, 1000, f"carga_dia_{dia}")
        model.Add(carga_dia == sum(contribuciones))
        carga_diaria_horas.append(carga_dia)

    max_carga_diaria = model.NewIntVar(0, 1000, "max_carga_diaria")
    model.AddMaxEquality(max_carga_diaria, carga_diaria_horas)

    min_carga_diaria = model.NewIntVar(0, 1000, "min_carga_diaria")
    model.AddMinEquality(min_carga_diaria, carga_diaria_horas)

    # Diferencia entre día más cargado y menos cargado
    dispersion_carga = model.NewIntVar(0, 1000, "dispersion_carga")
    model.Add(dispersion_carga == max_carga_diaria - min_carga_diaria)

    # -------------------------------------------------
    # 3️⃣ FUNCIÓN OBJETIVO FINAL
    # -------------------------------------------------

    model.Minimize(
        peso_atrasos * sum(atrasos)
        + peso_carga * dispersion_carga
    )
    
    st.write("Objetivo: Minimizar atrasos + balancear carga en todo el horizonte")}
# ============================================================
# FASE 7 – RESOLVER MODELO Y MOSTRAR RESULTADOS
# ============================================================

with st.expander("FASE 7 – Resolución del Modelo", expanded=True):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):

        st.success("Modelo resuelto correctamente")

        resultados = []

        for nombre, start in start_vars.items():

            inicio = solver.Value(start)
            fin = solver.Value(end_vars[nombre])

            ot_id = nombre.split("_")[0]
            ot = next(o for o in raw_ots if o["id"] == ot_id)

            fecha_inicio = FECHA_INICIO + timedelta(hours=inicio)
            fecha_fin = FECHA_INICIO + timedelta(hours=fin)

            resultados.append({
                "OT": ot_id,
                "Activo": ot["Activo"],
                "Tipo": ot["Tipo"],
                "Criticidad": ot["Criticidad"],
                "Inicio": fecha_inicio,
                "Fin": fecha_fin,
                "Duracion (h)": ot["Duracion"]
            })

        df_resultados = pd.DataFrame(resultados)

        # ======================================================
        # MÉTRICAS CLAVE (IMPORTANTE CON TU NUEVA LÓGICA)
        # ======================================================

        col1, col2, col3 = st.columns(3)

        total_ot = len(df_resultados)

        ultimo_fin = df_resultados["Fin"].max()
        dias_usados = (ultimo_fin - FECHA_INICIO).days + 1

        horizonte_dias = dias_horizonte

        porcentaje_uso = round((dias_usados / horizonte_dias) * 100, 1)

        col1.metric("OTs Planificadas", total_ot)
        col2.metric("Días Usados del Horizonte", dias_usados)
        col3.metric("Uso del Horizonte (%)", f"{porcentaje_uso}%")

        # ======================================================
        # TABLA RESULTADOS
        # ======================================================

        st.subheader("Cronograma generado")
        st.dataframe(df_resultados, use_container_width=True)

    else:
        st.error("No se encontró solución factible")

