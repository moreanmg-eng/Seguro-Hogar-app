"""
Portal de cotización de seguro de hogar — app.py

Tres vistas dentro de la misma app (selector en la barra lateral):

  1. Cliente        -> cotiza (3 secciones), descarga PDF, decide si
                        quiere contratar
  2. Asesor         -> (con login) ve a sus prospectos interesados y
                        solicitudes manuales, confirma cuando está
                        listo para que se emita
  3. Administrador  -> (con password) define la fecha de fin de
                        vigencia, sube la póliza ya emitida

Para correrla:
    streamlit run app.py
"""

import re
from pathlib import Path
from datetime import datetime, date
import streamlit as st

import db
import cotizador
import pdf_generator
import email_utils
import sheets_backup
import asesores as asesores_mod
from config import get_secret

db.init_db()

# Verificación básica de formato de RFC (no exhaustiva: no valida dígito
# verificador). 3-4 letras + 6 dígitos (fecha) + 2-3 caracteres alfanuméricos
# = 12 caracteres (persona moral) o 13 (persona física).
_RFC_REGEX = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2,3}$")


def _rfc_parece_valido(rfc: str) -> bool:
    return bool(_RFC_REGEX.match(rfc.strip().upper())) if rfc else False


PLACEHOLDER_PAGO = "Selecciona una opción"

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "cambia-esta-clave")

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_BROKER = ASSETS_DIR / "logo_raspberry.png"
LOGO_ASEGURADORA = ASSETS_DIR / "logo_zurich.png"
AVISO_PRIVACIDAD_PATH = ASSETS_DIR / "aviso_privacidad.md"

st.set_page_config(page_title="Cotizador de Seguro de Hogar", page_icon="🏠", layout="centered")

if LOGO_BROKER.exists() or LOGO_ASEGURADORA.exists():
    col_logo_izq, col_logo_der = st.columns([3, 1])
    if LOGO_BROKER.exists():
        col_logo_izq.image(str(LOGO_BROKER), width=170)
    if LOGO_ASEGURADORA.exists():
        col_logo_der.image(str(LOGO_ASEGURADORA), width=90)


def avisar_si_fallo_correo(resultado: dict | None):
    """Muestra un aviso en pantalla si el envío de correo falló, sin
    interrumpir el flujo (la cotización/estatus ya se guardó igual)."""
    if resultado and resultado.get("modo") == "error":
        st.warning(
            "El registro se guardó correctamente, pero no se pudo enviar el "
            f"correo de aviso. Revisa tu configuración de correo en Secrets. "
            f"Detalle: {resultado.get('error')}"
        )


@st.dialog("¿Confirmar envío de póliza al cliente?")
def _dialog_confirmar_entrega(cot: dict, asesor: dict):
    st.write(
        f"¿Deseas confirmar el envío de la póliza al cliente "
        f"**{cot['cliente_nombre']}** (folio {cot['folio']})?"
    )
    col_si, col_no = st.columns(2)
    if col_si.button("✅ Confirmar", type="primary", use_container_width=True, key=f"dlg_confirmar_{cot['id']}"):
        db.marcar_entregada(cot["id"])
        if cot.get("poliza_pdf_path") and Path(cot["poliza_pdf_path"]).exists():
            r_entrega = email_utils.notificar_cliente_poliza_entregada(
                cot, cot["poliza_pdf_path"], asesor["nombre"], correo_asesor=asesor.get("correo"),
            )
            avisar_si_fallo_correo(r_entrega)
            if r_entrega.get("modo") != "error":
                st.success("Marcada como entregada. Le mandamos la póliza y las indicaciones al cliente (con copia a ti).")
            else:
                st.success("Marcada como entregada.")
        else:
            st.warning(
                "Marcada como entregada, pero no encontré el PDF de la póliza para "
                "mandárselo por correo al cliente — compártesela manualmente."
            )
        st.rerun()
    if col_no.button("❌ Cancelar", use_container_width=True, key=f"dlg_cancelar_{cot['id']}"):
        st.rerun()


@st.dialog("Regresar póliza al administrador")
def _dialog_regresar_poliza(cot: dict):
    st.write(
        f"Vas a regresar la póliza del folio **{cot['folio']}** — "
        f"**{cot['cliente_nombre']}** al administrador para que la corrija."
    )
    motivo = st.text_area(
        "Indica qué no está bien *",
        placeholder="Ejemplo: la calle correcta es Mariano Escobedo y viene como Marian Escobedo.",
        key=f"dlg_motivo_{cot['id']}",
    )
    col_enviar, col_cancelar = st.columns(2)
    if col_enviar.button("📨 Enviar", type="primary", use_container_width=True,
                          disabled=not motivo.strip(), key=f"dlg_enviar_regreso_{cot['id']}"):
        db.regresar_a_admin(cot["id"], motivo.strip())
        st.success("Póliza regresada al administrador con tu comentario.")
        st.rerun()
    if col_cancelar.button("❌ Cancelar", use_container_width=True, key=f"dlg_cancelar_regreso_{cot['id']}"):
        st.rerun()


ESTATUS_LEGIBLE = {
    "cotizada": "Cotizada (sin decisión)",
    "interesado": "Interesado en contratar",
    "confirmado_por_asesor": "Confirmado por asesor, listo para emitir",
    "emitida": "Póliza emitida",
    "entregada": "Entregada al cliente",
    "solicitud_manual": "Requiere cotización manual",
}

