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

cotizaciones.db se crea automáticamente en la primera ejecución.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "cotizaciones.db"
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
                cliente_nombre TEXT NOT NULL,
                cliente_correo TEXT NOT NULL,
                cliente_telefono TEXT,
                codigo_postal TEXT NOT NULL,
                paquete TEXT NOT NULL,
                prima_total_anual REAL NOT NULL,
                pdf_cotizacion_path TEXT,
                estatus TEXT NOT NULL DEFAULT 'cotizada',
                asesor_asignado TEXT,
                fecha_interes TEXT,
                fecha_confirmacion_asesor TEXT,
                fecha_emision TEXT,
                fecha_entrega TEXT,
                poliza_pdf_path TEXT,
                notas TEXT
            )
        """)
        conn.commit()


def crear_cotizacion(cliente_nombre, cliente_correo, cliente_telefono,
                      codigo_postal, paquete, prima_total_anual,
                      pdf_cotizacion_path) -> int:
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO cotizaciones (
                fecha_creacion, cliente_nombre, cliente_correo, cliente_telefono,
                codigo_postal, paquete, prima_total_anual, pdf_cotizacion_path, estatus
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'cotizada')
        """, (
            datetime.now().isoformat(timespec="seconds"),
            cliente_nombre, cliente_correo, cliente_telefono,
            codigo_postal, paquete, prima_total_anual, pdf_cotizacion_path,
        ))
        conn.commit()
        return cur.lastrowid


def marcar_interesado(cotizacion_id: int, asesor_asignado: str | None = None):
    with _conn() as conn:
        conn.execute("""
            UPDATE cotizaciones
            SET estatus = 'interesado',
                fecha_interes = ?,
                asesor_asignado = COALESCE(?, asesor_asignado)
            WHERE id = ?
        """, (datetime.now().isoformat(timespec="seconds"), asesor_asignado, cotizacion_id))
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
