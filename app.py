"""
Portal de cotización de seguro de hogar — app.py

Tres vistas dentro de la misma app (selector en la barra lateral):

  1. Cliente        -> cotiza, descarga PDF, decide si quiere contratar
  2. Asesor         -> (con login) ve a sus prospectos interesados,
                        confirma cuando está listo para que se emita
  3. Administrador  -> (con password) sube la póliza ya emitida,
                        lo que notifica al asesor para que la comparta

Para correrla:
    streamlit run app.py
"""

from pathlib import Path
from datetime import datetime
import streamlit as st

import db
import cotizador
import pdf_generator
import email_utils
import asesores as asesores_mod
from config import get_secret

db.init_db()

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "cambia-esta-clave")

st.set_page_config(page_title="Cotizador de Seguro de Hogar", page_icon="🏠", layout="centered")

def avisar_si_fallo_correo(resultado: dict | None):
    """Muestra un aviso en pantalla si el envío de correo falló, sin
    interrumpir el flujo (la cotización/estatus ya se guardó igual)."""
    if resultado and resultado.get("modo") == "error":
        st.warning(
            "El registro se guardó correctamente, pero no se pudo enviar el "
            f"correo de aviso. Revisa tu configuración de correo en Secrets. "
            f"Detalle: {resultado.get('error')}"
        )


ESTATUS_LEGIBLE = {
    "cotizada": "Cotizada (sin decisión)",
    "interesado": "Interesado en contratar",
    "confirmado_por_asesor": "Confirmado por asesor, listo para emitir",
    "emitida": "Póliza emitida",
    "entregada": "Entregada al cliente",
}

vista = st.sidebar.radio("¿Quién eres?", ["Cliente", "Asesor", "Administrador"])
if email_utils.MODO_SIMULADO:
    st.sidebar.warning(
        "Modo simulado: no hay credenciales SMTP configuradas en .env, "
        "así que los correos se guardan en correos_simulados/ en vez de "
        "enviarse de verdad. Útil para probar todo el flujo."
    )