vista = st.sidebar.radio("¿Quién eres?", ["Cliente", "Asesor", "Administrador"])
if email_utils.MODO_SIMULADO:
    st.sidebar.warning(
        "Modo simulado: no hay credenciales de correo configuradas, así que "
        "los correos se guardan en correos_simulados/ en vez de enviarse de "
        "verdad. Útil para probar todo el flujo."
    )

# =======================================================================
# VISTA CLIENTE
# =======================================================================
if vista == "Cliente":
    st.title("🏠 Cotiza tu Seguro de Hogar")

    with st.expander("🔎 ¿Ya cotizaste? Recupera tu cotización"):
        st.caption(
            "Si ya cotizaste pero no terminaste de decidir, ingresa tu folio "
            "y el correo con el que cotizaste para continuar donde te "
            f"quedaste. Disponible hasta {db.DIAS_VIGENCIA_RECUPERACION} días "
            "naturales después de haber cotizado."
        )
        col_rec1, col_rec2 = st.columns(2)
        folio_recuperar = col_rec1.text_input("Folio (ej. F193854)", key="c_folio_recuperar")
        correo_recuperar = col_rec2.text_input("Correo con el que cotizaste", key="c_correo_recuperar")
        if st.button("Buscar mi cotización", key="c_buscar_folio"):
            cot_encontrada = db.buscar_por_folio_y_correo(folio_recuperar, correo_recuperar)
            if not cot_encontrada:
                st.error(
                    "No encontramos ninguna cotización con ese folio y ese correo. "
                    "Verifica que estén bien escritos."
                )
            else:
                dias_transcurridos = (datetime.now() - datetime.fromisoformat(cot_encontrada["fecha_creacion"])).days
                if dias_transcurridos > db.DIAS_VIGENCIA_RECUPERACION:
                    st.error("Hemos detectado que tu cotización ya expiró. Te invitamos a generar una nueva.")
                elif cot_encontrada["estatus"] != "cotizada":
                    st.info(
                        "Esta cotización ya está en proceso — un asesor ya tiene tus "
                        "datos y se pondrá en contacto contigo, no es necesario volver "
                        "a decidir nada."
                    )
                else:
                    st.session_state["ultima_cotizacion_id"] = cot_encontrada["id"]
                    st.success("¡Listo! Encontramos tu cotización — continúa aquí abajo. 👇")

    st.subheader("1. Tus datos")
    col1, col2 = st.columns(2)
    with col1:
        nombre = st.text_input("Nombre completo *", key="c_nombre")
        nomina = st.text_input("Nómina / Matrícula", key="c_nomina")
        correo = st.text_input("Correo electrónico *", key="c_correo")
    with col2:
        telefono = st.text_input("Teléfono", key="c_telefono")
        codigo_postal = st.text_input("Código postal *", max_chars=5, key="c_cp")
        municipio_detectado = estado_detectado = None
        cp_limpio = (codigo_postal or "").strip()
        if len(cp_limpio) == 5 and cp_limpio.isdigit():
            zona_cp = cotizador.buscar_zona(cp_limpio)
            if zona_cp and zona_cp.get("municipio") and zona_cp.get("estado"):
                municipio_detectado = zona_cp["municipio"]
                estado_detectado = zona_cp["estado"]
                st.caption(f"📍 {municipio_detectado}, {estado_detectado}")
            else:
                st.caption("No encontramos ese código postal en nuestro catálogo.")

    tipo_cliente_label = st.radio(
        "¿Eres propietario o arrendatario del inmueble?",
        ["Propietario", "Arrendatario"], key="c_tipo_cliente", horizontal=True,
    )
    tipo_cliente = "propietario" if tipo_cliente_label == "Propietario" else "arrendatario"

    para_otro_label = st.radio(
        "¿El seguro es para ti o deseas extender el beneficio a alguien más?",
        ["Para mí", "Para alguien más"], key="c_para_otro", horizontal=True,
    )
    es_para_otro = para_otro_label == "Para alguien más"
    beneficiario_nombre = beneficiario_relacion = ""
    if es_para_otro:
        bc1, bc2 = st.columns(2)
        beneficiario_nombre = bc1.text_input("Nombre completo del beneficiario *", key="c_ben_nombre")
        beneficiario_relacion = bc2.text_input("Relación con el titular *", key="c_ben_relacion")

    # Forma de pago: se detecta según el formato de la nómina/matrícula
    # capturada arriba (L0... = nómina, tiene las 3 opciones; A0... =
    # matrícula, solo domiciliado o contado).
    nomina_valor = (nomina or "").strip().upper()
    forma_pago = None
    if nomina_valor.startswith("L0"):
        forma_pago = st.selectbox(
            "Forma de pago deseada *",
            [PLACEHOLDER_PAGO, "Nómina", "Domiciliado mensual", "Contado"],
            key="c_forma_pago",
        )
    elif nomina_valor.startswith("A0"):
        forma_pago = st.selectbox(
            "Forma de pago deseada *",
            [PLACEHOLDER_PAGO, "Domiciliado mensual", "Contado"],
            key="c_forma_pago",
        )
    elif nomina_valor:
        st.caption(
            "No reconocemos el formato de tu nómina/matrícula (debe iniciar con "
            "L0 para nómina o A0 para matrícula), así que no te mostramos "
            "opciones de forma de pago. Puedes continuar sin problema."
        )

    st.divider()
    st.subheader("2. El inmueble y el paquete")
    dc1, dc2, dc3, dc4 = st.columns([2, 1, 1, 2])
    calle = dc1.text_input("Calle *", key="c_calle")
    numero_ext = dc2.text_input("Número ext. *", key="c_num_ext")
    numero_int = dc3.text_input("Número int.", key="c_num_int")
    colonia = dc4.text_input("Colonia *", key="c_colonia")

    with st.expander("📦 Paq Nuevo - Solo Contenidos"):
        st.caption(
            "Coberturas y montos del paquete Solo Contenidos (no incluye "
            "edificio ni fenómenos naturales)."
        )
        tabla_solo_contenidos = cotizador.tabla_paquete_solo_contenidos()
        st.dataframe(
            tabla_solo_contenidos.style.format("${:,.0f}"),
            use_container_width=True,
        )

    with st.expander("📊 Comparar paquetes disponibles"):
        st.caption(
            "Suma asegurada de cada cobertura por paquete (MXN). La prima "
            "final también depende de tu código postal y de si agregas "
            "Terremoto; esto es solo para comparar coberturas."
        )
        tabla_comparativa = cotizador.tabla_comparativa(tipo_cliente)
        st.dataframe(
            tabla_comparativa.style.format("${:,.0f}"),
            use_container_width=True,
        )

    opciones = cotizador.paquetes_disponibles(tipo_cliente)
    OPCION_PERSONALIZADA = "Deseo asegurar con una suma mayor a la de los paquetes"
    etiquetas = [o["etiqueta"] for o in opciones] + [OPCION_PERSONALIZADA]
    etiqueta_elegida = st.selectbox("Paquete de interés *", etiquetas, key="c_paquete_etiqueta")

    es_personalizada = etiqueta_elegida == OPCION_PERSONALIZADA
    opcion_elegida = None
    suma_deseada = 0.0
    if es_personalizada:
        suma_deseada = st.number_input(
            "¿Con qué suma asegurada te gustaría asegurar tu inmueble? (MXN) *",
            min_value=0.0, step=500000.0, format="%.0f", key="c_suma_deseada",
        )
        if suma_deseada:
            st.caption(f"Suma que se cotizará: **${suma_deseada:,.0f} MXN**")
        st.caption(
            "Esta opción no genera una cotización automática: un asesor "
            "revisará tu solicitud y te cotizará directamente."
        )
    else:
        opcion_elegida = next(o for o in opciones if o["etiqueta"] == etiqueta_elegida)

    incluye_terremoto = False
    if opcion_elegida and opcion_elegida["tipo_paquete"] != "estandar":
        st.divider()
        st.subheader("3. Cobertura adicional")
        incluye_terremoto = st.checkbox(
            "¿Deseas agregar cobertura de Terremoto y/o erupción volcánica?",
            key="c_terremoto",
        )

    st.divider()
    if AVISO_PRIVACIDAD_PATH.exists():
        with st.expander("📄 Ver Aviso de Privacidad"):
            st.markdown(AVISO_PRIVACIDAD_PATH.read_text(encoding="utf-8"))
        acepto_privacidad = st.checkbox(
            "He leído y acepto el Aviso de Privacidad *", key="c_acepto_privacidad",
        )
    else:
        acepto_privacidad = True  # si no existe el archivo, no se bloquea la cotización

    if st.button("Cotizar", type="primary", disabled=not acepto_privacidad):
        faltantes = []
        if not nombre: faltantes.append("nombre completo")
        if not correo: faltantes.append("correo")
        if not codigo_postal or len(codigo_postal.strip()) != 5 or not codigo_postal.strip().isdigit():
            faltantes.append("código postal (5 dígitos)")
        if not calle: faltantes.append("calle")
        if not numero_ext: faltantes.append("número exterior")
        if not colonia: faltantes.append("colonia")
        if es_para_otro and (not beneficiario_nombre or not beneficiario_relacion):
            faltantes.append("nombre y relación del beneficiario")
        if es_personalizada and suma_deseada <= 0:
            faltantes.append("suma asegurada deseada")
        if forma_pago == PLACEHOLDER_PAGO:
            faltantes.append("forma de pago deseada")

        if faltantes:
            st.error("Falta completar: " + ", ".join(faltantes))
        elif es_personalizada:
            cot_id = db.crear_cotizacion(
                cliente_nombre=nombre, nomina=nomina, forma_pago=forma_pago, cliente_correo=correo,
                cliente_telefono=telefono, codigo_postal=codigo_postal.strip(),
                tipo_cliente=tipo_cliente, es_para_otro=int(es_para_otro),
                beneficiario_nombre=beneficiario_nombre, beneficiario_relacion=beneficiario_relacion,
                calle=calle, numero_ext=numero_ext, numero_int=numero_int, colonia=colonia,
                municipio=municipio_detectado, estado_inmueble=estado_detectado,
                es_solicitud_manual=1, suma_deseada=suma_deseada,
            )
            cot = db.obtener(cot_id)
            # Por ahora solo se envían 3 correos automáticos (cotización al
            # cliente, entrega de póliza, y solicitud de contacto de asesor);
            # este aviso al administrador queda deshabilitado a propósito.
            st.success(
                "¡Gracias! Tu información ya fue recabada. Un asesor se pondrá "
                "en contacto contigo pronto para cotizar tu caso."
            )
        else:
            fin_vigencia = db.get_fecha_fin_vigencia()
            try:
                resultado = cotizador.calcular_prima(
                    opcion_elegida["tipo_paquete"], opcion_elegida["paquete"],
                    codigo_postal.strip(), incluye_terremoto, fin_vigencia,
                )
            except ValueError as e:
                st.error(str(e))
            else:
                cot_id = db.crear_cotizacion(
                    cliente_nombre=nombre, nomina=nomina, forma_pago=forma_pago, cliente_correo=correo,
                    cliente_telefono=telefono, codigo_postal=resultado["codigo_postal"],
                    tipo_cliente=tipo_cliente, es_para_otro=int(es_para_otro),
                    beneficiario_nombre=beneficiario_nombre, beneficiario_relacion=beneficiario_relacion,
                    calle=calle, numero_ext=numero_ext, numero_int=numero_int, colonia=colonia,
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
                folio_creado = db.obtener(cot_id)["folio"]
                datos_cliente = dict(
                    nombre=nombre, nomina=nomina, forma_pago=forma_pago, correo=correo, telefono=telefono,
                    tipo_cliente=tipo_cliente, calle=calle, numero_ext=numero_ext,
                    numero_int=numero_int, colonia=colonia, es_para_otro=es_para_otro,
                    beneficiario_nombre=beneficiario_nombre, beneficiario_relacion=beneficiario_relacion,
                    municipio=resultado["municipio"], estado=resultado["estado"],
                )
                ruta_pdf = pdf_generator.generar_pdf_cotizacion(datos_cliente, resultado, cot_id, folio_creado)
                db.actualizar_cotizacion(cot_id, pdf_cotizacion_path=ruta_pdf)
                cot_recien_creada = db.obtener(cot_id)
                r_cliente = email_utils.notificar_cliente_cotizacion(cot_recien_creada, ruta_pdf)

                st.session_state["ultima_cotizacion_id"] = cot_id
                st.success(f"¡Cotización lista! Folio {folio_creado}")
                st.metric("Prima total a pagar", f"${resultado['prima_total']:,.2f} MXN",
                          help=f"Prorrateada por {resultado['dias_restantes']} días restantes de vigencia")

                if r_cliente.get("modo") == "error":
                    st.warning(
                        "Tu cotización se generó correctamente, pero no pudimos "
                        f"enviártela por correo automáticamente. Descárgala aquí abajo. "
                        f"Detalle: {r_cliente.get('error')}"
                    )
                else:
                    st.caption(f"📧 También te enviamos esta cotización a {correo}.")

                with open(ruta_pdf, "rb") as f:
                    st.download_button("📄 Descargar cotización en PDF", f,
                                        file_name=Path(ruta_pdf).name, mime="application/pdf")

    # Paso final: decisión de contratar, para la última cotización generada en esta sesión
    if "ultima_cotizacion_id" in st.session_state:
        st.divider()
        cot_id = st.session_state["ultima_cotizacion_id"]
        cot = db.obtener(cot_id)
        if cot and cot["estatus"] == "cotizada":
            st.subheader("¿Deseas contratar esta póliza?")
            st.caption(
                f"Folio {cot.get('folio') or cot['id']} — {cot.get('paquete') or 'Suma personalizada'} — "
                f"Prima total: ${cot['prima_total']:,.2f} MXN" if cot.get("prima_total")
                else f"Folio {cot.get('folio') or cot['id']}"
            )
            opcion_decision = st.radio(
                "¿Qué te gustaría hacer?",
                [
                    "Sí, quiero contratar",
                    "Quiero que un asesor me contacte para más información",
                    "Por ahora no, gracias",
                ],
                key="c_decision",
            )
            asesores_disponibles = asesores_mod.asesores_para_publico(cot.get("nomina"))
            asesor_pref = st.selectbox(
                "Asesor de preferencia (opcional)",
                ["Cualquiera disponible"] + asesores_disponibles["nombre"].tolist(),
                key="asesor_pref",
            )

            rfc_ingresado = ""
            rfc_valido = True
            if opcion_decision == "Sí, quiero contratar":
                st.info(
                    "Para confirmar que quieres contratar, por favor ingresa tu RFC "
                    "(lo necesitamos para poder emitir tu póliza)."
                )
                rfc_ingresado = st.text_input("RFC *", key="c_rfc_confirmar", max_chars=13)
                rfc_valido = _rfc_parece_valido(rfc_ingresado)
                if rfc_ingresado and not rfc_valido:
                    st.caption("⚠️ Verifica tu RFC: debe tener 12 o 13 caracteres (letras y números).")
                if st.button("✅ Confirmar contratación", disabled=not (rfc_ingresado and rfc_valido)):
                    asesor_asignado = None if asesor_pref == "Cualquiera disponible" else asesor_pref
                    db.marcar_interesado(
                        cot_id, asesor_asignado,
                        rfc=rfc_ingresado.strip().upper(),
                        notas_cliente="Confirmó que quiere contratar.",
                    )
                    cot_actualizada = db.obtener(cot_id)

                    nombre_para_correo = asesor_asignado or asesores_disponibles.iloc[0]["nombre"]
                    correo_asesor = asesores_mod.correo_de(nombre_para_correo)
                    r = email_utils.notificar_cliente_confirmacion_contratacion(cot_actualizada, correo_asesor)
                    avisar_si_fallo_correo(r)

                    st.success("¡Gracias! Un asesor se pondrá en contacto contigo en breve.")
                    del st.session_state["ultima_cotizacion_id"]

            elif opcion_decision == "Quiero que un asesor me contacte para más información":
                rfc_ingresado = st.text_input(
                    "RFC (opcional, si ya lo tienes a la mano)", key="c_rfc_info", max_chars=13,
                )
                if st.button("📞 Solicitar contacto de un asesor"):
                    asesor_asignado = None if asesor_pref == "Cualquiera disponible" else asesor_pref
                    db.marcar_interesado(
                        cot_id, asesor_asignado,
                        rfc=(rfc_ingresado.strip().upper() or None),
                        notas_cliente="Quiere más información antes de decidir.",
                    )
                    cot_actualizada = db.obtener(cot_id)

                    nombre_para_correo = asesor_asignado or asesores_disponibles.iloc[0]["nombre"]
                    correo_asesor = asesores_mod.correo_de(nombre_para_correo)
                    if correo_asesor:
                        r = email_utils.notificar_asesor_nuevo_interesado(
                            cot_actualizada, correo_asesor, asesor_nombre=nombre_para_correo,
                        )
                        avisar_si_fallo_correo(r)

                    st.success("¡Gracias! Un asesor se pondrá en contacto contigo en breve.")
                    del st.session_state["ultima_cotizacion_id"]

            else:
                if st.button("Continuar"):
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
        and asesores_mod.asesor_atiende_nomina(asesor, c.get("nomina"))
    ]
    if not interesados:
        st.info("No tienes prospectos pendientes por ahora.")
    for cot in interesados:
        with st.expander(f"Folio {cot['folio']} — {cot['cliente_nombre']} — {cot['paquete']} ({cot['tipo_paquete']})"):
            st.write(f"**Correo:** {cot['cliente_correo']}")
            st.write(f"**Teléfono:** {cot['cliente_telefono']}")
            st.write(f"**RFC:** {cot.get('rfc') or '— (no lo dejó)'}")
            st.write(f"**Forma de pago deseada:** {cot.get('forma_pago') or '—'}")
            st.write(f"**Motivo:** {cot.get('notas_cliente') or '—'}")
            st.write(f"**Prima total:** ${cot['prima_total']:,.2f} MXN")
            st.write(f"**Código postal:** {cot['codigo_postal']}")
            direccion = ", ".join(filter(None, [cot.get("calle"), cot.get("numero_ext"), cot.get("colonia")]))
            st.write(f"**Dirección:** {direccion or '—'}")
            if cot["pdf_cotizacion_path"] and Path(cot["pdf_cotizacion_path"]).exists():
                with open(cot["pdf_cotizacion_path"], "rb") as f:
                    st.download_button("📄 Ver cotización", f, file_name=Path(cot["pdf_cotizacion_path"]).name,
                                        key=f"pdf_{cot['id']}")
            notas = st.text_area("Notas para el administrador (opcional)", key=f"notas_{cot['id']}")
            if st.button("✅ Confirmar listo para emisión", key=f"confirmar_{cot['id']}"):
                db.confirmar_por_asesor(cot["id"], asesor["nombre"], notas)
                # Por ahora solo se envían 3 correos automáticos (cotización al
                # cliente, entrega de póliza, y solicitud de contacto de asesor);
                # este aviso al administrador queda deshabilitado a propósito.
                st.success("Confirmado. El administrador podrá verlo en su panel para emitir la póliza.")
                st.rerun()

    st.divider()
    st.subheader("📋 Prospectos asignados por Administración")
    st.caption(
        "Clientes que solo cotizaron (no pidieron contacto ni confirmaron "
        "contratar) y que el administrador te asignó para que los "
        "contactes tú directamente."
    )
    asignados_admin = [
        c for c in db.listar(estatus="cotizada")
        if c["asesor_asignado"] == asesor["nombre"]
    ]
    if not asignados_admin:
        st.info("No tienes prospectos asignados por el administrador por ahora.")
    for cot in asignados_admin:
        with st.expander(f"Folio {cot['folio']} — {cot['cliente_nombre']} — {cot['paquete']} ({cot['tipo_paquete']})"):
            st.write(f"**Correo:** {cot['cliente_correo']}")
            st.write(f"**Teléfono:** {cot['cliente_telefono']}")
            st.write(f"**Forma de pago deseada:** {cot.get('forma_pago') or '—'}")
            st.write(f"**Prima total:** ${cot['prima_total']:,.2f} MXN")
            st.write(f"**Código postal:** {cot['codigo_postal']}")
            direccion = ", ".join(filter(None, [cot.get("calle"), cot.get("numero_ext"), cot.get("colonia")]))
            st.write(f"**Dirección:** {direccion or '—'}")
            if cot["pdf_cotizacion_path"] and Path(cot["pdf_cotizacion_path"]).exists():
                with open(cot["pdf_cotizacion_path"], "rb") as f:
                    st.download_button("📄 Ver cotización", f, file_name=Path(cot["pdf_cotizacion_path"]).name,
                                        key=f"pdf_asignado_{cot['id']}")

    st.divider()
    st.subheader("Solicitudes de cotización manual (suma mayor a los paquetes)")
    manuales = [
        c for c in db.listar(estatus="solicitud_manual")
        if c["asesor_asignado"] in (None, "", asesor["nombre"])
        and asesores_mod.asesor_atiende_nomina(asesor, c.get("nomina"))
    ]
    if not manuales:
        st.info("No hay solicitudes manuales pendientes por ahora.")
    for cot in manuales:
        with st.expander(f"Folio {cot['folio']} — {cot['cliente_nombre']} — suma deseada ${cot['suma_deseada']:,.0f}"):
            st.write(f"**Correo:** {cot['cliente_correo']}")
            st.write(f"**Teléfono:** {cot['cliente_telefono']}")
            st.write(f"**Nómina/Matrícula:** {cot.get('nomina') or '—'}")
            st.write(f"**Tipo:** {'Propietario' if cot['tipo_cliente']=='propietario' else 'Arrendatario'}")
            st.write(f"**Código postal:** {cot['codigo_postal']}")
            if not cot["asesor_asignado"]:
                if st.button("Asignarme este caso", key=f"asignar_{cot['id']}"):
                    db.actualizar_cotizacion(cot["id"], asesor_asignado=asesor["nombre"])
                    st.success("Caso asignado. Da seguimiento por fuera del portal para cotizarlo.")
                    st.rerun()
            else:
                st.caption(f"Asignado a {cot['asesor_asignado']}")

    st.divider()
    st.subheader("Pólizas emitidas, listas para compartir con el cliente")
    emitidas = [c for c in db.listar(estatus="emitida") if c["asesor_asignado"] == asesor["nombre"]]
    if not emitidas:
        st.info("No tienes pólizas emitidas pendientes de entregar.")
    for cot in emitidas:
        with st.expander(f"Folio {cot['folio']} — {cot['cliente_nombre']}"):
            if cot["poliza_pdf_path"] and Path(cot["poliza_pdf_path"]).exists():
                with open(cot["poliza_pdf_path"], "rb") as f:
                    st.download_button("📄 Descargar póliza", f, file_name=Path(cot["poliza_pdf_path"]).name,
                                        key=f"poliza_{cot['id']}")
            col_entregar, col_regresar = st.columns(2)
            if col_entregar.button("Marcar como entregada al cliente", key=f"entregada_{cot['id']}", use_container_width=True):
                _dialog_confirmar_entrega(cot, asesor)
            if col_regresar.button("↩️ Regresar póliza al Admin", key=f"regresar_{cot['id']}", use_container_width=True):
                _dialog_regresar_poliza(cot)

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
    st.subheader("Fin de vigencia de la póliza de flotilla")
    st.caption(
        "Toda cotización se prorratea desde el día en que se hace hasta esta "
        "fecha. Actualízala cada vez que renueve la flotilla (normalmente el "
        "1 de enero)."
    )
    fin_actual = db.get_fecha_fin_vigencia()
    if fin_actual < date.today():
        st.warning(f"⚠️ La fecha de fin de vigencia ({fin_actual.strftime('%d/%m/%Y')}) ya pasó. Actualízala antes de seguir cotizando.")
    nueva_fecha = st.date_input("Fecha de fin de vigencia", value=fin_actual, key="fin_vigencia_input")
    if st.button("Guardar fecha de fin de vigencia"):
        db.set_fecha_fin_vigencia(nueva_fecha)
        st.success(f"Actualizada a {nueva_fecha.strftime('%d/%m/%Y')}. Las cotizaciones nuevas usarán esta fecha.")
        st.rerun()

    st.divider()
    st.subheader("📊 Panel de métricas")

    todas_metricas = db.listar()
    if not todas_metricas:
        st.info("Aún no hay cotizaciones registradas para mostrar métricas.")
    else:
        import pandas as pd

        df_m = pd.DataFrame(todas_metricas)
        conteo_estatus = df_m["estatus"].value_counts()

        total_cotizaciones = len(df_m)
        n_interesados = int(conteo_estatus.get("interesado", 0))
        n_confirmados = int(conteo_estatus.get("confirmado_por_asesor", 0))
        n_emitidas = int(conteo_estatus.get("emitida", 0))
        n_entregadas = int(conteo_estatus.get("entregada", 0))
        n_polizas = n_emitidas + n_entregadas
        n_manuales = int(conteo_estatus.get("solicitud_manual", 0))

        # "En pipeline de contratación" = llegó a interesarse en contratar,
        # sin importar en qué paso del proceso vaya ahora.
        en_pipeline = n_interesados + n_confirmados + n_polizas
        tasa_conversion = (en_pipeline / total_cotizaciones * 100) if total_cotizaciones else 0
        # Prima NETA (antes de IVA y del $1 de derecho de emisión) -- es la
        # que se usa para contar internamente, a diferencia de "prima_total"
        # que es lo que paga el cliente (ya con impuestos y derecho incluidos).
        prima_neta_emitida = df_m.loc[df_m["estatus"].isin(["emitida", "entregada"]), "prima_neta_prorateada"].fillna(0).sum()

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Cotizaciones totales", total_cotizaciones)
        col_m2.metric("Quisieron contratar", en_pipeline, help="Pasaron a 'interesado' o más adelante")
        col_m3.metric("Pólizas emitidas", n_polizas)
        col_m4.metric("Tasa de conversión", f"{tasa_conversion:.0f}%", help="Cotizaciones que llegaron a 'interesado' o más adelante")

        col_m5, col_m6 = st.columns(2)
        col_m5.metric("Prima neta emitida", f"${prima_neta_emitida:,.2f} MXN")
        col_m6.metric("Solicitudes manuales (suma mayor)", n_manuales)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.caption("Cotizaciones por estatus")
            conteo_legible = conteo_estatus.rename(index=ESTATUS_LEGIBLE)
            st.bar_chart(conteo_legible)
        with col_g2:
            if df_m["paquete"].notna().any():
                st.caption("Cotizaciones por paquete")
                st.bar_chart(df_m["paquete"].value_counts())
            else:
                st.caption("Aún no hay cotizaciones con paquete automático.")

        if df_m["asesor_asignado"].notna().any():
            st.caption("Casos por asesor (todos los estatus)")
            df_m["_es_poliza"] = df_m["estatus"].isin(["emitida", "entregada"])
            df_m["_prima_neta_emitida"] = df_m["prima_neta_prorateada"].where(df_m["_es_poliza"], 0).fillna(0)
            resumen_asesor = (
                df_m.dropna(subset=["asesor_asignado"])
                .groupby("asesor_asignado")
                .agg(
                    casos=("id", "count"),
                    emitidas=("_es_poliza", "sum"),
                    prima_neta_emitida=("_prima_neta_emitida", "sum"),
                )
                .sort_values("casos", ascending=False)
            )
            st.dataframe(resumen_asesor, use_container_width=True)

    st.divider()
    st.subheader("Confirmados por asesor, pendientes de emitir")
    pendientes = db.listar(estatus="confirmado_por_asesor")
    if not pendientes:
        st.info("No hay pólizas pendientes de emitir por ahora.")
    for cot in pendientes:
        titulo = f"Folio {cot['folio']} — {cot['cliente_nombre']} — {cot['paquete']} ({cot['tipo_paquete']})"
        if cot.get("motivo_devolucion"):
            titulo = "⚠️ DEVUELTA POR ASESOR — " + titulo
        with st.expander(titulo):
            if cot.get("motivo_devolucion"):
                st.error(f"**El asesor regresó esta póliza para corrección:** {cot['motivo_devolucion']}")
            st.write(f"**Asesor:** {cot['asesor_asignado']}")
            st.write(f"**RFC:** {cot.get('rfc') or '⚠️ no lo dejó — pídeselo antes de emitir'}")
            st.write(f"**Forma de pago deseada:** {cot.get('forma_pago') or '—'}")
            st.write(f"**Notas del asesor:** {cot['notas'] or '—'}")
            st.write(f"**Prima total:** ${cot['prima_total']:,.2f} MXN")
            if cot.get("pdf_cotizacion_path") and Path(cot["pdf_cotizacion_path"]).exists():
                with open(cot["pdf_cotizacion_path"], "rb") as f:
                    st.download_button("📄 Descargar cotización", f, file_name=Path(cot["pdf_cotizacion_path"]).name,
                                        key=f"cotizacion_{cot['id']}")
            else:
                st.caption("No hay PDF de cotización disponible (fue una solicitud manual o no se guardó el archivo).")
            archivo = st.file_uploader(
                "Subir PDF de la póliza emitida (el nombre del archivo debe ser el número de póliza)",
                type="pdf", key=f"upload_{cot['id']}",
            )
            if archivo:
                st.caption(f"Número de póliza detectado: **{Path(archivo.name).stem}**")

            monto_descuento = None
            if cot.get("forma_pago") == "Nómina":
                monto_descuento = st.number_input(
                    "Monto de descuento quincenal por nómina (MXN) *",
                    min_value=0.0, step=50.0, format="%.2f", key=f"monto_nomina_{cot['id']}",
                    help="Este cliente eligió pago por Nómina, así que aquí no se genera una liga de "
                         "pago — se le informará este monto a descontar en el correo de entrega.",
                )

            disabled_emitir = not archivo or (cot.get("forma_pago") == "Nómina" and not monto_descuento)
            if st.button("Confirmar emisión y notificar al asesor", key=f"emitir_{cot['id']}", disabled=disabled_emitir):
                numero_poliza = Path(archivo.name).stem
                ruta_destino = db.POLIZAS_DIR / f"poliza_{cot['id']:05d}.pdf"
                with open(ruta_destino, "wb") as f:
                    f.write(archivo.read())
                db.registrar_emision(
                    cot["id"], str(ruta_destino),
                    numero_poliza=numero_poliza, monto_descuento_nomina=monto_descuento,
                )
                # Por ahora solo se envían 3 correos automáticos (cotización al
                # cliente, entrega de póliza, y solicitud de contacto de asesor);
                # este aviso al asesor queda deshabilitado a propósito — lo verá
                # en su panel, en "Pólizas emitidas, listas para compartir".
                st.success("Póliza registrada. El asesor la verá en su panel para entregarla al cliente.")
                st.rerun()

    st.divider()
    st.subheader("Solicitudes de cotización manual")
    manuales = db.listar(estatus="solicitud_manual")
    if not manuales:
        st.info("No hay solicitudes manuales pendientes.")
    for cot in manuales:
        st.write(
            f"Folio {cot['folio']} — {cot['cliente_nombre']} — suma deseada "
            f"${cot['suma_deseada']:,.0f} — asesor: {cot['asesor_asignado'] or 'sin asignar'}"
        )

    st.divider()
    st.subheader("Cotizaciones sin seguimiento (el cliente solo cotizó)")
    st.caption(
        "Aquí aparecen los clientes que generaron su cotización pero no "
        "seleccionaron ninguna opción después (ni pidieron que los "
        "contacten, ni confirmaron contratar). Puedes asignarle un asesor "
        "para que le dé seguimiento por su cuenta y cierre la venta."
    )
    sin_seguimiento = db.listar(estatus="cotizada")
    if not sin_seguimiento:
        st.info("No hay cotizaciones sin seguimiento por ahora.")
    for cot in sin_seguimiento:
        titulo = f"Folio {cot['folio']} — {cot['cliente_nombre']} — {cot['paquete']} ({cot['tipo_paquete']})"
        if cot.get("asesor_asignado"):
            titulo += f"  ·  asignado a {cot['asesor_asignado']}"
        with st.expander(titulo):
            st.write(f"**Correo:** {cot['cliente_correo']}")
            st.write(f"**Teléfono:** {cot['cliente_telefono']}")
            st.write(f"**Forma de pago deseada:** {cot.get('forma_pago') or '—'}")
            st.write(f"**Prima total:** ${cot['prima_total']:,.2f} MXN")
            st.write(f"**Código postal:** {cot['codigo_postal']}")
            direccion = ", ".join(filter(None, [cot.get("calle"), cot.get("numero_ext"), cot.get("colonia")]))
            st.write(f"**Dirección:** {direccion or '—'}")
            if cot.get("pdf_cotizacion_path") and Path(cot["pdf_cotizacion_path"]).exists():
                with open(cot["pdf_cotizacion_path"], "rb") as f:
                    st.download_button("📄 Ver cotización", f, file_name=Path(cot["pdf_cotizacion_path"]).name,
                                        key=f"cotizada_pdf_{cot['id']}")

            candidatos = asesores_mod.asesores_para_publico(cot.get("nomina"))
            nombres_candidatos = candidatos["nombre"].tolist()
            if not nombres_candidatos:
                st.warning("No hay asesores configurados en el catálogo.")
            else:
                index_actual = (
                    nombres_candidatos.index(cot["asesor_asignado"])
                    if cot.get("asesor_asignado") in nombres_candidatos else 0
                )
                asesor_elegido = st.selectbox(
                    "Asignar a Asesor", nombres_candidatos, index=index_actual,
                    key=f"select_asesor_{cot['id']}",
                )
                if st.button("Asignar a Asesor", key=f"btn_asignar_{cot['id']}", use_container_width=True):
                    db.actualizar_cotizacion(cot["id"], asesor_asignado=asesor_elegido)
                    st.success(
                        f"Asignado a {asesor_elegido}. Ya lo puede ver en su portal, en "
                        "\"Prospectos asignados por Administración\"."
                    )
                    st.rerun()

    st.divider()
    st.subheader("Panel general de todas las cotizaciones")

    if sheets_backup.configurado():
        col_sync1, col_sync2 = st.columns([3, 1])
        col_sync1.success(
            "✅ Respaldo automático a Google Sheets activado: cada cotización "
            "nueva o cambio de estatus se sincroniza solo."
        )
        if col_sync2.button("🔄 Sincronizar ahora"):
            resultado_sync = sheets_backup.respaldar(db.listar())
            if resultado_sync.get("modo") == "sincronizado":
                st.success(f"Sincronizado: {resultado_sync['filas']} cotizaciones en Google Sheets.")
            else:
                st.error(f"No se pudo sincronizar: {resultado_sync.get('error')}")
    else:
        st.warning(
            "⚠️ Si esta app está desplegada en Streamlit Community Cloud, el "
            "almacenamiento **no está garantizado como permanente**: la "
            "plataforma puede borrar los archivos locales (la base de datos y "
            "los PDFs) en cualquier reinicio. Descarga un respaldo seguido, "
            "sobre todo después de registrar contrataciones o emisiones "
            "importantes, o configura el respaldo automático a Google Sheets "
            "(ver README) para no depender de acordarte."
        )

    todas = db.listar()
    if todas:
        import pandas as pd
        import io

        df = pd.DataFrame(todas)
        columnas_mostrar = [c for c in [
            "id", "fecha_creacion", "cliente_nombre", "tipo_cliente", "paquete",
            "tipo_paquete", "prima_total", "suma_deseada", "forma_pago", "rfc",
            "estatus", "asesor_asignado",
        ] if c in df.columns]
        df_mostrar = df[columnas_mostrar].copy()
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
