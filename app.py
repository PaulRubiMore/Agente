import pandas as pd
import random
from datetime import datetime, timedelta

# ============================================================
# PARÁMETROS DE SIMULACIÓN
# ============================================================

num_ot = 20  # Número de órdenes de trabajo a generar

criticidad_list = ["Alta", "Media", "Baja"]
ubicacion_list = ["Planta", "Remota"]
disciplinas_list = ["Mecánica", "Eléctrica", "Instrumentación", "Seguridad"]

# Para cada disciplina, horas hombre promedio requeridas
horas_por_disciplina = {
    "Mecánica": 4,
    "Eléctrica": 3,
    "Instrumentación": 2,
    "Seguridad": 1
}

# Técnicos disponibles por disciplina
tecnicos_por_disciplina = {
    "Mecánica": ["T1", "T2", "T3"],
    "Eléctrica": ["T4", "T5"],
    "Instrumentación": ["T6", "T7"],
    "Seguridad": ["T8", "T9"]
}

# ============================================================
# GENERACIÓN DE ÓRDENES DE TRABAJO
# ============================================================

ordenes = []

for i in range(1, num_ot + 1):
    # Datos básicos
    criticidad = random.choice(criticidad_list)
    fecha = datetime.now() + timedelta(days=random.randint(0, 30))
    ubicacion = random.choice(ubicacion_list)
    
    # Camión solo si es remota
    camion = None
    if ubicacion == "Remota":
        camion = f"Camión-{random.randint(1,5)}"
    
    # Selección de disciplinas requeridas
    num_disciplinas = random.randint(1, len(disciplinas_list))
    disciplinas_requeridas = random.sample(disciplinas_list, num_disciplinas)
    
    # Horas hombre y técnicos por disciplina
    detalle_disciplinas = []
    for disc in disciplinas_requeridas:
        horas = horas_por_disciplina[disc]
        tecnicos = random.sample(tecnicos_por_disciplina[disc], k=1)
        detalle_disciplinas.append({
            "Disciplina": disc,
            "Horas": horas,
            "Tecnicos": tecnicos
        })
    
    # Crear diccionario de OT
    ot = {
        "ID_OT": f"OT-{i:03d}",
        "Criticidad": criticidad,
        "Fecha": fecha.strftime("%Y-%m-%d"),
        "Ubicacion": ubicacion,
        "Camion": camion,
        "Detalle_Disciplinas": detalle_disciplinas
    }
    
    ordenes.append(ot)

# ============================================================
# CONVERTIR A DATAFRAME PARA VISUALIZAR
# ============================================================

# Dataframe simplificado para ver resumen
resumen = []
for ot in ordenes:
    for disc in ot["Detalle_Disciplinas"]:
        resumen.append({
            "ID_OT": ot["ID_OT"],
            "Criticidad": ot["Criticidad"],
            "Fecha": ot["Fecha"],
            "Ubicacion": ot["Ubicacion"],
            "Camion": ot["Camion"],
            "Disciplina": disc["Disciplina"],
            "Horas": disc["Horas"],
            "Tecnicos": ", ".join(disc["Tecnicos"])
        })

df_ot = pd.DataFrame(resumen)

# Mostrar resultado
print(df_ot)

# Guardar en Excel si se quiere
df_ot.to_excel("ordenes_trabajo.xlsx", index=False)