# =======================================================================
# VISTA CLIENTE
# =======================================================================
if vista == "Cliente":
    st.title("🏠 Cotiza tu Seguro de Hogar")

    paquetes_df = cotizador.cargar_paquetes()
    asesores_df = asesores_mod.cargar_asesores()

    with st.form("form_cotizacion"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre completo *")
            correo = st.text_input("Correo electrónico *")
        with col2:
            telefono = st.text_input("Teléfono")
            codigo_postal = st.text_input("Código postal *", max_chars=5)

        paquete_elegido = st.selectbox("Paquete de interés *", paquetes_df["paquete"].tolist())
        enviado = st.form_submit_button("Cotizar")

    if enviado:
        if not nombre or not correo or not codigo_postal:
            st.error("Por favor completa nombre, correo y código postal.")
        else:
            try:
                resultado = cotizador.calcular_prima(paquete_elegido, codigo_postal)
            except ValueError as e:
                st.error(str(e))
            else:
                cotizacion_id = db.crear_cotizacion(
                    cliente_nombre=nombre, cliente_correo=correo,
                    cliente_telefono=telefono, codigo_postal=codigo_postal,
                    paquete=paquete_elegido, prima_total_anual=resultado["prima_total_anual"],
                    pdf_cotizacion_path=None,
                )
                ruta_pdf = pdf_generator.generar_pdf_cotizacion(
                    nombre, correo, telefono, resultado, cotizacion_id
                )
                with db._conn() as conn:
                    conn.execute("UPDATE cotizaciones SET pdf_cotizacion_path = ? WHERE id = ?",
                                 (ruta_pdf, cotizacion_id))
                    conn.commit()

                st.session_state["ultima_cotizacion_id"] = cotizacion_id
                st.success(f"¡Cotización lista! Folio {cotizacion_id:05d}")
                st.metric("Prima total anual", f"${resultado['prima_total_anual']:,.2f} MXN")

                with open(ruta_pdf, "rb") as f:
                    st.download_button("📄 Descargar cotización en PDF", f,
                                        file_name=Path(ruta_pdf).name, mime="application/pdf")

    # Paso 2: decisión de contratar, para la última cotización generada en esta sesión
    if "ultima_cotizacion_id" in st.session_state:
        st.divider()
        cot_id = st.session_state["ultima_cotizacion_id"]
        cot = db.obtener(cot_id)
        if cot and cot["estatus"] == "cotizada":
            st.subheader("¿Deseas contratar esta póliza?")
            asesor_pref = st.selectbox(
                "Asesor de preferencia (opcional)",
                ["Cualquiera disponible"] + asesores_df["nombre"].tolist(),
                key="asesor_pref",
            )
            c1, c2 = st.columns(2)
            if c1.button("✅ Sí, quiero contratar"):
                asesor_asignado = None if asesor_pref == "Cualquiera disponible" else asesor_pref
                db.marcar_interesado(cot_id, asesor_asignado)
                cot_actualizada = db.obtener(cot_id)

                # A quién notificar: el asesor elegido, o el primero de la lista si no eligió
                nombre_para_correo = asesor_asignado or asesores_df.iloc[0]["nombre"]
                correo_asesor = asesores_mod.correo_de(nombre_para_correo)
                if correo_asesor:
                    r = email_utils.notificar_asesor_nuevo_interesado(cot_actualizada, correo_asesor)
                    avisar_si_fallo_correo(r)

                st.success("¡Gracias! Un asesor se pondrá en contacto contigo en breve.")
                del st.session_state["ultima_cotizacion_id"]
            if c2.button("No por ahora"):
                st.info("Sin problema, tu cotización queda guardada por si decides contratar después.")
                del st.session_state["ultima_cotizacion_id"]

# =======================================================================
# VISTA ASESOR
# =======================================================================
elif vista == "Asesor":
    st.title("👤 Portal del Asesor")

    if "asesor_autenticado" not in st.session_state:
        st.session_state["asesor_autenticado"] = None

    if not st.session_state["asesor_autenticado"]:
        with st.form("login_asesor"):
            usuario = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Entrar")
        if entrar:
            asesor = asesores_mod.validar_login(usuario, password)
            if asesor:
                st.session_state["asesor_autenticado"] = asesor
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
        st.stop()

    asesor = st.session_state["asesor_autenticado"]
    st.success(f"Sesión iniciada como {asesor['nombre']}")
    if st.button("Cerrar sesión"):
        st.session_state["asesor_autenticado"] = None
        st.rerun()

    st.divider()
    st.subheader("Prospectos interesados (pendientes de confirmar emisión)")

    interesados = [
        c for c in db.listar(estatus="interesado")
        if c["asesor_asignado"] in (None, "", asesor["nombre"])
    ]
    if not interesados:
        st.info("No tienes prospectos pendientes por ahora.")
    for cot in interesados:
        with st.expander(f"Folio {cot['id']:05d} — {cot['cliente_nombre']} — {cot['paquete']}"):
            st.write(f"**Correo:** {cot['cliente_correo']}")
            st.write(f"**Teléfono:** {cot['cliente_telefono']}")
            st.write(f"**Prima anual:** ${cot['prima_total_anual']:,.2f} MXN")
            st.write(f"**Código postal:** {cot['codigo_postal']}")
            if cot["pdf_cotizacion_path"] and Path(cot["pdf_cotizacion_path"]).exists():
                with open(cot["pdf_cotizacion_path"], "rb") as f:
                    st.download_button("📄 Ver cotización", f, file_name=Path(cot["pdf_cotizacion_path"]).name,
                                        key=f"pdf_{cot['id']}")
            notas = st.text_area("Notas para el administrador (opcional)", key=f"notas_{cot['id']}")
            if st.button("✅ Confirmar listo para emisión", key=f"confirmar_{cot['id']}"):
                db.confirmar_por_asesor(cot["id"], asesor["nombre"], notas)
                cot_actualizada = db.obtener(cot["id"])
                r = email_utils.notificar_admin_confirmacion_asesor(cot_actualizada, asesor["nombre"])
                avisar_si_fallo_correo(r)
                st.success("Confirmado. Se notificó al administrador para que emita la póliza.")
                st.rerun()

    st.divider()
    st.subheader("Pólizas emitidas, listas para compartir con el cliente")
    emitidas = [c for c in db.listar(estatus="emitida") if c["asesor_asignado"] == asesor["nombre"]]
    if not emitidas:
        st.info("No tienes pólizas emitidas pendientes de entregar.")
    for cot in emitidas:
        with st.expander(f"Folio {cot['id']:05d} — {cot['cliente_nombre']}"):
            if cot["poliza_pdf_path"] and Path(cot["poliza_pdf_path"]).exists():
                with open(cot["poliza_pdf_path"], "rb") as f:
                    st.download_button("📄 Descargar póliza", f, file_name=Path(cot["poliza_pdf_path"]).name,
                                        key=f"poliza_{cot['id']}")
            if st.button("Marcar como entregada al cliente", key=f"entregada_{cot['id']}"):
                db.marcar_entregada(cot["id"])
                st.success("Marcada como entregada.")
                st.rerun()

# =======================================================================
# VISTA ADMINISTRADOR
# =======================================================================
elif vista == "Administrador":
    st.title("🛠️ Portal del Administrador")

    if "admin_autenticado" not in st.session_state:
        st.session_state["admin_autenticado"] = False

    if not st.session_state["admin_autenticado"]:
        with st.form("login_admin"):
            password = st.text_input("Contraseña de administrador", type="password")
            entrar = st.form_submit_button("Entrar")
        if entrar:
            if password == ADMIN_PASSWORD:
                st.session_state["admin_autenticado"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()

    if st.button("Cerrar sesión"):
        st.session_state["admin_autenticado"] = False
        st.rerun()

    st.divider()
    st.subheader("Confirmados por asesor, pendientes de emitir")
    pendientes = db.listar(estatus="confirmado_por_asesor")
    if not pendientes:
        st.info("No hay pólizas pendientes de emitir por ahora.")
    for cot in pendientes:
        with st.expander(f"Folio {cot['id']:05d} — {cot['cliente_nombre']} — {cot['paquete']}"):
            st.write(f"**Asesor:** {cot['asesor_asignado']}")
            st.write(f"**Notas del asesor:** {cot['notas'] or '—'}")
            st.write(f"**Prima anual:** ${cot['prima_total_anual']:,.2f} MXN")
            archivo = st.file_uploader("Subir PDF de la póliza emitida", type="pdf", key=f"upload_{cot['id']}")
            if archivo and st.button("Confirmar emisión y notificar al asesor", key=f"emitir_{cot['id']}"):
                ruta_destino = db.POLIZAS_DIR / f"poliza_{cot['id']:05d}.pdf"
                with open(ruta_destino, "wb") as f:
                    f.write(archivo.read())
                db.registrar_emision(cot["id"], str(ruta_destino))
                cot_actualizada = db.obtener(cot["id"])
                correo_asesor = asesores_mod.correo_de(cot["asesor_asignado"])
                if correo_asesor:
                    r = email_utils.notificar_asesor_poliza_emitida(cot_actualizada, correo_asesor, str(ruta_destino))
                    avisar_si_fallo_correo(r)
                st.success("Póliza registrada y asesor notificado.")
                st.rerun()

    st.divider()
    st.subheader("Panel general de todas las cotizaciones")

    st.warning(
        "⚠️ Si esta app está desplegada en Streamlit Community Cloud, el "
        "almacenamiento **no está garantizado como permanente**: la "
        "plataforma puede borrar los archivos locales (la base de datos y "
        "los PDFs) en cualquier reinicio. Descarga un respaldo seguido, "
        "sobre todo después de registrar contrataciones o emisiones "
        "importantes."
    )

    todas = db.listar()
    if todas:
        import pandas as pd
        import io

        df = pd.DataFrame(todas)
        df_mostrar = df[[
            "id", "fecha_creacion", "cliente_nombre", "paquete",
            "prima_total_anual", "estatus", "asesor_asignado"
        ]].copy()
        df_mostrar["estatus"] = df_mostrar["estatus"].map(ESTATUS_LEGIBLE).fillna(df_mostrar["estatus"])
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, sheet_name="cotizaciones")
        buffer.seek(0)
        nombre_respaldo = f"respaldo_cotizaciones_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        st.download_button(
            "📥 Descargar respaldo completo (Excel)",
            buffer,
            file_name=nombre_respaldo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("Aún no hay cotizaciones registradas.")
