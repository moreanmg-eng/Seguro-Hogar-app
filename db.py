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

import random
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta

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


# Días naturales que un folio sigue siendo válido para que el cliente
# pueda "recuperar" su cotización y retomar la decisión de contratar.
DIAS_VIGENCIA_RECUPERACION = 5


def _generar_folio(conn) -> str:
    """
    Genera un folio público de la forma 'F123456' (6 dígitos al azar,
    NO consecutivo) a propósito: a diferencia del id interno de la
    base de datos, este folio es el que ve y comparte el cliente, así
    que no debe ser adivinable en secuencia (F1, F2, F3...) para que
    nadie pueda ver los datos de otro cliente solo probando números.
    """
    while True:
        candidato = f"F{random.randint(100000, 999999)}"
        existe = conn.execute(
            "SELECT 1 FROM cotizaciones WHERE folio = ?", (candidato,)
        ).fetchone()
        if not existe:
            return candidato


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL,
                folio TEXT,                          -- identificador público no consecutivo, p.ej. "F193854"

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
                municipio TEXT,                      -- detectado a partir del código postal
                estado_inmueble TEXT,                 -- detectado a partir del código postal
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
        _restaurar_desde_sheets_si_vacio(conn)
        _backfill_folios_faltantes(conn)


def _restaurar_desde_sheets_si_vacio(conn):
    """
    Streamlit Community Cloud NO garantiza que cotizaciones_v2.db
    sobreviva entre despliegues -- cada vez que se sube código nuevo,
    puede arrancar con un contenedor limpio (base de datos local
    vacía). Antes, eso provocaba que el primer respaldo automático a
    Google Sheets SOBRESCRIBIERA la hoja con esa base vacía, borrando
    todo el historial real que sí seguía ahí.

    Para evitarlo: si la tabla local está vacía Y hay un respaldo
    configurado en Google Sheets con datos, se restauran esas filas a
    la base local ANTES de que la app pueda escribir nada nuevo, para
    que el siguiente respaldo automático vuelva a reflejar el
    historial completo en vez de borrarlo.

    Nunca lanza excepción: si algo falla (sin internet, credenciales,
    etc.) simplemente no restaura nada y la app sigue arrancando
    normal, igual que el resto de la integración con Sheets.
    """
    try:
        ya_hay_datos = conn.execute("SELECT 1 FROM cotizaciones LIMIT 1").fetchone()
        if ya_hay_datos:
            return

        import sheets_backup
        filas = sheets_backup.leer_todo()
        if not filas:
            return

        columnas_tabla = [fila["name"] for fila in conn.execute("PRAGMA table_info(cotizaciones)")]
        tipos_columna = {
            fila["name"]: fila["type"] for fila in conn.execute("PRAGMA table_info(cotizaciones)")
        }

        def _convertir(valor, tipo_sql):
            if valor is None or valor == "":
                return None
            if tipo_sql in ("INTEGER", "REAL"):
                try:
                    return int(valor) if tipo_sql == "INTEGER" else float(valor)
                except (TypeError, ValueError):
                    return None
            return str(valor)

        for fila in filas:
            columnas_presentes = [c for c in columnas_tabla if c in fila]
            if "id" not in columnas_presentes:
                continue  # fila sin id no se puede restaurar de forma confiable
            valores = [_convertir(fila.get(c), tipos_columna.get(c)) for c in columnas_presentes]
            placeholders = ", ".join("?" for _ in columnas_presentes)
            conn.execute(
                f"INSERT OR IGNORE INTO cotizaciones ({', '.join(columnas_presentes)}) VALUES ({placeholders})",
                valores,
            )
        conn.commit()
    except Exception:
        pass


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
    "municipio": "TEXT",
    "estado_inmueble": "TEXT",
    "folio": "TEXT",
    "numero_poliza": "TEXT",           # nombre del PDF de la póliza (sin ".pdf"), usado para la liga de pago
    "monto_descuento_nomina": "REAL",  # solo si forma_pago == 'Nómina'
    "motivo_devolucion": "TEXT",       # comentario del asesor al regresar una póliza mal emitida al admin
    "duplicado_de_folio": "TEXT",      # folio de una cotización anterior con el mismo cliente+domicilio+paquete
}


