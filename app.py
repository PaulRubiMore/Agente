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
# FASE 6 – FUNCIÓN OBJETIVO INDUSTRIAL CORREGIDA
# ============================================================

with st.expander("FASE 6 – Función Objetivo Industrial", expanded=True):

    atrasos = []
    pesos_criticidad = {"Alta": 10, "Media": 5, "Baja": 1}
    bloques_tempranos = []

    # -----------------------------
    # CÁLCULO DE ATRASOS
    # -----------------------------
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

        # Penalización si se ejecuta en la primera semana
        es_temprano = model.NewBoolVar(f"temprano_{nombre}")
        model.Add(start < 5 * HORAS_POR_DIA).OnlyEnforceIf(es_temprano)
        model.Add(start >= 5 * HORAS_POR_DIA).OnlyEnforceIf(es_temprano.Not())
        bloques_tempranos.append(es_temprano)

    penalizacion_temprana = model.NewIntVar(0, len(bloques_tempranos), "penalizacion_temprana")
    model.Add(penalizacion_temprana == sum(bloques_tempranos))

    # -----------------------------
    # BALANCE DE CARGA
    # -----------------------------
    if not desactivar_balance_carga:

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

    else:
        max_carga_diaria = 0

    # -----------------------------
    # MAKESPAN (Duración total del plan)
    # -----------------------------
    makespan = model.NewIntVar(0, HORIZONTE_HORAS, "makespan")
    model.AddMaxEquality(makespan, list(end_vars.values()))

    # -----------------------------
    # FUNCIÓN OBJETIVO CORREGIDA
    # -----------------------------

    # Peso dinámico para usar mejor el horizonte
    peso_makespan = 1

    if desactivar_balance_carga:
    model.Minimize(
        peso_atrasos * sum(atrasos)
        + peso_temprano * penalizacion_temprana
    )
    st.write("Objetivo: minimizar atrasos + penalización temprana")

else:
    model.Minimize(
        peso_atrasos * sum(atrasos)
        + peso_carga * max_carga_diaria
        + peso_temprano * penalizacion_temana
    )
    st.write("Objetivo: minimizar atrasos + balance de carga + penalización temprana")

# ============================================================
# FASE 7 – RESOLUCIÓN Y RESULTADOS
# ============================================================

