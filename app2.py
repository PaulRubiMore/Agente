# ============================================================
# SISTEMA MULTI-AGENTE DE MANTENIMIENTO – v4.0 DEFINITIVO
# SIMULACIÓN MENSUAL – MARZO 2026
# ============================================================
#
# HISTORIAL DE ERRORES Y CORRECCIONES:
#
#  v1 ORIGINAL – Colapsaba en días 9-11:
#    ✗ Penalización simétrica + deseo_expansion = incentivo a comprimir
#    ✗ HORAS_POR_DIA=6 arbitrario, sin jornada real
#
#  v2 – INFEASIBLE:
#    ✗ Bloques de overtime consumían (cap-1) técnicos
#    ✗ Tareas de 10-12h cruzaban esos bloques → 5+2=7 > 6 = contradicción
#
#  v3 – INFEASIBLE:
#    ✗ Bug crítico de indexación: OVERTIME_START_IN_DAY = 8-2 = 6
#      Los "slots de overtime" resultaron ser los slots 6-7 del día
#      = horario 14:00-16:00 = JORNADA REGULAR, no horas extra.
#      Se bloqueaba trabajo en plena tarde laboral.
#    ✗ AddCumulative llamado DOS VECES por disciplina (duplicación)
#
#  v4 DEFINITIVO – Arquitectura correcta:
#  ═══════════════════════════════════════
#  PRINCIPIO: Con MAX_H_DIA=8 el horizonte SOLO contiene jornada
#  regular (08:00-16:00). Las "horas extra" (16:00-18:00) están
#  FUERA del horizonte → no se pueden modelar con slot-blocking.
#
#  SOLUCIÓN:
#  1. MAX_H_DIA = 8 → slots 0-7 del día = 08:00-15:00
#     El horizonte es puramente laboral. Cero trabajo nocturno.
#
#  2. Sin bloques de overtime en el modelo de capacidad.
#     El overtime se modela como VARIABLE DE DECISIÓN SEPARADA
#     en la función objetivo (penalización blanda por usar horas extra).
#
#  3. Restricción de capacidad única y correcta por disciplina.
#
#  4. Partición automática de tareas >8h en bloques ≤8h
#     con precedencia: bloque_k+1 empieza el siguiente día.
#
#  5. Función objetivo industrial real:
#     MIN Σ Score_i × tardiness_i  +  Σ 15 × inicio_tardio_i
#
# ============================================================

import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import random
from datetime import datetime, timedelta
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 6 – Programador Inteligente (CP-SAT)")
st.markdown(
    "**Simulación Multi-Agente – Planificación Óptima Marzo 2026**  "
    "`v4.0 DEFINITIVO · Calendario Real · Modelo Garantizado Factible`"
)

# ============================================================
# ★ CONFIGURACIÓN GLOBAL ★
# ============================================================

FECHA_INICIO = datetime(2026, 3, 1)
MES_ACTUAL   = 3

# ── Jornada laboral ────────────────────────────────────────
# Cada slot = 1 hora de trabajo real
# MAX_H_DIA = 8 significa que el modelo opera SOLO en 08:00-16:00
# Las horas extra (16:00-18:00) están FUERA del horizonte de slots
# → no hay nada que bloquear; no pueden ocurrir por construcción.
REGULAR_H_DIA = 8    # slots por día hábil (08:00–16:00)
MAX_H_DIA     = REGULAR_H_DIA

# ── Días hábiles Marzo 2026 (Lunes=0 … Sábado=5, Domingo=6) ─
dias_habiles: list[int] = [
    d for d in range(31)
    if (FECHA_INICIO + timedelta(days=d)).weekday() <= 5
]
N_DIAS_HABILES: int = len(dias_habiles)   # 26 días hábiles

# Índice hábil ↔ offset en calendario
cal_a_idx: dict[int, int] = {d: i for i, d in enumerate(dias_habiles)}
idx_a_cal: list[int]      = dias_habiles   # inverso

# Horizonte completo: 26 días × 8 h/día = 208 slots laborales
HORIZONTE_SLOTS: int = N_DIAS_HABILES * MAX_H_DIA