def _migrar_columnas_faltantes(conn):
    columnas_actuales = {fila["name"] for fila in conn.execute("PRAGMA table_info(cotizaciones)")}
    for columna, tipo in _COLUMNAS_NUEVAS.items():
        if columna not in columnas_actuales:
            conn.execute(f"ALTER TABLE cotizaciones ADD COLUMN {columna} {tipo}")


def _backfill_folios_faltantes(conn):
    """
    Si hay filas sin folio (de antes de que existiera esta función, o
    restauradas desde un respaldo de Sheets muy viejo que no tenía esa
    columna), les genera uno para que también se puedan identificar de
    forma consistente.
    """
    filas_sin_folio = conn.execute(
        "SELECT id FROM cotizaciones WHERE folio IS NULL OR folio = ''"
    ).fetchall()
    for fila in filas_sin_folio:
        conn.execute(
            "UPDATE cotizaciones SET folio = ? WHERE id = ?",
            (_generar_folio(conn), fila["id"]),
        )
    if filas_sin_folio:
        conn.commit()


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

def _respaldar_en_sheets():
    """Empuja el snapshot completo de la tabla a Google Sheets (si está
    configurado). Nunca lanza excepción -- si falla o no está
    configurado, simplemente no pasa nada; la operación en SQLite ya
    quedó guardada de todas formas."""
    try:
        import sheets_backup
        sheets_backup.respaldar(listar())
    except Exception:
        pass


def buscar_folio_duplicado(cliente_nombre: str, cliente_correo: str, calle: str,
                            numero_ext: str, colonia: str, codigo_postal: str,
                            paquete: str) -> str | None:
    """
    Busca, en TODO el historial (sin importar estatus ni qué tan vieja
    sea la cotización), si este mismo cliente (mismo nombre Y mismo
    correo) ya cotizó antes exactamente el mismo domicilio (calle,
    número ext., colonia y código postal) con el mismo paquete. Si
    encuentra una coincidencia, regresa el folio de la cotización
    anterior más antigua que coincida; si no, regresa None.

    Esto NO bloquea ni le avisa nada al cliente -- solo se usa para
    marcar la nueva cotización como "posible duplicado" (ver
    duplicado_de_folio) para que el admin/asesor lo vean en su panel.
    """
    if not (cliente_nombre and cliente_correo and calle and numero_ext and colonia and paquete):
        return None
    with _conn() as conn:
        fila = conn.execute("""
            SELECT folio FROM cotizaciones
            WHERE TRIM(UPPER(cliente_nombre)) = TRIM(UPPER(?))
              AND TRIM(LOWER(cliente_correo)) = TRIM(LOWER(?))
              AND TRIM(UPPER(calle)) = TRIM(UPPER(?))
              AND TRIM(UPPER(numero_ext)) = TRIM(UPPER(?))
              AND TRIM(UPPER(colonia)) = TRIM(UPPER(?))
              AND TRIM(UPPER(COALESCE(codigo_postal, ''))) = TRIM(UPPER(?))
              AND TRIM(UPPER(paquete)) = TRIM(UPPER(?))
            ORDER BY fecha_creacion ASC
            LIMIT 1
        """, (
            cliente_nombre, cliente_correo, calle, numero_ext, colonia,
            codigo_postal or "", paquete,
        )).fetchone()
        return fila["folio"] if fila else None


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
        if "folio" not in campos:
            campos["folio"] = _generar_folio(conn)
            columnas = list(campos.keys())
            placeholders = ", ".join("?" for _ in columnas)
        cur = conn.execute(
            f"INSERT INTO cotizaciones ({', '.join(columnas)}) VALUES ({placeholders})",
            [campos[c] for c in columnas],
        )
        conn.commit()
        nuevo_id = cur.lastrowid
    _respaldar_en_sheets()
    return nuevo_id


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
    _respaldar_en_sheets()


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
    _respaldar_en_sheets()


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
    _respaldar_en_sheets()


