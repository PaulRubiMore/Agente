import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

# ============================================================
# CONFIGURACIÓN DE PANTALLA
# ============================================================

st.set_page_config(layout="wide")

# Ocultar menú y footer
hide_st_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("🛠️ Generador de Órdenes de Trabajo")

# ============================================================
# DATOS BASE
# ============================================================

disciplinas_posibles = ['Eléctrico', 'Mecánico', 'Instrumentista', 'Civil']
criticidades = ['Alta', 'Media', 'Baja']
ubicaciones = ['Planta', 'Remota']

# ============================================================
# FUNCIÓN GENERADORA
# ============================================================

def generar_orden(id_orden):
    criticidad = random.choice(criticidades)
    fecha = datetime.today() + timedelta(days=random.randint(0, 30))
    ubicacion = random.choice(ubicaciones)
    camion = 'Sí' if ubicacion == 'Remota' else 'No'
    
    num_disciplinas = random.randint(1, 3)
    disciplinas = random.sample(disciplinas_posibles, num_disciplinas)
    
    horas = [random.randint(1, 8) for _ in disciplinas]
    tecnicos = [random.randint(1, 3) for _ in disciplinas]
    
    return {
        'ID': id_orden,
        'Criticidad': criticidad,
        'Fecha': fecha.strftime("%Y-%m-%d"),
        'Ubicación': ubicacion,
        'Camión': camion,
        'Disciplinas': ', '.join(disciplinas),
        'Horas por disciplina': ', '.join(str(h) for h in horas),
        'Técnicos por disciplina': ', '.join(str(t) for t in tecnicos)
    }

# ============================================================
# GENERACIÓN DE ÓRDENES
# ============================================================

num_ordenes = st.slider(
    "Número de órdenes a generar",
    min_value=1,
    max_value=150,
    value=110
)

ordenes = [generar_orden(f"OT{i+1}") for i in range(num_ordenes)]
df_ordenes = pd.DataFrame(ordenes)

# ============================================================
# MÉTRICAS EJECUTIVAS
# ============================================================

st.subheader("Resumen Ejecutivo")

col1, col2, col3 = st.columns(3)

col1.metric("Total Órdenes", len(df_ordenes))
col2.metric(
    "Órdenes Alta Criticidad",
    len(df_ordenes[df_ordenes["Criticidad"] == "Alta"])
)
col3.metric(
    "Órdenes Remotas",
    len(df_ordenes[df_ordenes["Ubicación"] == "Remota"])
)

# ============================================================
# TABLA
# ============================================================

st.subheader("Todas las Órdenes de Trabajo")

st.dataframe(
    df_ordenes,
    use_container_width=True,
    height=700
)
