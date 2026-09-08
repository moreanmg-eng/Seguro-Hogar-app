"""
Genera los archivos Excel de EJEMPLO usados por el cotizador mientras
se integra el Excel real del usuario (paquetes + códigos postales).

Estructura pensada para ser fácil de reemplazar:
- data/paquetes_ejemplo.xlsx      -> catálogo de paquetes pre-armados
- data/codigos_postales_ejemplo.xlsx -> factor de riesgo/prima por CP

Cuando llegue el Excel real, solo hay que:
1) Copiar sus hojas a data/paquetes.xlsx y data/codigos_postales.xlsx
   (o ajustar las rutas en cotizador.py), y
2) Verificar que los nombres de columna coincidan con los que usa
   cotizador.py (están documentados ahí mismo).
"""

import pandas as pd

# ---------------------------------------------------------------------
# 1) Paquetes pre-armados por suma asegurada
# ---------------------------------------------------------------------
paquetes = pd.DataFrame([
    {
        "paquete": "Bronce",
        "suma_asegurada_contenidos": 250_000,
        "suma_asegurada_rc": 500_000,
        "cobertura_incendio": True,
        "cobertura_robo": False,
        "cobertura_cristales": False,
        "cobertura_responsabilidad_civil": True,
        "deducible_pct": 5,
        "prima_base_anual": 1800,
    },
    {
        "paquete": "Plata",
        "suma_asegurada_contenidos": 500_000,
        "suma_asegurada_rc": 1_000_000,
        "cobertura_incendio": True,
        "cobertura_robo": True,
        "cobertura_cristales": False,
        "cobertura_responsabilidad_civil": True,
        "deducible_pct": 5,
        "prima_base_anual": 3200,
    },
    {
        "paquete": "Oro",
        "suma_asegurada_contenidos": 1_000_000,
        "suma_asegurada_rc": 2_000_000,
        "cobertura_incendio": True,
        "cobertura_robo": True,
        "cobertura_cristales": True,
        "cobertura_responsabilidad_civil": True,
        "deducible_pct": 3,
        "prima_base_anual": 5600,
    },
    {
        "paquete": "Platino",
        "suma_asegurada_contenidos": 2_000_000,
        "suma_asegurada_rc": 3_000_000,
        "cobertura_incendio": True,
        "cobertura_robo": True,
        "cobertura_cristales": True,
        "cobertura_responsabilidad_civil": True,
        "deducible_pct": 2,
        "prima_base_anual": 9800,
    },
])

paquetes.to_excel("data/paquetes_ejemplo.xlsx", index=False)

# ---------------------------------------------------------------------
# 2) Factor de prima por código postal (zona de riesgo)
#    factor_zona multiplica la prima_base_anual del paquete elegido
# ---------------------------------------------------------------------
codigos_postales = pd.DataFrame([
    {"codigo_postal": "01000", "estado": "CDMX", "municipio": "Álvaro Obregón", "zona_riesgo": "Baja", "factor_zona": 1.00},
    {"codigo_postal": "03100", "estado": "CDMX", "municipio": "Benito Juárez", "zona_riesgo": "Baja", "factor_zona": 1.00},
    {"codigo_postal": "06700", "estado": "CDMX", "municipio": "Cuauhtémoc", "zona_riesgo": "Media", "factor_zona": 1.10},
    {"codigo_postal": "09000", "estado": "CDMX", "municipio": "Iztapalapa", "zona_riesgo": "Alta", "factor_zona": 1.25},
    {"codigo_postal": "44100", "estado": "Jalisco", "municipio": "Guadalajara", "zona_riesgo": "Media", "factor_zona": 1.08},
    {"codigo_postal": "64000", "estado": "Nuevo León", "municipio": "Monterrey", "zona_riesgo": "Media", "factor_zona": 1.05},
    {"codigo_postal": "72000", "estado": "Puebla", "municipio": "Puebla", "zona_riesgo": "Baja", "factor_zona": 0.98},
])

codigos_postales.to_excel("data/codigos_postales_ejemplo.xlsx", index=False)

print("Listo: data/paquetes_ejemplo.xlsx y data/codigos_postales_ejemplo.xlsx generados.")
