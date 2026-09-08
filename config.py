"""
Lectura de configuración que funciona tanto:
  - en tu computadora (leyendo el archivo .env), como
  - en Streamlit Community Cloud (leyendo los "Secrets" que se
    configuran desde la página web de tu app, formato TOML).

Así el mismo código funciona en los dos lugares sin cambiar nada.
"""

import os
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    _TIENE_STREAMLIT = True
except Exception:
    _TIENE_STREAMLIT = False


def get_secret(key: str, default=None):
    if _TIENE_STREAMLIT:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.getenv(key, default)
