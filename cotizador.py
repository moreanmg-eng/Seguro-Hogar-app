"""
Lógica de cotización real (paquetes Zurich vigentes).

Cómo se calcula la prima total (confirmado con el equipo):

  1. Del código postal se obtiene la zona de Fenómeno Hidrometeorológico
     (siempre aplica) y la zona de Terremoto (solo si el cliente la
     quiere incluir). El paquete "Estándar" nunca usa ninguna de las
     dos zonas — no cubre fenómenos naturales.
  2. prima_anual_total = prima_base_anual del paquete
                        + adicional de zona Hidro (si aplica)
                        + adicional de zona Terremoto (si el cliente la pidió)
  3. prima_diaria = prima_anual_total / 365
  4. dias_restantes = días desde la fecha de cotización hasta el fin
     de vigencia de la póliza de flotilla (esta fecha la define el
     Administrador y puede cambiar cada año).
  5. prima_neta_prorateada = prima_diaria * dias_restantes
  6. prima_total = prima_neta_prorateada + 16% IVA + $1 de derecho de emisión

Los datos vienen de:
  - data/paquetes.xlsx   -> catálogo de paquetes (Propietario/Arrendatario/Estándar)
  - data/zonas_cp.xlsx   -> zona hidro y zona terremoto por código postal
"""

from pathlib import Path
from datetime import date
import pandas as pd

BASE_DIR = Path(__file__).parent
RUTA_PAQUETES = BASE_DIR / "data" / "paquetes.xlsx"
RUTA_ZONAS = BASE_DIR / "data" / "zonas_cp.xlsx"

DIAS_ANIO_COMERCIAL = 365
IVA = 0.16
DERECHO_EMISION = 1.0

NOMBRES_ZONA_HIDRO = {
    "peninsula_yucatan": "Alfa 1 – Península de Yucatán",
    "golfo_pacifico": "Alfa 1 – Golfo de México / Pacífico",
    "interior_republica": "Alfa 1 – Interior de la República",
    "alfa2": "Alfa 2",
    "alfa3": "Alfa 3",
}


def cargar_paquetes() -> pd.DataFrame:
    return pd.read_excel(RUTA_PAQUETES)


def cargar_zonas() -> pd.DataFrame:
    df = pd.read_excel(RUTA_ZONAS, dtype={"codigo_postal": str})
    df["codigo_postal"] = df["codigo_postal"].str.strip().str.zfill(5)
    return df


def paquetes_disponibles(tipo_cliente: str) -> list[dict]:
    """
    tipo_cliente: 'propietario' | 'arrendatario'
    Regresa las opciones de paquete que se le deben mostrar en el
    formulario (los suyos + siempre la opción Estándar), con una
    etiqueta lista para mostrar en el selector.
    """
    df = cargar_paquetes()
    propios = df[df["tipo"] == tipo_cliente]
    estandar = df[df["tipo"] == "estandar"]

    opciones = []
    for _, fila in propios.iterrows():
        suma = fila["suma_edificio_incendio"] + fila["suma_contenidos_incendio"] \
            if tipo_cliente == "propietario" else fila["suma_contenidos_incendio"]
        etiqueta = f"{fila['paquete']} (contenidos ${fila['suma_contenidos_incendio']:,.0f}"
        if tipo_cliente == "propietario":
            etiqueta += f" + edificio ${fila['suma_edificio_incendio']:,.0f}"
        etiqueta += ")"
        opciones.append({"tipo_paquete": tipo_cliente, "paquete": fila["paquete"], "etiqueta": etiqueta})

    for _, fila in estandar.iterrows():
        etiqueta = f"{fila['paquete']} (solo contenidos ${fila['suma_contenidos_incendio']:,.0f}, sin fenómenos naturales)"
        opciones.append({"tipo_paquete": "estandar", "paquete": fila["paquete"], "etiqueta": etiqueta})

    return opciones


def buscar_zona(codigo_postal: str) -> dict | None:
    codigo_postal = str(codigo_postal).strip().zfill(5)
    df = cargar_zonas()
    fila = df[df["codigo_postal"] == codigo_postal]
    if fila.empty:
        return None
    return fila.iloc[0].to_dict()


