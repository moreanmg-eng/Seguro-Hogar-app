"""
Prueba end-to-end de la LÓGICA de negocio (sin la interfaz de Streamlit)
para validar que todo el flujo funciona antes de entregarlo, usando el
catálogo real de paquetes y zonas.
"""

import os
from datetime import date
os.environ.setdefault("ADMIN_EMAIL", "morean.mg@gmail.com")

import db
import cotizador
import pdf_generator
import email_utils
import asesores as asesores_mod

db.init_db()

print("0) Fecha de fin de vigencia configurada:", db.get_fecha_fin_vigencia())

print("\n1) Cliente propietario cotiza Paquete 2 con Terremoto (CP 01000)...")
fin_vigencia = db.get_fecha_fin_vigencia()
resultado = cotizador.calcular_prima("propietario", "Paquete 2", "01000", True, fin_vigencia)
assert resultado["prima_total"] > 0
assert resultado["municipio"] and resultado["estado"], "Debería detectar municipio/estado para un CP válido"
print("   Prima total:", round(resultado["prima_total"], 2), "| días restantes:", resultado["dias_restantes"])
print("   Municipio/Estado detectados:", resultado["municipio"], "-", resultado["estado"])

cot_id = db.crear_cotizacion(
    cliente_nombre="Juan Pérez", nomina="L012345", forma_pago="Nómina", cliente_correo="juan@example.com",
    cliente_telefono="5512345678", codigo_postal=resultado["codigo_postal"],
    tipo_cliente="propietario", es_para_otro=0, beneficiario_nombre="", beneficiario_relacion="",
    calle="Av. Reforma", numero_ext="123", numero_int="4", colonia="Centro",
    municipio=resultado["municipio"], estado_inmueble=resultado["estado"],
    paquete=resultado["paquete"], tipo_paquete=resultado["tipo_paquete"],
    incluye_terremoto=int(resultado["incluye_terremoto"]),
    zona_hidro_key=resultado["zona_hidro_key"], zona_tev_num=resultado["zona_tev_num"],
    prima_base_anual=resultado["prima_base_anual"], hidro_adder=resultado["hidro_adder"],
    tev_adder=resultado["tev_adder"], prima_anual_total=resultado["prima_anual_total"],
    dias_restantes=resultado["dias_restantes"],
    fecha_fin_vigencia_usada=resultado["fecha_fin_vigencia"].isoformat(),
    prima_neta_prorateada=resultado["prima_neta_prorateada"], iva=resultado["iva"],
    derecho_emision=resultado["derecho_emision"], prima_total=resultado["prima_total"],
)
cot_creada = db.obtener(cot_id)
folio = cot_creada["folio"]
assert folio and folio.startswith("F") and len(folio) == 7 and folio[1:].isdigit(), \
    f"El folio debe verse como 'F123456', no como {folio!r}"
print("   Folio generado (no consecutivo):", folio)

datos_cliente = dict(
    nombre="Juan Pérez", nomina="EMP-001", correo="juan@example.com", telefono="5512345678",
    tipo_cliente="propietario", calle="Av. Reforma", numero_ext="123", numero_int="4",
    colonia="Centro", es_para_otro=False, beneficiario_nombre="", beneficiario_relacion="",
    municipio=resultado["municipio"], estado=resultado["estado"],
)
ruta_pdf = pdf_generator.generar_pdf_cotizacion(datos_cliente, resultado, cot_id, folio)
db.actualizar_cotizacion(cot_id, pdf_cotizacion_path=ruta_pdf)
assert os.path.exists(ruta_pdf)
print("   PDF generado en:", ruta_pdf)

print("\n1.1) Recuperar cotización por folio + correo (nueva función de seguridad)...")
encontrada = db.buscar_por_folio_y_correo(folio, "JUAN@example.com")  # mayúsculas no deben importar
assert encontrada and encontrada["id"] == cot_id
assert db.buscar_por_folio_y_correo(folio, "otro@example.com") is None, "Correo incorrecto no debe regresar nada"
assert db.buscar_por_folio_y_correo("F000000", "juan@example.com") is None, "Folio incorrecto no debe regresar nada"
print("   OK: solo se encuentra con folio Y correo correctos.")

