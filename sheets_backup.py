"""
Respaldo automático de todas las cotizaciones a una hoja de Google
Sheets, para no depender solo del archivo SQLite local (que en
Streamlit Community Cloud NO está garantizado como permanente).

Se sincroniza solo, cada vez que se crea o cambia el estatus de una
cotización (ver las llamadas dentro de db.py) — sobrescribe la hoja
completa con el snapshot actual de la tabla "cotizaciones", igual que
el botón "Descargar respaldo completo (Excel)" del panel de
Administrador, pero en vivo y sin que nadie tenga que darle clic.

Mientras no configures las credenciales, la app sigue funcionando
normal: el respaldo simplemente se omite en silencio (modo "no
configurado"), igual que pasa con el correo cuando falta SMTP.

Cómo configurarlo: ver la sección "Respaldo automático en Google
Sheets" del README.md.
"""

import json
from pathlib import Path

import pandas as pd

from config import get_secret

BASE_DIR = Path(__file__).parent
# Alternativa para probar en tu computadora: coloca aquí el archivo
# .json de la cuenta de servicio que descargas de Google Cloud (nunca
# lo subas a GitHub — ya está en .gitignore). En la nube no hace falta
# este archivo, se usan los Secrets de Streamlit.
RUTA_CREDENCIALES_LOCAL = BASE_DIR / "google_service_account.json"

NOMBRE_HOJA = "cotizaciones"
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

_cliente_cache = None


def _credenciales_dict() -> dict | None:
    """Junta las credenciales de la cuenta de servicio de Google,
    probando en este orden: archivo local, Secrets de Streamlit (tabla
    [gcp_service_account]), o una variable de entorno con el JSON
    completo en una sola línea."""
    if RUTA_CREDENCIALES_LOCAL.exists():
        try:
            return json.loads(RUTA_CREDENCIALES_LOCAL.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass

    valor_env = get_secret("GOOGLE_SERVICE_ACCOUNT_JSON")
    if valor_env:
        try:
            return json.loads(valor_env)
        except json.JSONDecodeError:
            return None

    return None


def configurado() -> bool:
    """True si ya hay credenciales de Google Y el ID de la hoja de
    cálculo destino — o sea, si el respaldo automático puede correr."""
    return _credenciales_dict() is not None and bool(get_secret("GOOGLE_SHEET_ID"))


def _obtener_cliente():
    global _cliente_cache
    if _cliente_cache is not None:
        return _cliente_cache

    import gspread
    from google.oauth2.service_account import Credentials

    info = _credenciales_dict()
    credenciales = Credentials.from_service_account_info(info, scopes=_SCOPES)
    _cliente_cache = gspread.authorize(credenciales)
    return _cliente_cache


def respaldar(filas: list[dict]) -> dict:
    """
    Sobrescribe la hoja "cotizaciones" de tu Google Sheet con el
    snapshot completo que le pases (normalmente db.listar()).

    Nunca lanza una excepción: si algo falla (credenciales inválidas,
    hoja no compartida con la cuenta de servicio, sin internet, etc.)
    regresa {"modo": "error", "error": "..."} para que quien la llame
    decida si avisar en pantalla o simplemente ignorarlo, sin tronar
    el resto de la app.
    """
    if not configurado():
        return {"modo": "no_configurado"}

    try:
        import gspread

        cliente = _obtener_cliente()
        hoja_calculo = cliente.open_by_key(get_secret("GOOGLE_SHEET_ID"))
        try:
            hoja = hoja_calculo.worksheet(NOMBRE_HOJA)
        except gspread.exceptions.WorksheetNotFound:
            hoja = hoja_calculo.add_worksheet(title=NOMBRE_HOJA, rows=1000, cols=40)

        df = pd.DataFrame(filas)
        hoja.clear()
        if not df.empty:
            df = df.fillna("")
            hoja.update([df.columns.tolist()] + df.astype(str).values.tolist())
        return {"modo": "sincronizado", "filas": len(df)}
    except Exception as e:
        return {"modo": "error", "error": str(e)}
