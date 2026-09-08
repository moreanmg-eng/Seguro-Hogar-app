"""
Prueba end-to-end de la LÓGICA de negocio (sin la interfaz de Streamlit)
para validar que todo el flujo funciona antes de entregarlo.
"""

import os
os.environ.setdefault("ADMIN_EMAIL", "morean.mg@gmail.com")

import db
import cotizador
import pdf_generator
import email_utils
import asesores as asesores_mod

db.init_db()

print("1) Cliente cotiza...")
resultado = cotizador.calcular_prima("Oro", "01000")
assert resultado["prima_total_anual"] > 0
print("   Prima calculada:", resultado["prima_total_anual"])

cot_id = db.crear_cotizacion(
    cliente_nombre="Juan Pérez", cliente_correo="juan@example.com",
    cliente_telefono="5512345678", codigo_postal="01000",
    paquete="Oro", prima_total_anual=resultado["prima_total_anual"],
    pdf_cotizacion_path=None,
)
ruta_pdf = pdf_generator.generar_pdf_cotizacion(
    "Juan Pérez", "juan@example.com", "5512345678", resultado, cot_id
)
with db._conn() as conn:
    conn.execute("UPDATE cotizaciones SET pdf_cotizacion_path = ? WHERE id = ?", (ruta_pdf, cot_id))
    conn.commit()
assert os.path.exists(ruta_pdf)
print("   PDF de cotización generado en:", ruta_pdf)

print("2) Cliente decide contratar y elige asesor...")
asesores_df = asesores_mod.cargar_asesores()
nombre_asesor = asesores_df.iloc[0]["nombre"]
db.marcar_interesado(cot_id, nombre_asesor)
cot = db.obtener(cot_id)
assert cot["estatus"] == "interesado"
r = email_utils.notificar_asesor_nuevo_interesado(cot, asesores_mod.correo_de(nombre_asesor))
print("   Notificación a asesor:", r)

print("3) Asesor confirma listo para emisión...")
db.confirmar_por_asesor(cot_id, nombre_asesor, notas="Cliente firmó solicitud y pagó primer recibo")
cot = db.obtener(cot_id)
assert cot["estatus"] == "confirmado_por_asesor"
r = email_utils.notificar_admin_confirmacion_asesor(cot, nombre_asesor)
print("   Notificación a admin:", r)

print("4) Administrador sube la póliza emitida...")
ruta_poliza = db.POLIZAS_DIR / f"poliza_{cot_id:05d}.pdf"
with open(ruta_poliza, "wb") as f:
    f.write(b"%PDF-1.4 (poliza de prueba)")
db.registrar_emision(cot_id, str(ruta_poliza))
cot = db.obtener(cot_id)
assert cot["estatus"] == "emitida"
r = email_utils.notificar_asesor_poliza_emitida(cot, asesores_mod.correo_de(nombre_asesor), str(ruta_poliza))
print("   Notificación de póliza emitida a asesor:", r)

print("5) Asesor marca como entregada al cliente...")
db.marcar_entregada(cot_id)
cot = db.obtener(cot_id)
assert cot["estatus"] == "entregada"

print("\n✅ Flujo completo probado sin errores. Folio:", f"{cot_id:05d}")
print("   Estatus final:", cot["estatus"])
