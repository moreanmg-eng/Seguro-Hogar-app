"""
Base de datos local (SQLite) para dar seguimiento a cada cotización a
lo largo de todo su ciclo de vida:

  cotizada
      -> el cliente cotizó pero aún no dice si quiere contratar
  interesado
      -> el cliente dijo que sí quiere contratar (se notificó al asesor)
  confirmado_por_asesor
      -> el asesor ya dio seguimiento y confirma que está listo para
         que el administrador emita la póliza (se notificó al admin)
  emitida
      -> el administrador subió el PDF de la póliza emitida
         (se notificó al asesor para que la descargue y comparta)
  entregada
      -> el asesor marca que ya se la compartió al cliente (opcional)

  solicitud_manual
      -> el cliente pidió una suma asegurada mayor a los paquetes; no
         se calculó una prima automática, solo se guardaron sus datos
         para que un asesor le dé seguimiento y cotice manualmente.

También guarda una tabla de configuración de una sola fila por llave
(por ahora solo la fecha de fin de vigencia de la póliza de flotilla,
editable desde la vista de Administrador).

cotizaciones.db se crea automáticamente en la primera ejecución.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, date

BASE_DIR = Path(__file__).parent
# Nombre de archivo "v2" a propósito: el esquema de la tabla cambió
# (paquetes reales, zonas, prorrateo). Si en algún despliegue quedara
# por ahí un cotizaciones.db viejo (esquema anterior), esto evita que
# la app truene por columnas que no existen en el archivo antiguo.
DB_PATH = BASE_DIR / "cotizaciones_v2.db"
POLIZAS_DIR = BASE_DIR / "polizas_emitidas"
POLIZAS_DIR.mkdir(exist_ok=True)


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL,

                -- Sección 1 del formulario
                cliente_nombre TEXT NOT NULL,
                nomina TEXT,
                forma_pago TEXT,                     -- 'Nómina' | 'Domiciliado mensual' | 'Contado'
                cliente_correo TEXT NOT NULL,
                cliente_telefono TEXT,
                codigo_postal TEXT NOT NULL,
                tipo_cliente TEXT NOT NULL,          -- 'propietario' | 'arrendatario'
                es_para_otro INTEGER NOT NULL DEFAULT 0,
                beneficiario_nombre TEXT,
                beneficiario_relacion TEXT,

                -- Sección 2 del formulario
                calle TEXT,
                numero_ext TEXT,
                numero_int TEXT,
                colonia TEXT,
                paquete TEXT,                        -- 'Paquete 1'..'Paquete 4' o NULL si es solicitud manual
                tipo_paquete TEXT,                    -- 'propietario' | 'arrendatario' | 'estandar'
                es_solicitud_manual INTEGER NOT NULL DEFAULT 0,
                suma_deseada REAL,                    -- solo si es_solicitud_manual

                -- Sección 3 del formulario
                incluye_terremoto INTEGER NOT NULL DEFAULT 0,

                -- Desglose del cálculo (solo si no es solicitud manual)
                zona_hidro_key TEXT,
                zona_tev_num INTEGER,
                prima_base_anual REAL,
                hidro_adder REAL,
                tev_adder REAL,
                prima_anual_total REAL,
                dias_restantes INTEGER,
                fecha_fin_vigencia_usada TEXT,
                prima_neta_prorateada REAL,
                iva REAL,
                derecho_emision REAL,
                prima_total REAL,

                pdf_cotizacion_path TEXT,
                estatus TEXT NOT NULL DEFAULT 'cotizada',
                asesor_asignado TEXT,
                rfc TEXT,                            -- se captura al decidir contratar
                notas_cliente TEXT,                  -- lo que indicó el cliente al decidir
                fecha_interes TEXT,
                fecha_confirmacion_asesor TEXT,
                fecha_emision TEXT,
                fecha_entrega TEXT,
                poliza_pdf_path TEXT,
                notas TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        _migrar_columnas_faltantes(conn)
        conn.commit()


# ---------------------------------------------------------------------
# Migración ligera: si la tabla "cotizaciones" ya existía de un
# despliegue anterior (con menos columnas), le agrega las que falten
# sin borrar nada. Así, cuando el formulario crece con nuevos campos,
# ya no hace falta renombrar el archivo de la base de datos para evitar
# el error "no such column" — solo se agrega la lista aquí abajo.
# ---------------------------------------------------------------------

_COLUMNAS_NUEVAS = {
    "rfc": "TEXT",
    "notas_cliente": "TEXT",
    "forma_pago": "TEXT",
}


def _migrar_columnas_faltantes(conn):
    columnas_actuales = {fila["name"] for fila in conn.execute("PRAGMA table_info(cotizaciones)")}
    for columna, tipo in _COLUMNAS_NUEVAS.items():
        if columna not in columnas_actuales:
            conn.execute(f"ALTER TABLE cotizaciones ADD COLUMN {columna} {tipo}")


# ---------------------------------------------------------------------
# Configuración (fecha de fin de vigencia, editable por el admin)
# ---------------------------------------------------------------------

def get_config(clave: str, default: str | None = None) -> str | None:
    with _conn() as conn:
        fila = conn.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
        return fila["valor"] if fila else default


def set_config(clave: str, valor: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor),
        )
        conn.commit()


def _default_fin_vigencia() -> str:
    """1 de enero del año siguiente (o del actual si hoy ya es después
    del 1 de enero, lo normal): el próximo 1 de enero que venga."""
    hoy = date.today()
    anio = hoy.year if hoy < date(hoy.year, 1, 1) else hoy.year + 1
    # (date.today() nunca es menor al 1 de enero de su propio año, así
    # que en la práctica esto siempre da el 1 de enero del año siguiente)
    return date(anio, 1, 1).isoformat()


def get_fecha_fin_vigencia() -> date:
    valor = get_config("fecha_fin_vigencia")
    if not valor:
        valor = _default_fin_vigencia()
        set_config("fecha_fin_vigencia", valor)
    return date.fromisoformat(valor)


def set_fecha_fin_vigencia(fecha: date):
    set_config("fecha_fin_vigencia", fecha.isoformat())


# ---------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------

def crear_cotizacion(**campos) -> int:
    """
    Crea una cotización. Pasa los campos como keyword arguments —
    cualquier columna de la tabla que no se especifique queda en NULL
    o su valor por defecto. Siempre agrega fecha_creacion y estatus
    inicial automáticamente.
    """
    campos = dict(campos)
    campos["fecha_creacion"] = datetime.now().isoformat(timespec="seconds")
    campos.setdefault("estatus", "solicitud_manual" if campos.get("es_solicitud_manual") else "cotizada")

    columnas = list(campos.keys())
    placeholders = ", ".join("?" for _ in columnas)
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO cotizaciones ({', '.join(columnas)}) VALUES ({placeholders})",
            [campos[c] for c in columnas],
        )
        conn.commit()
        return cur.lastrowid


def actualizar_cotizacion(cotizacion_id: int, **campos):
    if not campos:
        return
    sets = ", ".join(f"{k} = ?" for k in campos)
    with _conn() as conn:
        conn.execute(
            f"UPDATE cotizaciones SET {sets} WHERE id = ?",
            [*campos.values(), cotizacion_id],
        )
        conn.commit()


def marcar_interesado(cotizacion_id: int, asesor_asignado: str | None = None,
                       rfc: str | None = None, notas_cliente: str | None = None):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'interesado',
                fecha_interes = ?,
                asesor_asignado = COALESCE(?, asesor_asignado),
                rfc = COALESCE(?, rfc),
                notas_cliente = COALESCE(?, notas_cliente)
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), asesor_asignado, rfc, notas_cliente, cotizacion_id))
        conn.commit()


def confirmar_por_asesor(cotizacion_id: int, asesor_nombre: str, notas: str = ""):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'confirmado_por_asesor',
                fecha_confirmacion_asesor = ?,
                asesor_asignado = ?,
                notas = ?
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), asesor_nombre, notas, cotizacion_id))
        conn.commit()


def registrar_emision(cotizacion_id: int, poliza_pdf_path: str):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'emitida',
                fecha_emision = ?,
                poliza_pdf_path = ?
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), poliza_pdf_path, cotizacion_id))
        conn.commit()


def marcar_entregada(cotizacion_id: int):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'entregada', fecha_entrega = ?
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), cotizacion_id))
        conn.commit()


def obtener(cotizacion_id: int) -> dict | None:
    with _conn() as conn:
        fila = conn.execute("SELECT * FROM cotizaciones WHERE id = ?", (cotizacion_id,)).fetchone()
        return dict(fila) if fila else None


def listar(estatus: str | None = None, asesor: str | None = None) -> list[dict]:
    query = "SELECT * FROM cotizaciones"
    condiciones, params = [], []
    if estatus:
        condiciones.append("estatus = ?")
        params.append(estatus)
    if asesor:
        condiciones.append("asesor_asignado = ?")
        params.append(asesor)
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    query += " ORDER BY fecha_creacion DESC"
    with _conn() as conn:
        filas = conn.execute(query, params).fetchall()
        return [dict(f) for f in filas]
