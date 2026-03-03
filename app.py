import streamlit as st
import random
from datetime import datetime, timedelta
import pandas as pd

st.title("🛠️ Generador de Órdenes de Trabajo")

# Parámetros
disciplinas_posibles = ['Eléc', 'Mecán', 'Instru', 'Civil']
criticidades = ['Alta', 'Media', 'Baja']
ubicaciones = ['Planta', 'Remota']

def generar_orden(id_orden):
    criticidad = random.choice(criticidades)
    fecha = datetime.today() + timedelta(days=random.randint(0, 30))
    ubicacion = random.choice(ubicaciones)
    camion = 'Sí' if ubicacion == 'Remota' else 'No'
    
    # Seleccionamos aleatoriamente disciplinas (1 a 3)
    num_disciplinas = random.randint(1, 3)
    disciplinas = random.sample(disciplinas_posibles, num_disciplinas)
    
    # Asignamos horas y técnicos por disciplina
    horas = {d: random.randint(1, 8) for d in disciplinas}
    tecnicos = {d: random.randint(1, 3) for d in disciplinas}
    
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

# Generar órdenes
num_ordenes = st.slider("Número de órdenes a generar", min_value=1, max_value=100, value=100)
ordenes = [generar_orden(i+1) for i in range(num_ordenes)]
df_ordenes = pd.DataFrame(ordenes)

# Mostrar tabla completa
st.subheader("Todas las Órdenes de Trabajo")
st.dataframe(df_ordenes)



