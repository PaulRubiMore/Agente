# ============================================================
# AGENTE 2 – ANALISTA DE CONDICIÓN DE ACTIVOS
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("🧠 AGENTE 2 – Analista de Condición de Activos")

# ============================================================
# 1️⃣ GENERAR DATOS HISTÓRICOS SIMULADOS
# ============================================================

def generar_datos_activo(nombre_activo):

    fechas = pd.date_range(end=datetime.today(), periods=180)

    np.random.seed(42)

    vibracion = np.random.normal(4.5, 0.5, len(fechas))
    temperatura = np.random.normal(70, 3, len(fechas))

    # Simular degradación progresiva
    vibracion = vibracion + np.linspace(0, 2, len(fechas))
    temperatura = temperatura + np.linspace(0, 5, len(fechas))

    # Simular fallas aleatorias
    fallas = np.random.choice([0,1], size=len(fechas), p=[0.9,0.1])

    df = pd.DataFrame({
        "Fecha": fechas,
        "Vibracion": vibracion,
        "Temperatura": temperatura,
        "Falla": fallas
    })

    return df

# ============================================================
# 2️⃣ SELECCIÓN DE ACTIVO
# ============================================================

activo = st.selectbox("Seleccionar Activo", ["Motor A", "Bomba B", "Compresor C"])

df = generar_datos_activo(activo)

# ============================================================
# 3️⃣ DETECCIÓN DE ANOMALÍAS (Z-SCORE)
# ============================================================

df["Z_Vibracion"] = (df["Vibracion"] - df["Vibracion"].mean()) / df["Vibracion"].std()
df["Anomalia"] = df["Z_Vibracion"].abs() > 2

# ============================================================
# 4️⃣ CÁLCULO DE MTBF
# ============================================================

fechas_falla = df[df["Falla"] == 1]["Fecha"]

if len(fechas_falla) > 1:
    diferencias = fechas_falla.diff().dropna()
    mtbf = diferencias.mean().days
else:
    mtbf = "No suficiente información"

# ============================================================
# 5️⃣ CLASIFICACIÓN DEL ACTIVO
# ============================================================

total_fallas = df["Falla"].sum()
anomalias = df["Anomalia"].sum()

if total_fallas < 5 and anomalias < 5:
    estado = "🟢 Estable"
elif total_fallas < 10:
    estado = "🟡 En Observación"
elif total_fallas < 20:
    estado = "🟠 Degradándose"
else:
    estado = "🔴 Crítico"

# ============================================================
# 6️⃣ DASHBOARD
# ============================================================

col1, col2, col3 = st.columns(3)

col1.metric("Total Fallas", total_fallas)
col2.metric("Anomalías Detectadas", anomalias)
col3.metric("MTBF (días)", mtbf)

st.subheader("Estado del Activo")
st.markdown(f"## {estado}")

# ============================================================
# 7️⃣ GRÁFICAS
# ============================================================

st.subheader("Tendencia de Vibración")

fig1 = px.line(df, x="Fecha", y="Vibracion", title="Vibración del Activo")
st.plotly_chart(fig1, use_container_width=True)

st.subheader("Tendencia de Temperatura")

fig2 = px.line(df, x="Fecha", y="Temperatura", title="Temperatura del Activo")
st.plotly_chart(fig2, use_container_width=True)

# ============================================================
# 8️⃣ ALERTAS
# ============================================================

st.subheader("🚨 Alertas Inteligentes")

if anomalias > 10:
    st.error("Alta cantidad de anomalías detectadas. Revisar inmediatamente.")
elif anomalias > 5:
    st.warning("Activo con comportamiento inestable.")
else:
    st.success("Activo operando dentro de parámetros normales.")

# ============================================================
# 9️⃣ PREDICCIÓN SIMPLE DE FALLA
# ============================================================

tendencia_vibracion = np.polyfit(range(len(df)), df["Vibracion"], 1)[0]

if tendencia_vibracion > 0.01:
    st.warning("📈 Tendencia creciente de vibración. Posible falla futura.")
else:
    st.success("📊 No se detecta tendencia crítica.")
