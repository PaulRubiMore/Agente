import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

# 👉 Pantalla en modo ancho
st.set_page_config(layout="wide")

st.title("🛠️ Generador de Órdenes de Trabajo - Solo Números")

# Listas posibles
disciplinas_posibles = ['Eléctrico', 'Mecánico', 'Instrumentista', 'Civil']
criticidades = ['Alta', 'Media', 'Baja']
ubicaciones = ['Planta', 'Remota']

def generar_orden(id_orden):
    criticidad = random.choice(criticidades)
    fecha = datetime.today() + timedelta(days=random.randint(0,30))
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

num_ordenes = st.slider("Número de órdenes a generar", min_value=1, max_value=150, value=110)
ordenes = [generar_orden(i+1) for i in range(num_ordenes)]
df_ordenes = pd.DataFrame(ordenes)

st.subheader("Todas las Órdenes de Trabajo")
st.dataframe(df_ordenes, use_container_width=True)
