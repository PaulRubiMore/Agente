import random
from datetime import datetime, timedelta
import pandas as pd

# Parámetros
disciplinas_posibles = ['Eléctrico', 'Mecánico', 'Instrumentista', 'Civil']
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
        'Fecha': fecha.date(),
        'Ubicación': ubicacion,
        'Camión': camion,
        'Disciplinas': ', '.join(disciplinas),
        'Horas por disciplina': ', '.join([f"{d}:{h}" for d,h in horas.items()]),
        'Técnicos por disciplina': ', '.join([f"{d}:{t}" for d,t in tecnicos.items()])
    }

# Generar 10 órdenes de trabajo
ordenes = [generar_orden(i+1) for i in range(10)]
df_ordenes = pd.DataFrame(ordenes)
print(df_ordenes)