with st.expander("FASE 7 – Resolución del Modelo", expanded=True):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("Solución encontrada ✔")
        resultados = []
        for nombre, start in start_vars.items():
            inicio = solver.Value(start)
            fin = solver.Value(end_vars[nombre])
            ot_id = nombre.split("_")[0]
            ot = next(o for o in raw_ots if o["id"] == ot_id)
            fecha_entrada = ot["Fecha_Inicial"]
            fecha_limite = ot["Fecha_Limite"]
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
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Bloques", total_bloques)
        col2.metric("Bloques en Backlog", backlog_count)
        col3.metric("% Cumplimiento", f"{cumplimiento:.1f}%")
        ots_fuera = len(raw_ots) - len(ots_filtradas)
        col4.metric("OTs fuera horizonte", ots_fuera)
        # 🔹 ESTA LÍNEA SE QUEDA
        st.dataframe(df, width='stretch')

        # Carga diaria (si se calculó)
        if not desactivar_balance_carga:
            st.subheader("📈 Carga Diaria de Trabajo (horas)")
            cargas_reales = []
            for dia in range(dias_horizonte):
                inicio_dia = dia * HORAS_POR_DIA
                fin_dia = (dia + 1) * HORAS_POR_DIA
                carga = 0
                for _, row in df.iterrows():
                    if row["Inicio (h)"] < fin_dia and row["Fin (h)"] > inicio_dia:
                        duracion = row["Fin (h)"] - row["Inicio (h)"]
                        carga += duracion
                cargas_reales.append(carga)
            df_carga = pd.DataFrame({"Día": range(1, 32), "Carga (horas)": cargas_reales})
            fig_carga = px.bar(df_carga, x="Día", y="Carga (horas)", title="Carga diaria de trabajo")
            st.plotly_chart(fig_carga, use_container_width=True)

        # Gantt principal
        df["Inicio_dt"] = df["Inicio (h)"].apply(lambda h: FECHA_INICIO + timedelta(hours=h))
        df["Fin_dt"] = df["Fin (h)"].apply(lambda h: FECHA_INICIO + timedelta(hours=h))
        fig = px.timeline(
            df,
            x_start="Inicio_dt",
            x_end="Fin_dt",
            y="OT",
            color="Backlog",
            title="📅 Diagrama de Gantt – Simulación Marzo 2026"
        )
        fig.update_layout(height=1000, xaxis_title="Calendario Marzo 2026", yaxis_title="Ordenes de Trabajo (OTs)")
        fig.update_xaxes(range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=dias_horizonte)], dtick="D1", tickformat="%d %b")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        # ===== Gantt de Camionetas =====
        if nombres_remotos:
            st.subheader("🚐 Programación de Camionetas")
            data_cam = []
            for nombre in nombres_remotos:
                if nombre in start_vars:
                    inicio = solver.Value(start_vars[nombre])
                    fin = solver.Value(end_vars[nombre])
                    ot_id = nombre.split("_")[0]
                    data_cam.append({
                        "Bloque": nombre,
                        "OT": ot_id,
                        "Inicio_dt": FECHA_INICIO + timedelta(hours=inicio),
                        "Fin_dt": FECHA_INICIO + timedelta(hours=fin)
                    })
            if data_cam:
                df_cam = pd.DataFrame(data_cam)
                fig_cam = px.timeline(
                    df_cam,
                    x_start="Inicio_dt",
                    x_end="Fin_dt",
                    y="OT",
                    color="OT",
                    title="Uso de camionetas por OT"
                )
                fig_cam.update_layout(height=500, xaxis_title="Calendario Marzo 2026", yaxis_title="OT")
                fig_cam.update_xaxes(range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=dias_horizonte)], dtick="D1", tickformat="%d %b")
                fig_cam.update_yaxes(autorange="reversed")
                st.plotly_chart(fig_cam, use_container_width=True)
            else:
                st.info("No hay bloques remotos en la solución.")
        else:
            st.info("No hay OTs remotas en esta simulación.")

        # ===== NUEVO: Gantt de Personal (Asignación de técnicos) =====
        st.subheader("👥 Asignación de Técnicos (Gantt Personal)")

        # Crear lista de técnicos por disciplina
        tecnicos_por_disciplina = {}
        for disc, num in capacidad_disciplina.items():
            tecnicos_por_disciplina[disc] = [f"{disc}_{j+1}" for j in range(num)]

        # Obtener los valores de inicio y fin de cada bloque
        bloques_con_tiempo = []
        for nombre, start in start_vars.items():
            inicio = solver.Value(start)
            fin = solver.Value(end_vars[nombre])
            # Buscar la disciplina y demanda de este bloque en info_bloques
            for (nom, disc, dur, demanda) in info_bloques:
                if nom == nombre:
                    bloques_con_tiempo.append((nombre, disc, demanda, inicio, fin))
                    break

        # Ordenar bloques por inicio
        bloques_con_tiempo.sort(key=lambda x: x[3])

        # Asignación voraz: por disciplina, mantener agenda de técnicos
        asignaciones = []  # (tecnico, bloque, inicio_dt, fin_dt)
        agenda_tecnicos = {disc: {tec: [] for tec in tecnicos_por_disciplina[disc]} for disc in capacidad_disciplina}

        for (nombre, disc, demanda, inicio, fin) in bloques_con_tiempo:
            # Buscar técnicos de esta disciplina que estén libres en [inicio, fin)
            tecnicos_asignados = []
            for tec in tecnicos_por_disciplina[disc]:
                # Verificar si el técnico tiene algún intervalo que se solape
                ocupado = False
                for (i, f) in agenda_tecnicos[disc][tec]:
                    if not (fin <= i or f <= inicio):  # se solapa
                        ocupado = True
                        break
                if not ocupado:
                    tecnicos_asignados.append(tec)
                    if len(tecnicos_asignados) == demanda:
                        break
            if len(tecnicos_asignados) < demanda:
                st.warning(f"No se pudo asignar suficientes técnicos para {nombre} (disc {disc}, demanda {demanda}). Se asignarán los disponibles.")
                # Completar con los primeros disponibles (puede haber conflicto)
                for tec in tecnicos_por_disciplina[disc]:
                    if tec not in tecnicos_asignados:
                        tecnicos_asignados.append(tec)
                        if len(tecnicos_asignados) == demanda:
                            break

            # Registrar la asignación y actualizar agenda
            for tec in tecnicos_asignados[:demanda]:
                agenda_tecnicos[disc][tec].append((inicio, fin))
                asignaciones.append({
                    "Técnico": tec,
                    "Bloque": nombre,
                    "OT": nombre.split("_")[0],
                    "Inicio_dt": FECHA_INICIO + timedelta(hours=inicio),
                    "Fin_dt": FECHA_INICIO + timedelta(hours=fin)
                })

        if asignaciones:
            df_personal = pd.DataFrame(asignaciones)
            fig_personal = px.timeline(
                df_personal,
                x_start="Inicio_dt",
                x_end="Fin_dt",
                y="Técnico",
                color="OT",
                title="Asignación de Técnicos a lo largo del mes"
            )
            fig_personal.update_layout(height=600, xaxis_title="Calendario Marzo 2026", yaxis_title="Técnico")
            fig_personal.update_xaxes(range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=dias_horizonte)], dtick="D1", tickformat="%d %b")
            fig_personal.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_personal, use_container_width=True)
        else:
            st.info("No hay asignaciones para mostrar.")

        
    # ===== VISTA CONSOLIDADA TABLA EJECUTIVA =====
        st.subheader("📋 Tabla Ejecutiva de Operaciones")
        
        # Usar bloques_con_tiempo que ya tenemos (con disc, demanda, inicio, fin)
        # Crear DataFrame para análisis diario
        dias = list(range(31))
        data_diario = []
        for dia in dias:
            inicio_dia = dia * HORAS_POR_DIA
            fin_dia = (dia + 1) * HORAS_POR_DIA
            # Filtrar bloques que se ejecutan este día
            bloques_dia = [b for b in bloques_con_tiempo if b[3] < fin_dia and b[4] > inicio_dia]
            # Horas hombre por disciplina
            hh_mec = sum(b[2] * (min(b[4], fin_dia) - max(b[3], inicio_dia)) for b in bloques_dia if b[1] == "MEC")
            hh_ele = sum(b[2] * (min(b[4], fin_dia) - max(b[3], inicio_dia)) for b in bloques_dia if b[1] == "ELE")
            hh_ins = sum(b[2] * (min(b[4], fin_dia) - max(b[3], inicio_dia)) for b in bloques_dia if b[1] == "INS")
            hh_civ = sum(b[2] * (min(b[4], fin_dia) - max(b[3], inicio_dia)) for b in bloques_dia if b[1] == "CIV")
            # Uso de camionetas: bloques remotos (necesitamos saber cuáles son remotos)
            # Podemos obtener de nombres_remotos
            uso_camionetas = sum(1 for b in bloques_dia if b[0] in nombres_remotos)
            # Backlog: bloques con atraso (según df)
            # Necesitamos saber qué bloques tienen atraso. En df tenemos columna Backlog.
            # Construir un diccionario backlog por bloque
            backlog_dict = dict(zip(df["Bloque"], df["Backlog"] == "SI"))
            horas_atraso_dict = dict(zip(df["Bloque"], df["Horas Atraso"]))
            bloques_backlog_dia = [b for b in bloques_dia if backlog_dict.get(b[0], False)]
            cantidad_backlog = len(bloques_backlog_dia)
            horas_backlog = sum(horas_atraso_dict.get(b[0], 0) for b in bloques_dia)
            
            data_diario.append({
                "Día": dia + 1,
                "HH MEC": round(hh_mec, 1),
                "HH ELE": round(hh_ele, 1),
                "HH INS": round(hh_ins, 1),
                "HH CIV": round(hh_civ, 1),
                "Uso Camionetas": uso_camionetas,
                "Bloques Backlog": cantidad_backlog,
                "Horas Backlog": round(horas_backlog, 1)
            })
        
        df_ejecutivo = pd.DataFrame(data_diario)
        st.dataframe(df_ejecutivo.style.format({
            "HH MEC": "{:.1f}",
            "HH ELE": "{:.1f}",
            "HH INS": "{:.1f}",
            "HH CIV": "{:.1f}",
            "Uso Camionetas": "{:.0f}",
            "Bloques Backlog": "{:.0f}",
            "Horas Backlog": "{:.1f}"
        }), use_container_width=True)
        
        # Resumen global
        st.markdown("**Resumen Global**")
        total_hh = df_ejecutivo[["HH MEC","HH ELE","HH INS","HH CIV"]].sum().sum()
        total_camionetas = df_ejecutivo["Uso Camionetas"].sum()
        total_bloques_backlog = df_ejecutivo["Bloques Backlog"].sum()
        total_horas_backlog = df_ejecutivo["Horas Backlog"].sum()
        cumplimiento_global = 100 * (1 - total_bloques_backlog / total_bloques) if total_bloques > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total HH", f"{total_hh:.0f}")
        col2.metric("Uso Camionetas", f"{total_camionetas:.0f}")
        col3.metric("Bloques Backlog", f"{total_bloques_backlog:.0f}")
        col4.metric("% Cumplimiento", f"{cumplimiento_global:.1f}%")

        st.metric("Duración total del plan (horas)", solver.Value(makespan))
    else:
        st.error("No se encontró solución factible. Revise las restricciones o aumente el horizonte.")
        st.write("**Posibles causas:**")
        st.write("- Capacidad insuficiente de técnicos o camionetas.")
        st.write("- Fechas iniciales demasiado tardías combinadas con fechas límite tempranas.")
        st.write("- Restricciones de precedencia demasiado estrictas.")
        st.write("- Balance de carga muy exigente (si está activado).")
        st.write("**Diagnóstico adicional:**")
        st.write(f"Número de OTs: {len(raw_ots)}")
        total_bloques = len(start_vars)
        st.write(f"Número total de bloques: {total_bloques}")
        
        # Demanda por disciplina
        demanda_disc = {d: 0 for d in capacidad_disciplina}
        for ot in raw_ots:
            discs = [d.strip() for d in ot["Disciplinas"].split("|")]
            horas = [int(h.strip()) for h in ot["Horas"].split("|")]
            for d, h in zip(discs, horas):
                demanda_disc[d] += h
        st.write("Demanda total por disciplina (horas):")
        st.json(demanda_disc)
        
        # Capacidad mensual
        st.write("Capacidad mensual por disciplina (horas):")
        capacidad_mensual = {d: cap * HORAS_POR_DIA * dias_horizonte for d, cap in capacidad_disciplina.items()}
        st.json(capacidad_mensual)
        
        # OTs con ventana insuficiente (después del ajuste)
        ventanas_ajustadas = 0
        for ot in raw_ots:
            dur_total = sum([int(h.strip()) for h in ot["Horas"].split("|")])
            dias_ventana = (ot["Fecha_Limite"] - ot["Fecha_Inicial"]).days + 1
            horas_disponibles = dias_ventana * HORAS_POR_DIA
            if dur_total > horas_disponibles:
                ventanas_ajustadas += 1
        st.write(f"OTs con ventana insuficiente (después de ajuste): {ventanas_ajustadas}")
        
        st.info("Prueba activando 'Ignorar fechas iniciales' y/o 'Desactivar balance de carga' en el panel lateral.")



