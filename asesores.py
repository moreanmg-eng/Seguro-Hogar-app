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


def publico_reconocido(nomina: str | None) -> bool:
    """
    True si la nómina/matrícula del cliente trae un prefijo reconocido
    (L0 o A0). Si no lo trae (vacía, o cualquier otro prefijo), no se
    sabe a qué público pertenece ese cliente -- esos casos ya no se
    reparten "por si las dudas" entre todos los asesores, sino que se
    quedan para que el Administrador los revise y los asigne él mismo
    a un asesor específico (ver "Clientes sin público identificado"
    en el panel de Administrador).
    """
    nomina = (nomina or "").strip().upper()
    return nomina.startswith("L0") or nomina.startswith("A0")


def asesores_para_publico(nomina: str | None) -> pd.DataFrame:
    """
    Filtra el catálogo de asesores según a qué público atiende cada
    quien, detectado por el prefijo de la nómina/matrícula del
    cliente ('L0...' o 'A0...'). Un asesor con "publico" = 'ambos'
    siempre se incluye, sin importar el prefijo.

    Si la nómina no trae un prefijo reconocido (vacía, o no empieza
    con L0/A0), o si la columna "publico" no existe en el catálogo
    (por ejemplo en un despliegue viejo que aún no la tiene), regresa
    el catálogo completo sin filtrar — así nunca se oculta un asesor
    por error.
    """
    df = cargar_asesores()
    if "publico" not in df.columns:
        return df

    nomina = (nomina or "").strip().upper()
    if nomina.startswith("L0"):
        prefijo = "L0"
    elif nomina.startswith("A0"):
        prefijo = "A0"
    else:
        return df

    filtrado = df[df["publico"].str.upper().isin([prefijo, "AMBOS"])]
    return filtrado if not filtrado.empty else df


def asesor_atiende_nomina(asesor: dict, nomina: str | None) -> bool:
    """
    True si el "publico" del asesor coincide con el prefijo de la
    nómina/matrícula del cliente (o si el asesor atiende 'ambos').
    Igual que asesores_para_publico(), por seguridad regresa True
    (no oculta el caso) cuando el asesor no tiene "publico" definido,
    o cuando la nómina no trae un prefijo L0/A0 reconocible.
    """
    publico_asesor = (asesor.get("publico") or "").strip().upper()
    if not publico_asesor or publico_asesor == "AMBOS":
        return True

    nomina = (nomina or "").strip().upper()
    if nomina.startswith("L0"):
        prefijo = "L0"
    elif nomina.startswith("A0"):
        prefijo = "A0"
    else:
        return True

    return publico_asesor == prefijo


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