print("\n2) Cliente decide contratar, deja su RFC y elige asesor...")
asesores_df = asesores_mod.cargar_asesores()
nombre_asesor = asesores_df.iloc[0]["nombre"]
db.marcar_interesado(cot_id, nombre_asesor, rfc="PEXJ800101AB1", notas_cliente="Confirmó que quiere contratar.")
cot = db.obtener(cot_id)
assert cot["estatus"] == "interesado"
assert cot["rfc"] == "PEXJ800101AB1"
r = email_utils.notificar_asesor_nuevo_interesado(cot, asesores_mod.correo_de(nombre_asesor))
print("   Notificación a asesor:", r["modo"])

print("\n3) Asesor confirma listo para emisión...")
db.confirmar_por_asesor(cot_id, nombre_asesor, notas="Cliente firmó solicitud")
cot = db.obtener(cot_id)
assert cot["estatus"] == "confirmado_por_asesor"
r = email_utils.notificar_admin_confirmacion_asesor(cot, nombre_asesor)
print("   Notificación a admin:", r["modo"])

print("\n4) Administrador sube la póliza emitida...")
ruta_poliza = db.POLIZAS_DIR / f"poliza_{cot_id:05d}.pdf"
with open(ruta_poliza, "wb") as f:
    f.write(b"%PDF-1.4 (poliza de prueba)")
db.registrar_emision(cot_id, str(ruta_poliza))
cot = db.obtener(cot_id)
assert cot["estatus"] == "emitida"
r = email_utils.notificar_asesor_poliza_emitida(cot, asesores_mod.correo_de(nombre_asesor), str(ruta_poliza))
print("   Notificación de póliza emitida:", r["modo"])

print("\n5) Asesor marca como entregada al cliente...")
db.marcar_entregada(cot_id)
cot = db.obtener(cot_id)
assert cot["estatus"] == "entregada"
print("   Estatus final:", cot["estatus"])

print("\n6) Cliente arrendatario cotiza paquete Solo Contenidos (sin zona, CP inventado válido)...")
resultado_std = cotizador.calcular_prima("estandar", "Solo Contenidos", "20000", False, fin_vigencia)
assert resultado_std["hidro_adder"] == 0 and resultado_std["tev_adder"] == 0
assert round(resultado_std["prima_base_anual"], 2) == 534.24
assert resultado_std["municipio"] and resultado_std["estado"], "Solo Contenidos también debería traer municipio/estado"
print("   Prima total Solo Contenidos:", round(resultado_std["prima_total"], 2))
print("   Municipio/Estado (Solo Contenidos):", resultado_std["municipio"], "-", resultado_std["estado"])

print("\n7) Cliente pide suma personalizada (solicitud manual, sin PDF)...")
cot_id_manual = db.crear_cotizacion(
    cliente_nombre="Ana López", nomina="", cliente_correo="ana@example.com",
    cliente_telefono="5599998888", codigo_postal="01000", tipo_cliente="propietario",
    es_para_otro=0, beneficiario_nombre="", beneficiario_relacion="",
    calle="Calle Falsa", numero_ext="42", numero_int="", colonia="Centro",
    es_solicitud_manual=1, suma_deseada=5_000_000,
)
cot_manual = db.obtener(cot_id_manual)
assert cot_manual["estatus"] == "solicitud_manual"
r = email_utils.notificar_solicitud_manual(cot_manual)
print("   Notificación de solicitud manual:", r["modo"])

print("\n8) CP fuera de catálogo debe fallar con mensaje claro...")
try:
    cotizador.calcular_prima("propietario", "Paquete 1", "99999", False, fin_vigencia)
    print("   ERROR: debería haber lanzado ValueError")
except ValueError as e:
    print("   OK, error esperado:", e)

print("\n9) CP fuera de catálogo con paquete Solo Contenidos NO debe fallar (no necesita zona)...")
resultado_std_sin_cp = cotizador.calcular_prima("estandar", "Solo Contenidos", "99999", False, fin_vigencia)
assert resultado_std_sin_cp["municipio"] is None and resultado_std_sin_cp["estado"] is None
assert resultado_std_sin_cp["prima_total"] > 0
print("   OK, cotiza sin problema y sin municipio/estado (CP desconocido).")

print("\n✅ Flujo completo probado sin errores.")