def calcular_prima(tipo_paquete: str, paquete_nombre: str, codigo_postal: str,
                    incluye_terremoto: bool, fecha_fin_vigencia: date,
                    fecha_cotizacion: date | None = None) -> dict:
    """
    tipo_paquete: 'propietario' | 'arrendatario' | 'estandar'
    Regresa el desglose completo, o lanza ValueError con un mensaje
    claro si falta algún dato (paquete inexistente, CP no encontrado,
    zona de riesgo desconocida para ese CP cuando sí se necesita).
    """
    fecha_cotizacion = fecha_cotizacion or date.today()

    paquetes = cargar_paquetes()
    fila_paquete = paquetes[(paquetes["tipo"] == tipo_paquete) & (paquetes["paquete"] == paquete_nombre)]
    if fila_paquete.empty:
        raise ValueError(f"No existe el paquete '{paquete_nombre}' de tipo '{tipo_paquete}'.")
    paquete = fila_paquete.iloc[0].to_dict()

    prima_base = float(paquete["prima_base_anual"])
    hidro_adder = 0.0
    tev_adder = 0.0
    zona_hidro_key = None
    zona_tev_num = None

    if tipo_paquete != "estandar":
        zona = buscar_zona(codigo_postal)
        if zona is None:
            raise ValueError(
                f"El código postal '{codigo_postal}' no está en nuestro catálogo de zonas. "
                "Verifica que esté bien escrito, o contáctanos para cotizar manualmente."
            )
        zona_hidro_key = zona["zona_hidro_key"]
        zona_tev_num = zona["zona_tev_num"]

        if pd.isna(zona_hidro_key) or not zona_hidro_key:
            raise ValueError(
                "No pudimos determinar la zona de riesgo hidrometeorológico para ese "
                "código postal. Un asesor debe cotizar este caso manualmente."
            )
        hidro_adder = float(paquete[f"hidro_{zona_hidro_key}"])

        if incluye_terremoto:
            if pd.isna(zona_tev_num) or not zona_tev_num:
                raise ValueError(
                    "No pudimos determinar la zona sísmica para ese código postal, así "
                    "que no podemos cotizar la cobertura de Terremoto automáticamente. "
                    "Un asesor debe cotizar este caso manualmente, o puedes continuar sin "
                    "esa cobertura."
                )
            tev_adder = float(paquete[f"tev_zona{int(zona_tev_num)}"])

    prima_anual_total = prima_base + hidro_adder + tev_adder

    dias_restantes = (fecha_fin_vigencia - fecha_cotizacion).days
    dias_restantes = max(dias_restantes, 1)  # nunca menos de 1 día

    prima_diaria = prima_anual_total / DIAS_ANIO_COMERCIAL
    prima_neta_prorateada = prima_diaria * dias_restantes
    iva = prima_neta_prorateada * IVA
    prima_total = prima_neta_prorateada + iva + DERECHO_EMISION

    return {
        "tipo_paquete": tipo_paquete,
        "paquete": paquete_nombre,
        "codigo_postal": str(codigo_postal).strip().zfill(5),
        "suma_edificio_incendio": paquete["suma_edificio_incendio"],
        "suma_contenidos_incendio": paquete["suma_contenidos_incendio"],
        "suma_edificio_remocion_escombros": paquete["suma_edificio_remocion_escombros"],
        "suma_contenidos_remocion_escombros": paquete["suma_contenidos_remocion_escombros"],
        "suma_edificio_gastos_extra": paquete["suma_edificio_gastos_extra"],
        "suma_contenidos_gastos_extra": paquete["suma_contenidos_gastos_extra"],
        "suma_cristales": paquete["suma_cristales"],
        "suma_equipo_electronico": paquete["suma_equipo_electronico"],
        "suma_equipo_electronico_movil": paquete["suma_equipo_electronico_movil"],
        "suma_robo_menaje": paquete["suma_robo_menaje"],
        "suma_robo_transito": paquete["suma_robo_transito"],
        "suma_rc_privada_familiar": paquete["suma_rc_privada_familiar"],
        "suma_rc_arrendatario": paquete["suma_rc_arrendatario"],
        "suma_mascotas": paquete["suma_mascotas"],
        "zona_hidro_key": zona_hidro_key,
        "zona_hidro_nombre": NOMBRES_ZONA_HIDRO.get(zona_hidro_key, "—") if tipo_paquete != "estandar" else "No aplica (paquete Estándar)",
        "zona_tev_num": zona_tev_num,
        "incluye_terremoto": incluye_terremoto and tipo_paquete != "estandar",
        "prima_base_anual": prima_base,
        "hidro_adder": hidro_adder,
        "tev_adder": tev_adder,
        "prima_anual_total": prima_anual_total,
        "fecha_cotizacion": fecha_cotizacion,
        "fecha_fin_vigencia": fecha_fin_vigencia,
        "dias_restantes": dias_restantes,
        "prima_diaria": prima_diaria,
        "prima_neta_prorateada": prima_neta_prorateada,
        "iva": iva,
        "derecho_emision": DERECHO_EMISION,
        "prima_total": prima_total,
    }
