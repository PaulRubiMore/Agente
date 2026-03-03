import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta

st.title("🛠️ Generador de Órdenes de Trabajo - Formato Exacto")

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
    horas = {}
    tecnicos = {}
    for d in disciplinas:
        horas[d] = random.randint(1, 8)
        tecnicos[d] = random.randint(1, 3)
    
    return {
        'ID': id_orden,
        'Criticidad': criticidad,
        'Fecha': fecha.strftime("%Y-%m-%d"),
        'Ubicación': ubicacion,
        'Camión': camion,
        'Disciplinas': ', '.join(disciplinas),
        'Horas por disciplina': ', '.join([f"{d}:{h}" for d,h in horas.items()]),
        'Técnicos por disciplina': ', '.join([f"{d}:{t}" for d,t in tecnicos.items()])
    }

# Número de órdenes a generar
num_ordenes = st.slider("Número de órdenes a generar", min_value=1, max_value=50, value=10)
ordenes = [generar_orden(i+1) for i in range(num_ordenes)]
df_ordenes = pd.DataFrame(ordenes)

# Mostrar tabla completa
st.subheader("Todas las Órdenes de Trabajo")
st.dataframe(df_ordenes)