def cerrar_sin_venta(cotizacion_id: int, motivo: str | None = None):
    """
    Cierra una cotización (típicamente una solicitud manual) como "no
    vendida" -- el cliente no confirmó, o declinó por fuera del portal.
    Queda fuera de las listas de pendientes, pero el registro no se
    borra: sigue apareciendo en el panel general del Administrador con
    ese estatus, para tener historial de qué se perdió y por qué.
    """
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'no_vendida',
                notas = COALESCE(?, notas)
            WHERE id = ?
        """, (motivo, cotizacion_id))
        conn.commit()
    _respaldar_en_sheets()


def descartar_cotizacion(cotizacion_id: int, motivo: str | None = None):
    """
    Descarta una cotización que solo se quedó "cotizada" (el cliente no
    hizo nada después) para que ya no le sature al Administrador la
    lista de "Cotizaciones sin seguimiento". El registro NO se borra:
    sigue apareciendo en el "Panel general de todas las cotizaciones"
    con el estatus "descartada", para tener historial.
    """
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'descartada',
                notas = COALESCE(?, notas)
            WHERE id = ?
        """, (motivo, cotizacion_id))
        conn.commit()
    _respaldar_en_sheets()


def registrar_emision(cotizacion_id: int, poliza_pdf_path: str, numero_poliza: str | None = None,
                       monto_descuento_nomina: float | None = None):
    """
    numero_poliza: nombre original del PDF subido (sin ".pdf"), usado
    para construir la liga de pago (Domiciliado/Contado).
    monto_descuento_nomina: monto quincenal que se le descontará al
    cliente vía nómina (solo aplica cuando forma_pago == 'Nómina').
    """
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'emitida',
                fecha_emision = ?,
                poliza_pdf_path = ?,
                numero_poliza = ?,
                monto_descuento_nomina = ?,
                motivo_devolucion = NULL
            WHERE id = ?
        """, (
            datetime.now().isoformat(timespec="seconds"), poliza_pdf_path,
            numero_poliza, monto_descuento_nomina, cotizacion_id,
        ))
        conn.commit()
    _respaldar_en_sheets()


def regresar_a_admin(cotizacion_id: int, motivo: str):
    """
    El asesor detectó que la póliza no está correctamente emitida (por
    ejemplo, un error de captura) y la regresa a la bandeja del
    administrador para que la corrija: el caso vuelve a aparecer en
    "Confirmados por asesor, pendientes de emitir", con el comentario
    del asesor visible, y se limpia el PDF de la póliza mal emitida
    (el número de póliza y el monto de descuento por nómina, si los
    había, se quedan como estaban -- el admin los puede corregir al
    volver a subir la póliza).
    """
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'confirmado_por_asesor',
                poliza_pdf_path = NULL,
                fecha_emision = NULL,
                motivo_devolucion = ?
            WHERE id = ?
        """, (motivo, cotizacion_id))
        conn.commit()
    _respaldar_en_sheets()


def marcar_entregada(cotizacion_id: int):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'entregada', fecha_entrega = ?
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), cotizacion_id))
        conn.commit()
    _respaldar_en_sheets()


def obtener(cotizacion_id: int) -> dict | None:
    with _conn() as conn:
        fila = conn.execute("SELECT * FROM cotizaciones WHERE id = ?", (cotizacion_id,)).fetchone()
        return dict(fila) if fila else None


def buscar_por_folio_y_correo(folio: str, correo: str) -> dict | None:
    """
    Para la opción "Recuperar cotización" del cliente: solo regresa la
    cotización si el folio Y el correo coinciden con lo que se guardó
    al cotizar (evita que alguien vea los datos de otro cliente solo
    adivinando o probando folios). No filtra por vigencia ni estatus
    -- eso se revisa en la pantalla que llama a esta función, para
    poder mostrar el mensaje correcto en cada caso (expirada, ya en
    proceso, etc.).
    """
    folio = (folio or "").strip().upper()
    correo = (correo or "").strip().lower()
    if not folio or not correo:
        return None
    with _conn() as conn:
        fila = conn.execute(
            "SELECT * FROM cotizaciones WHERE folio = ? AND LOWER(cliente_correo) = ?",
            (folio, correo),
        ).fetchone()
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
