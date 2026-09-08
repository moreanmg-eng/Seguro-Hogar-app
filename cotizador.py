"""
Lógica de cotización: carga los catálogos (paquetes y códigos postales)
y calcula la prima total para un paquete + CP determinados.

>>> IMPORTANTE PARA CONECTAR EL EXCEL REAL <<<
Cuando tengas tu Excel real, la forma más simple de integrarlo es:

1. Guardar tu hoja de paquetes como  data/paquetes.xlsx
   Debe tener (al menos) estas columnas, con estos nombres exactos
   (renombra tus columnas o dime cómo se llaman y ajusto el código):
     - paquete                        (texto, nombre del paquete)
     - suma_asegurada_contenidos      (número)
     - suma_asegurada_rc              (número)
     - cobertura_incendio             (True/False)
     - cobertura_robo                 (True/False)
     - cobertura_cristales            (True/False)
     - cobertura_responsabilidad_civil(True/False)
     - deducible_pct                  (número, %)
     - prima_base_anual               (número, $)

2. Guardar tu catálogo de códigos postales como data/codigos_postales.xlsx
   con columnas:
     - codigo_postal   (texto, 5 dígitos)
     - estado
     - municipio
     - zona_riesgo
     - factor_zona     (número que multiplica la prima_base_anual)

3. Cambiar RUTA_PAQUETES y RUTA_CPS abajo para apuntar a esos archivos
   (o simplemente reemplazar los _ejemplo.xlsx una vez validada la
   estructura).

Si tu Excel real calcula la prima de otra forma (por ejemplo, una tabla
de tarifas distinta por suma asegurada y por CP en vez de un factor),
avísame la lógica exacta y ajusto `calcular_prima()`.
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent
RUTA_PAQUETES = BASE_DIR / "data" / "paquetes_ejemplo.xlsx"
RUTA_CPS = BASE_DIR / "data" / "codigos_postales_ejemplo.xlsx"


def cargar_paquetes() -> pd.DataFrame:
    return pd.read_excel(RUTA_PAQUETES, dtype={"paquete": str})


def cargar_codigos_postales() -> pd.DataFrame:
    df = pd.read_excel(RUTA_CPS, dtype={"codigo_postal": str})
    df["codigo_postal"] = df["codigo_postal"].str.strip().str.zfill(5)
    return df


def buscar_cp(codigo_postal: str) -> dict | None:
    codigo_postal = str(codigo_postal).strip().zfill(5)
    df = cargar_codigos_postales()
    fila = df[df["codigo_postal"] == codigo_postal]
    if fila.empty:
        return None
    return fila.iloc[0].to_dict()


def calcular_prima(paquete_nombre: str, codigo_postal: str) -> dict:
    """
    Regresa un dict con el detalle de la cotización, o lanza ValueError
    si el paquete o el CP no existen en los catálogos.
    """
    paquetes = cargar_paquetes()
    fila_paquete = paquetes[paquetes["paquete"] == paquete_nombre]
    if fila_paquete.empty:
        raise ValueError(f"El paquete '{paquete_nombre}' no existe en el catálogo.")
    paquete = fila_paquete.iloc[0].to_dict()

    info_cp = buscar_cp(codigo_postal)
    if info_cp is None:
        raise ValueError(
            f"El código postal '{codigo_postal}' no está en el catálogo. "
            "Verifica que esté escrito correctamente."
        )

    prima_base = float(paquete["prima_base_anual"])
    factor_zona = float(info_cp["factor_zona"])
    prima_total = round(prima_base * factor_zona, 2)

    return {
        "paquete": paquete["paquete"],
        "suma_asegurada_contenidos": paquete["suma_asegurada_contenidos"],
        "suma_asegurada_rc": paquete["suma_asegurada_rc"],
        "cobertura_incendio": bool(paquete["cobertura_incendio"]),
        "cobertura_robo": bool(paquete["cobertura_robo"]),
        "cobertura_cristales": bool(paquete["cobertura_cristales"]),
        "cobertura_responsabilidad_civil": bool(paquete["cobertura_responsabilidad_civil"]),
        "deducible_pct": paquete["deducible_pct"],
        "prima_base_anual": prima_base,
        "codigo_postal": info_cp["codigo_postal"],
        "estado": info_cp["estado"],
        "municipio": info_cp["municipio"],
        "zona_riesgo": info_cp["zona_riesgo"],
        "factor_zona": factor_zona,
        "prima_total_anual": prima_total,
    }
