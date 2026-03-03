import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

st.title("🛠️ Generador de Órdenes de Trabajo - Solo Números")

# Listas posibles
disciplinas_posibles = ['Eléctrico', 'Mecánico', 'Instrumentista', 'Civil']
criticidades = ['Alta', 'Media', 'Baja']
ubicaciones = ['Planta', 'Remota']

def generar_orden(id_orden):
    # Criticidad, fecha, ubicación, camión
    criticidad = random.choice(criticidades)
    fecha = datetime.today() + timedelta(days=random.randint(0,30))
    ubicacion = random.choice(ubicaciones)
    camion = 'Sí' if ubicacion == 'Remota' else 'No'
    
    # Elegimos disciplinas sin repetir
    num_disciplinas = random.randint(1, 3)
    disciplinas = random.sample(disciplinas_posibles, num_disciplinas)
    
    # Asignamos horas y técnicos por disciplina
    horas = [random.randint(1, 8) for _ in disciplinas]
    tecnicos = [random.randint(1, 3) for _ in disciplinas]
    
    return {
        'ID': id_orden,
        'Criticidad': criticidad,
        'Fecha': fecha.strftime("%Y-%m-%d"),
        'Ubicación': ubicacion,
        'Camión': camion,
        'Horas por disciplina': ', '.join(str(h) for h in horas),
        'Técnicos por disciplina': ', '.join(str(t) for t in tecnicos)
    }

# Número de órdenes a generar
num_ordenes = st.slider("Número de órdenes a generar", min_value=1, max_value=50, value=10)
ordenes = [generar_orden(i+1) for i in range(num_ordenes)]
df_ordenes = pd.DataFrame(ordenes)

# Mostrar tabla completa
st.subheader("Todas las Órdenes de Trabajo")
st.dataframe(df_ordenes)

# Filtrado por criticidad
filtro_criticidad = st.multiselect("Filtrar por Criticidad", options=criticidades, default=criticidades)
df_filtrado = df_ordenes[df_ordenes['Criticidad'].isin(filtro_criticidad)]

st.subheader("Órdenes filtradas")
st.dataframe(df_filtrado)
