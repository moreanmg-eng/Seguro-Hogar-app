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
    {"nombre": "Fernando Muñoz", "correo": "fernando.munoz@raspberry.mx", "usuario": "fernando", "password": "cambia-esto-1"},
    {"nombre": "Martín Morales", "correo": "martin.morales@raspberry.mx", "usuario": "martin",   "password": "cambia-esto-2"},
])

asesores.to_excel("data/asesores_ejemplo.xlsx", index=False)
print("Listo: data/asesores_ejemplo.xlsx generado.")