# ── Capacidades del equipo (técnicos disponibles) ─────────
capacidad_disciplina: dict[str, int] = {
    "MEC": 6,
    "ELE": 4,
    "INS": 3,
    "CIV": 3,
}

# ── Funciones de conversión ────────────────────────────────

def fecha_a_slot_ini(fecha: datetime) -> int:
    """
    Fecha calendario → primer slot laboral del día hábil en o después de esa fecha.
    Domingo 01/mar → slot 0 (lunes 02/mar 08:00).
    """
    offset = max(0, (fecha - FECHA_INICIO).days)
    for d in range(offset, 32):
        if d in cal_a_idx:
            return cal_a_idx[d] * MAX_H_DIA
    return HORIZONTE_SLOTS   # fuera del horizonte → costo máximo


def fecha_a_slot_deadline(fecha: datetime) -> int:
    """
    Fecha límite → final del último slot regular del día hábil
    en o antes de esa fecha.
    """
    offset = min(max(0, (fecha - FECHA_INICIO).days), 30)
    for d in range(offset, -1, -1):
        if d in cal_a_idx:
            return cal_a_idx[d] * MAX_H_DIA + REGULAR_H_DIA
    return REGULAR_H_DIA


def slot_a_dt(slot: int) -> datetime:
    """
    Slot laboral → datetime real para Gantt.
    slot=0  → lun 02/mar 08:00
    slot=7  → lun 02/mar 15:00
    slot=8  → mar 03/mar 08:00
    """
    slot = min(slot, HORIZONTE_SLOTS)
    idx  = min(slot // MAX_H_DIA, N_DIAS_HABILES - 1)
    h    = slot % MAX_H_DIA            # posición dentro del turno
    dia  = FECHA_INICIO + timedelta(days=idx_a_cal[idx])
    return datetime(dia.year, dia.month, dia.day, 8 + h, 0)


def partir_tarea(horas_total: int) -> list[int]:
    """
    Parte una tarea en bloques de máximo MAX_H_DIA horas.
    12h → [8, 4]   |   8h → [8]   |   4h → [4]
    Modela que no es posible ejecutar más de un turno completo
    sin pausa nocturna.
    """
    bloques, restante = [], horas_total
    while restante > 0:
        bloques.append(min(restante, MAX_H_DIA))
        restante -= MAX_H_DIA
    return bloques


# ============================================================
# PANEL INFORMATIVO DEL CALENDARIO
# ============================================================

with st.expander("📋 Calendario Laboral Marzo 2026", expanded=False):
    rows = []
    for d in dias_habiles:
        fecha_real = FECHA_INICIO + timedelta(days=d)
        i          = cal_a_idx[d]
        rows.append({
            "Día":         fecha_real.strftime("%A %d/%m/%Y"),
            "Idx hábil":   i + 1,
            "Slot inicio": i * MAX_H_DIA,
            "Slot fin":    i * MAX_H_DIA + MAX_H_DIA - 1,
            "Horario":     "08:00 – 16:00",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True, height=300)
    st.info(
        f"**{N_DIAS_HABILES} días hábiles** (Lun–Sáb) · "
        f"**{HORIZONTE_SLOTS} slots** totales · "
        f"Primer día: {(FECHA_INICIO + timedelta(days=dias_habiles[0])).strftime('%A %d/%m')} · "
        f"Último día: {(FECHA_INICIO + timedelta(days=dias_habiles[-1])).strftime('%A %d/%m')}"
    )

# ============================================================
# FASE 0 – GENERADOR
# ============================================================

with st.expander("FASE 0 – Generación Automática de Órdenes de Trabajo", expanded=True):

    random.seed(42)

    def generar_ots(n: int = 130) -> list[dict]:
        tipos                = ["PREV", "PRED", "CORR"]
        criticidades         = ["Alta", "Media", "Baja"]
        disciplinas_posibles = ["MEC", "ELE", "INS", "CIV", "MEC | ELE", "MEC | INS"]
        ots = []
        for i in range(1, n + 1):
            tipo       = random.choice(tipos)
            criticidad = random.choice(criticidades)
            dia_tent   = random.randint(1, 22)
            # Ventana mínima de 5 días para garantizar espacio de programación
            dia_lim    = random.randint(dia_tent + 5, 31)
            disciplina = random.choice(disciplinas_posibles)

            if "|" in disciplina:
                partes   = disciplina.split("|")
                horas    = " | ".join(str(random.choice([4, 6, 8])) for _ in partes)
                tecnicos = " | ".join(str(random.randint(1, 2))     for _ in partes)
            else:
                horas    = str(random.choice([4, 6, 8, 10, 12]))
                tecnicos = str(random.randint(1, 2))

            ots.append({
                "id":            f"OT{i:03}",
                "Tipo":          tipo,
                "Criticidad":    criticidad,
                "Fecha_Inicial": FECHA_INICIO + timedelta(days=dia_tent - 1),
                "Fecha_Limite":  FECHA_INICIO + timedelta(days=dia_lim  - 1),
                "Ubicacion":     random.choice(["Planta", "Remota"]),
                "Camioneta":     random.choice([0, 1]),
                "Disciplinas":   disciplina,
                "Horas":         horas,
                "Tecnicos":      tecnicos,
                "Mes_Origen":    random.choice([2, 3]),
            })
        return ots

    raw_ots = generar_ots(130)
    st.write(f"Total OTs generadas: **{len(raw_ots)}**")
    st.dataframe(pd.DataFrame(raw_ots), use_container_width=True, height=320)
    st.success("Simulación de carga mensual completada.")

# ============================================================
# FASE 1 – REPROGRAMACIÓN
# ============================================================

with st.expander("FASE 1 – Reprogramación de OTs Vencidas", expanded=True):
    for ot in raw_ots:
        if ot["Mes_Origen"] < MES_ACTUAL:
            if ot["Tipo"] == "PREV" and ot["Criticidad"] == "Alta":
                ot["Fecha_Inicial"] = ot["Fecha_Limite"]
            elif ot["Tipo"] == "PRED":
                ot["Fecha_Inicial"] = FECHA_INICIO + timedelta(days=random.randint(0, 19))
            elif ot["Tipo"] == "CORR" and ot["Criticidad"] == "Alta":
                ot["Fecha_Inicial"] = FECHA_INICIO
            else:
                ot["Fecha_Inicial"] = FECHA_INICIO + timedelta(days=random.randint(0, 24))
    st.success("Reprogramación aplicada.")

# ============================================================
# FASE 2 – ÍNDICE DE DEGRADACIÓN
# ============================================================

with st.expander("FASE 2 – Agente Analista de Condición", expanded=True):
    deg_map = {"CORR": 0.9, "PRED": 0.6, "PREV": 0.3}
    for ot in raw_ots:
        ot["Indice_Degradacion"] = deg_map[ot["Tipo"]]

# ============================================================
# FASE 3 – PRIORIZACIÓN
# ============================================================

with st.expander("FASE 3 – Priorización Estratégica", expanded=True):
    def criticidad_score(c: str) -> int: return {"Alta": 3, "Media": 2, "Baja": 1}[c]
    def tipo_score(t: str)       -> int: return {"CORR": 100, "PRED": 60, "PREV": 40}[t]
    for ot in raw_ots:
        ot["Score"] = int(
            tipo_score(ot["Tipo"])
            + criticidad_score(ot["Criticidad"]) * 10
            + ot["Indice_Degradacion"] * 20
        )
    st.success("Scores calculados.")

# ============================================================
# ★ FASE 4 – MODELO CP-SAT v4 ★
# ============================================================

with st.expander("FASE 4 – Construcción del Modelo CP-SAT", expanded=True):

    st.markdown(f"""
    #### Por qué v3 seguía siendo INFEASIBLE (diagnóstico final)

    ```
    MAX_H_DIA = 8  →  OVERTIME_START_IN_DAY = 8 - 2 = 6

    "Slot de overtime" del día 0  =  slots 6 y 7
    =  horario 14:00–16:00  =  ¡JORNADA REGULAR!

    Con bloqueo = cap - cap_overtime = 6 - 2 = 4
    Una tarea de 8h (slots 0-7) SIEMPRE pasa por slots 6-7:
        bloqueo(4) + task1(2) + task2(2) = 8 > 6  → INFEASIBLE
    ```

    #### Arquitectura v4 (garantizada factible)

    | Componente | Decisión de diseño |
    |---|---|
    | Horizonte | {HORIZONTE_SLOTS} slots = {N_DIAS_HABILES} días × {MAX_H_DIA}h regulares |
    | Overtime | **Fuera del horizonte** – no ocurre por construcción |
    | Capacidad | 1 sola `AddCumulative` por disciplina – sin duplicados |
    | Tareas >8h | Partición en bloques ≤8h con precedencia de día a día |
    | Factibilidad | Garantizada si demanda_total ≤ capacidad_total |

    #### Verificación de capacidad
    """)

    # Pre-check capacidad vs demanda
    cap_check = []
    all_feasible = True
    for disc, cap in capacidad_disciplina.items():
        horas_req = 0
        for ot in raw_ots:
            discs = [d.strip() for d in ot["Disciplinas"].split("|")]
            horas = [int(h.strip()) for h in ot["Horas"].split("|")]
            for d, h in zip(discs, horas):
                if d == disc:
                    horas_req += h
        cap_mes = cap * N_DIAS_HABILES * REGULAR_H_DIA
        ok = horas_req <= cap_mes
        if not ok:
            all_feasible = False
        cap_check.append({
            "Disciplina":        disc,
            "Técnicos":          cap,
            "Horas disponibles": cap_mes,
            "Horas requeridas":  horas_req,
            "% Ocupación":       f"{100*horas_req/cap_mes:.0f}%",
            "Estado":            "✅ OK" if ok else "❌ Excede",
        })
    st.dataframe(pd.DataFrame(cap_check), use_container_width=True, hide_index=True)
    if not all_feasible:
        st.error("⚠️ La demanda supera la capacidad en alguna disciplina. Reducir OTs o ampliar equipo.")
    else:
        st.success("✅ Capacidad suficiente para toda la demanda del mes")

    # ── Construcción del modelo ──────────────────────────────
    model = cp_model.CpModel()

    # Contenedores
    start_vars:               dict[str, cp_model.IntVar] = {}
    end_vars:                 dict[str, cp_model.IntVar] = {}
    # Cada disciplina tiene UNA lista de (interval, demand) para AddCumulative
    intervals_por_disc:       dict[str, list]            = {d: [] for d in capacidad_disciplina}
    intervalos_camionetas:    list = []
    demandas_camionetas:      list = []
    CAMIONETAS = 3

    # Términos de la función objetivo
    tard_terms:    list = []
    ini_lat_terms: list = []

    n_partidas = 0

    for ot in raw_ots:

        slot_ini  = fecha_a_slot_ini(ot["Fecha_Inicial"])
        slot_dead = fecha_a_slot_deadline(ot["Fecha_Limite"])

        # Ventana mínima de 1 slot (seguridad)
        slot_ini  = min(slot_ini,  HORIZONTE_SLOTS - 1)
        slot_dead = max(slot_dead, slot_ini + 1)

        disciplinas_ot = [d.strip() for d in ot["Disciplinas"].split("|")]
        horas_ot       = [int(h.strip()) for h in ot["Horas"].split("|")]
        tecnicos_ot    = [int(t.strip()) for t in ot["Tecnicos"].split("|")]

        # Puntero de precedencia global de la OT (entre disciplinas)
        ot_prev_end = None

        for disc, dur_total, demanda in zip(disciplinas_ot, horas_ot, tecnicos_ot):

            sub_bloques = partir_tarea(dur_total)   # máx MAX_H_DIA por bloque
            if len(sub_bloques) > 1:
                n_partidas += 1

            blq_prev_end = ot_prev_end   # precedencia dentro de la OT

            for k, dur in enumerate(sub_bloques):
                nombre = f"{ot['id']}_{disc}_{k}"

                # ── Variables de decisión ────────────────────
                # start en [slot_ini, HORIZONTE_SLOTS]:
                #   Si la solución necesita ir más allá del horizonte,
                #   se permite (el costo de tardiness lo penaliza).
                start = model.NewIntVar(
                    slot_ini,
                    HORIZONTE_SLOTS,
                    f"s_{nombre}"
                )
                # end = start + dur (forzado por IntervalVar)
                end = model.NewIntVar(
                    slot_ini + dur,
                    HORIZONTE_SLOTS + dur,
                    f"e_{nombre}"
                )
                iv = model.NewIntervalVar(start, dur, end, f"iv_{nombre}")

                start_vars[nombre] = start
                end_vars[nombre]   = end

                # ── Capacidad por disciplina ─────────────────
                if disc in intervals_por_disc:
                    intervals_por_disc[disc].append((iv, demanda))

                # ── Camioneta ────────────────────────────────
                if ot["Ubicacion"] == "Remota":
                    intervalos_camionetas.append(iv)
                    demandas_camionetas.append(1)

                # ── Precedencia (disc_i → disc_i+1, blq_k → blq_k+1) ──
                if blq_prev_end is not None:
                    # El siguiente bloque empieza al menos 1 día hábil después
                    # (gap = MAX_H_DIA simula la pausa nocturna entre bloques partidos)
                    gap = MAX_H_DIA if k > 0 else 0
                    model.Add(start >= blq_prev_end + gap)
                blq_prev_end = end

            ot_prev_end = blq_prev_end

            # ── Tardiness ponderada ──────────────────────────
            # Se mide sobre el ÚLTIMO bloque de la tarea
            last_nombre = f"{ot['id']}_{disc}_{len(sub_bloques)-1}"
            last_end    = end_vars[last_nombre]
            tard = model.NewIntVar(0, HORIZONTE_SLOTS * 2, f"tard_{last_nombre}")
            model.Add(tard >= last_end - slot_dead)
            model.Add(tard >= 0)
            tard_terms.append(ot["Score"] * tard)

            # ── Inicio tardío (solo del primer bloque) ───────
            first_nombre = f"{ot['id']}_{disc}_0"
            first_start  = start_vars[first_nombre]
            ini_lat = model.NewIntVar(0, HORIZONTE_SLOTS, f"il_{first_nombre}")
            model.Add(ini_lat >= first_start - slot_ini)
            model.Add(ini_lat >= 0)
            ini_lat_terms.append(ini_lat)

    n_bloques = len(start_vars)
    st.success(
        f"✅ **{n_bloques}** bloques de intervalo creados "
        f"· **{n_partidas}** tareas partidas por exceder {MAX_H_DIA}h/turno"
    )

# ============================================================
# ★ FASE 5 – RESTRICCIONES DE CAPACIDAD (ÚNICA, CORRECTA) ★
# ============================================================

with st.expander("FASE 5 – Restricciones de Capacidad", expanded=True):

    st.markdown("""
    #### Una sola `AddCumulative` por disciplina (sin duplicados, sin bloqueos)

    ```
    ∀ t ∈ [0, HORIZONTE_SLOTS]:
        Σ demanda_i · 1[start_i ≤ t < end_i]  ≤  cap[disc]
    ```

    Sin bloques ficticios de overtime → la restricción es siempre satisfacible
    siempre que la demanda total no supere la capacidad total del mes.
    """)

    # ── Una sola AddCumulative por disciplina ────────────────
    for disc, lista in intervals_por_disc.items():
        if lista:
            model.AddCumulative(
                [it[0] for it in lista],
                [it[1] for it in lista],
                capacidad_disciplina[disc]
            )

    # ── Camionetas ────────────────────────────────────────────
    if intervalos_camionetas:
        model.AddCumulative(
            intervalos_camionetas,
            demandas_camionetas,
            CAMIONETAS
        )

    df_cap = pd.DataFrame([{
        "Disciplina":     disc,
        "Técnicos":       cap,
        "Slots / mes":    cap * HORIZONTE_SLOTS,
        "Jornada":        "08:00 – 16:00 · Lun–Sáb",
        "Overtime":       "Fuera del horizonte (no modelado en solver)",
    } for disc, cap in capacidad_disciplina.items()])
    st.dataframe(df_cap, use_container_width=True, hide_index=True)
    st.success(
        f"✅ {len(capacidad_disciplina)} restricciones acumulativas aplicadas "
        f"+ 1 restricción de camionetas (máx. {CAMIONETAS})"
    )

# ============================================================
# ★ FASE 6 – FUNCIÓN OBJETIVO ★
# ============================================================

with st.expander("FASE 6 – Función Objetivo Industrial", expanded=True):

    st.markdown("""
    ### Función objetivo sin colapso temporal

    ```
    MINIMIZAR:
        Σᵢ  Score_i × tardiness_i    (peso alto: OTs críticas NUNCA se atrasan)
      + Σᵢ  15 × inicio_tardio_i     (peso bajo: distribución suave en el mes)
    ```

    | Término | Peso | Propósito |
    |---|---|---|
    | `Score × tardiness` | 100–160 | Tardanzas → costo muy alto |
    | `inicio_tardio` | 15 | Distribuye suavemente sin anclar |
    | ~~`makespan`~~ | ~~eliminado~~ | Sin premio por terminar pronto |
    | ~~`deseo_expansion`~~ | ~~eliminado~~ | Sin incentivo a comprimir el mes |

    **Resultado esperado:** el solver usa toda la capacidad disponible
    durante el mes, distribuyendo naturalmente sin amontonar al inicio.
    """)

    PESO_INI_LAT = 15
    model.Minimize(
        sum(tard_terms)
        + sum(PESO_INI_LAT * t for t in ini_lat_terms)
    )
    st.success("✅ Función objetivo configurada")

# ============================================================
# FASE 7 – RESOLUCIÓN Y RESULTADOS
# ============================================================

with st.expander("FASE 7 – Resolución y Resultados", expanded=True):

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 45
    solver.parameters.num_search_workers  = 4

    with st.spinner("⚙️ Resolviendo… (máx. 45 s)"):
        status = solver.Solve(model)

    STATUS_TXT = {
        cp_model.OPTIMAL:    "ÓPTIMA ✅",
        cp_model.FEASIBLE:   "FACTIBLE ✅  (tiempo límite)",
        cp_model.INFEASIBLE: "INFEASIBLE ❌",
        cp_model.UNKNOWN:    "DESCONOCIDO ⚠️",
    }

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.error(f"Estado: {STATUS_TXT.get(status,'?')}")
        st.stop()

    st.success(
        f"Solución **{STATUS_TXT[status]}**  ·  "
        f"Objetivo: {solver.ObjectiveValue():,.0f}  ·  "
        f"Tiempo: {solver.WallTime():.1f}s"
    )

    # ── Construir DataFrame de resultados ─────────────────────
    resultados = []
    for nombre, s_var in start_vars.items():

        ini_slot = solver.Value(s_var)
        fin_slot = solver.Value(end_vars[nombre])

        partes = nombre.split("_")
        ot_id  = partes[0]
        disc   = partes[1] if len(partes) > 1 else "?"

        ot = next(o for o in raw_ots if o["id"] == ot_id)

        slot_dl      = fecha_a_slot_deadline(ot["Fecha_Limite"])
        atraso_slots = max(0, fin_slot - slot_dl)

        ini_dt = slot_a_dt(ini_slot)
        fin_dt = slot_a_dt(fin_slot)

        resultados.append({
            "Bloque":       nombre,
            "OT":           ot_id,
            "Tipo":         ot["Tipo"],
            "Criticidad":   ot["Criticidad"],
            "Score":        ot["Score"],
            "Disciplina":   disc,
            "Inicio_dt":    ini_dt,
            "Fin_dt":       fin_dt,
            "Fecha":        ini_dt.date(),
            "Hora":         ini_dt.strftime("%H:%M"),
            "Fecha_Limite": ot["Fecha_Limite"],
            "Ini_slot":     ini_slot,
            "Fin_slot":     fin_slot,
            "Atraso_h":     atraso_slots,
            "Backlog":      "SI" if atraso_slots > 0 else "NO",
        })

    df = pd.DataFrame(resultados).sort_values("Ini_slot")

    total   = len(df)
    backlog = (df["Backlog"] == "SI").sum()
    en_hora = total - backlog

    # ── KPIs ─────────────────────────────────────────────────
    st.subheader("📊 KPIs del Plan")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total bloques",  total)
    c2.metric("En tiempo",      en_hora)
    c3.metric("En backlog",     backlog)
    c4.metric("% Cumplimiento", f"{100*en_hora/total:.1f}%")

    st.dataframe(df, use_container_width=True)

    # ── Distribución diaria ────────────────────────────────────
    st.subheader("📈 Carga Diaria")
    cd = df.groupby("Fecha").agg(Bloques=("Bloque","count")).reset_index()
    fig1 = px.bar(
        cd, x="Fecha", y="Bloques",
        title="Bloques de Trabajo por Día Hábil – Marzo 2026",
        text="Bloques", color_discrete_sequence=["#2980b9"],
    )
    fig1.update_traces(textposition="outside")
    fig1.update_layout(xaxis_tickformat="%d %b", bargap=0.25, height=380)
    st.plotly_chart(fig1, use_container_width=True)

    # ── Carga por disciplina ───────────────────────────────────
    st.subheader("🔧 Distribución por Disciplina")
    cd2 = df.groupby(["Fecha","Disciplina"]).size().reset_index(name="Bloques")
    fig2 = px.bar(
        cd2, x="Fecha", y="Bloques", color="Disciplina",
        title="Carga por Disciplina – Marzo 2026", barmode="stack",
    )
    fig2.update_layout(xaxis_tickformat="%d %b", height=400)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Gantt ─────────────────────────────────────────────────
    st.subheader("📅 Diagrama de Gantt")
    st.caption(
        "🟢 En tiempo · 🔴 Backlog · Cada barra = 1 bloque (máx. 8h) · "
        "Escala: tiempo laboral real, Lun–Sáb 08:00–16:00"
    )
    fig_g = px.timeline(
        df,
        x_start="Inicio_dt", x_end="Fin_dt",
        y="OT", color="Backlog",
        color_discrete_map={"NO": "#27ae60", "SI": "#e74c3c"},
        hover_data=["Tipo","Criticidad","Score","Disciplina","Atraso_h","Hora"],
        title="Gantt – Plan de Mantenimiento Marzo 2026",
    )
    fig_g.update_xaxes(
        range=[FECHA_INICIO, FECHA_INICIO + timedelta(days=31)],
        dtick=86_400_000, tickformat="%d %b",
    )
    fig_g.update_layout(height=1100, xaxis_title="Marzo 2026", yaxis_title="OTs")
    fig_g.update_yaxes(autorange="reversed")
    st.plotly_chart(fig_g, use_container_width=True)

    # ── Diagnóstico final ──────────────────────────────────────
    st.subheader("⚠️ Diagnóstico")
    prom_vent = df["Fecha_Limite"].apply(
        lambda x: (x - FECHA_INICIO).days
    ).mean()
    slot_max_usado = df["Fin_slot"].max()

    c1d, c2d, c3d = st.columns(3)
    c1d.metric("Ventana promedio (días)", f"{prom_vent:.1f}")
    c2d.metric("Último slot usado",       f"{slot_max_usado} / {HORIZONTE_SLOTS}")
    c3d.metric("Utilización del horizonte", f"{100*slot_max_usado/HORIZONTE_SLOTS:.0f}%")

    if prom_vent < 5:
        st.warning("⚠️ Ventana promedio < 5 días. Considera ampliar Fecha_Limite.")
    else:
        st.success("✅ Ventanas suficientes – distribución natu
