import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

# ============================================================
# CONFIGURACIÓN DE PANTALLA
# ============================================================

st.set_page_config(layout="wide")

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
tipos_mantenimiento = ['Preventiva', 'Correctiva', 'Predictiva']

# ============================================================
# FUNCIÓN GENERADORA
# ============================================================

def generar_orden(id_orden):
    criticidad = random.choice(criticidades)
    tipo = random.choice(tipos_mantenimiento)
    fecha = datetime.today() + timedelta(days=random.randint(0, 30))
    ubicacion = random.choice(ubicaciones)
    camion = 'Sí' if ubicacion == 'Remota' else 'No'
    
    num_disciplinas = random.randint(1, 3)
    disciplinas = random.sample(disciplinas_posibles, num_disciplinas)
    
    horas = [random.randint(1, 8) for _ in disciplinas]
    tecnicos = [random.randint(1, 3) for _ in disciplinas]
    
    # 🔥 Cálculo Total Horas Hombre
    total_hh = sum(h * t for h, t in zip(horas, tecnicos))
    
    return {
        'ID': id_orden,
        'Tipo': tipo,
        'Criticidad': criticidad,
        'Fecha de planeacion': fecha.strftime("%Y-%m-%d"),
        'Ubicación': ubicacion,
        'Camión': camion,
        'Disciplinas': ', '.join(disciplinas),
        'Horas por disciplina': ', '.join(str(h) for h in horas),
        'Técnicos por disciplina': ', '.join(str(t) for t in tecnicos),
        'Total Horas-Hombre': total_hh
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

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Órdenes", len(df_ordenes))
col2.metric("Alta Criticidad", len(df_ordenes[df_ordenes["Criticidad"] == "Alta"]))
col3.metric("Correctivas", len(df_ordenes[df_ordenes["Tipo"] == "Correctiva"]))
col4.metric("Total HH", df_ordenes["Total Horas-Hombre"].sum())

# ============================================================
# TABLA
# ============================================================

st.subheader("Todas las Órdenes de Trabajo")

st.dataframe(
    df_ordenes,
    use_container_width=True,
    height=700
)


