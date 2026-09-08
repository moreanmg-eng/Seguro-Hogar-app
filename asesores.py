"""
Carga del catálogo de asesores comerciales (usuario/password simples,
pensado para uso interno) y utilidades de autenticación básica.
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent
RUTA_ASESORES = BASE_DIR / "data" / "asesores_ejemplo.xlsx"


def cargar_asesores() -> pd.DataFrame:
    return pd.read_excel(RUTA_ASESORES, dtype=str)


def validar_login(usuario: str, password: str) -> dict | None:
    df = cargar_asesores()
    fila = df[(df["usuario"] == usuario) & (df["password"] == password)]
    if fila.empty:
        return None
    return fila.iloc[0].to_dict()


def correo_de(nombre_asesor: str) -> str | None:
    df = cargar_asesores()
    fila = df[df["nombre"] == nombre_asesor]
    if fila.empty:
        return None
    return fila.iloc[0]["correo"]
