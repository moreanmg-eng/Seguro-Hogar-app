"""
Genera un catálogo de EJEMPLO de asesores comerciales.

Reemplaza data/asesores_ejemplo.xlsx por tu lista real de asesores
(mismas columnas), o dime los nombres/correos y te lo dejo armado.

ADVERTENCIA: el password aquí es una contraseña simple en texto plano,
pensada para uso interno/local con pocas personas de confianza (no es
un sistema de autenticación de nivel empresarial). Si más adelante
hosteas la app públicamente, conviene reforzar esto (hash de password,
login real, etc.).
"""

import pandas as pd

asesores = pd.DataFrame([
    {"nombre": "Ana Torres",   "correo": "ana.torres@ejemplo.com",   "usuario": "ana",   "password": "cambia-esto-1"},
    {"nombre": "Luis Ramírez", "correo": "luis.ramirez@ejemplo.com", "usuario": "luis",  "password": "cambia-esto-2"},
])

asesores.to_excel("data/asesores_ejemplo.xlsx", index=False)
print("Listo: data/asesores_ejemplo.xlsx generado.")
