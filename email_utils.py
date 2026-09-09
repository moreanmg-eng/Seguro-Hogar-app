"""
Envío de correos vía SMTP. Configuración en .env (ver .env.example):

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=tu_correo@gmail.com
    SMTP_PASSWORD=xxxxxxxxxxxxxxxx   <- contraseña de aplicación, no tu password normal
    FROM_EMAIL=tu_correo@gmail.com
    ADMIN_EMAIL=morean.mg@gmail.com

Si usas Gmail necesitas generar una "Contraseña de aplicación" en tu
cuenta de Google (con la verificación en 2 pasos activada) — la
contraseña normal de tu correo NO va a funcionar con smtplib.

Mientras no configures estas variables, la app sigue funcionando: los
correos simplemente se "simulan" (se muestran en pantalla y se guardan
en la carpeta correos_simulados/) en vez de enviarse de verdad, para
que puedas probar todo el flujo sin credenciales reales.
"""

import html
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime
from string import Template
from urllib.parse import quote

from config import get_secret

BASE_DIR = Path(__file__).parent
SIMULADOS_DIR = BASE_DIR / "correos_simulados"
SIMULADOS_DIR.mkdir(exist_ok=True)

PLANTILLAS_DIR = BASE_DIR / "assets" / "plantillas_correo"

# Infográficos que siempre se adjuntan al correo de entrega de póliza,
# junto con el PDF de la póliza misma.
ADJUNTOS_ENTREGA_POLIZA = [
    BASE_DIR / "assets" / "cuponera_asistencias_hogar.pdf",
    BASE_DIR / "assets" / "guia_asegurado_hogar.pdf",
]

# Logo que se inserta debajo de la firma "Raspberry | Hogar" en todos
# los correos automáticos (nada más para verse más profesional; si no
# existe el archivo, el correo se manda igual, solo sin logo).
LOGO_RASPBERRY_PATH = BASE_DIR / "assets" / "logo_raspberry.png"
LOGO_CID = "logo_raspberry"


def _cuerpo_a_html(cuerpo: str) -> str:
    """
    Convierte el cuerpo de texto plano de la plantilla a un HTML
    simple (mismos saltos de línea/párrafos), e inserta el logo justo
    debajo de la línea de firma "Raspberry | Hogar", si esa línea
    existe en el correo.
    """
    parrafos = cuerpo.strip("\n").split("\n\n")
    html_parrafos = [
        "<p style='margin:0 0 1em 0;'>" + html.escape(p).replace("\n", "<br>") + "</p>"
        for p in parrafos
    ]

    firma_html = "<p style='margin:0 0 1em 0;'>" + html.escape("Raspberry | Hogar") + "</p>"
    logo_html = (
        f"<p style='margin:0 0 1em 0;'><img src='cid:{LOGO_CID}' alt='Raspberry' "
        "style='max-width:160px;height:auto;'></p>"
    )
    if firma_html in html_parrafos:
        idx = html_parrafos.index(firma_html)
        html_parrafos.insert(idx + 1, logo_html)

    cuerpo_html = "".join(html_parrafos)
    return (
        "<div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;"
        f"color:#222;'>{cuerpo_html}</div>"
    )

SMTP_HOST = get_secret("SMTP_HOST")
SMTP_PORT = int(get_secret("SMTP_PORT", "587"))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")
FROM_EMAIL = get_secret("FROM_EMAIL", SMTP_USER)
ADMIN_EMAIL = get_secret("ADMIN_EMAIL", "morean.mg@gmail.com")

MODO_SIMULADO = not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])


def enviar_correo(destinatario: str, asunto: str, cuerpo: str, adjuntos: list[str] | None = None,
                   copia_a: str | None = None):
    """
    Envía un correo. Si no hay credenciales SMTP configuradas, lo
    simula guardándolo como .txt en correos_simulados/ y no falla.

    copia_a: correo opcional que recibe copia (CC) del mismo mensaje —
    por ejemplo, mandarle al asesor una copia de lo que se le envió al
    cliente, como respaldo de que se entregó.
    """
    adjuntos = adjuntos or []

    if MODO_SIMULADO:
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = SIMULADOS_DIR / f"{marca}_{destinatario.replace('@', '_at_')}.txt"
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"Para: {destinatario}\n")
            if copia_a:
                f.write(f"Cc: {copia_a}\n")
            f.write(f"Asunto: {asunto}\n\n{cuerpo}\n")
            if adjuntos:
                f.write(f"\nAdjuntos (rutas locales): {adjuntos}\n")
        return {"modo": "simulado", "ruta": str(ruta)}

    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = destinatario
    if copia_a:
        msg["Cc"] = copia_a
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    if LOGO_RASPBERRY_PATH.exists():
        msg.add_alternative(_cuerpo_a_html(cuerpo), subtype="html")
        msg.get_payload()[1].add_related(
            LOGO_RASPBERRY_PATH.read_bytes(), maintype="image", subtype="png", cid=LOGO_CID,
        )

    for ruta_adjunto in adjuntos:
        p = Path(ruta_adjunto)
        if p.exists():
            with open(p, "rb") as f:
                msg.add_attachment(
                    f.read(), maintype="application", subtype="pdf", filename=p.name
                )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return {"modo": "enviado", "destinatario": destinatario}
    except Exception as e:
        # No se pudo enviar de verdad (credenciales inválidas, servidor
        # incorrecto, etc.). En vez de tronar toda la app, guardamos el
        # correo como respaldo simulado y devolvemos el error para que
        # la interfaz pueda avisarle a la persona qué revisar.
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = SIMULADOS_DIR / f"FALLO_{marca}_{destinatario.replace('@', '_at_')}.txt"
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(
                f"⚠️ No se pudo enviar este correo de verdad. Revisa tu "
                f"configuración de correo (SMTP_HOST/PORT/USER/PASSWORD).\n"
                f"Error: {e}\n\nPara: {destinatario}\nAsunto: {asunto}\n\n{cuerpo}\n"
            )
        return {"modo": "error", "error": str(e), "ruta": str(ruta)}


def _cargar_plantilla(nombre_archivo: str, **valores) -> tuple[str, str]:
    """
    Lee una plantilla de correo editable desde
    assets/plantillas_correo/<nombre_archivo> y le rellena los
    marcadores tipo $nombre_variable con los valores que le pases.

    Para editar la redacción de cualquier correo automático, edita
    directamente el archivo de texto correspondiente (por ejemplo
    desde GitHub, con el ícono de lápiz) — no hace falta tocar nada de
    código. La primera línea del archivo debe empezar con "Asunto: " y
    el resto (después de una línea en blanco) es el cuerpo del correo.
    Si te falta algún marcador o le pones uno que no existe, no truena
    — simplemente se queda tal cual escrito.
    """
    contenido = (PLANTILLAS_DIR / nombre_archivo).read_text(encoding="utf-8")
    primera_linea, _, resto = contenido.partition("\n")
    asunto_crudo = primera_linea.removeprefix("Asunto:").strip()
    cuerpo_crudo = resto.lstrip("\n")
    asunto = Template(asunto_crudo).safe_substitute(**valores)
    cuerpo = Template(cuerpo_crudo).safe_substitute(**valores)
    return asunto, cuerpo


# ---------------------------------------------------------------------
# Notificaciones específicas del flujo de negocio
# ---------------------------------------------------------------------

_NOMBRE_TIPO_PAQUETE = {
    "propietario": "Propietario",
    "arrendatario": "Arrendatario",
    "estandar": "Solo Contenidos",
}


def notificar_asesor_nuevo_interesado(cotizacion: dict, correo_asesor: str, asesor_nombre: str = ""):
    """Se dispara cuando el cliente elige 'Quiero que un asesor me
    contacte para más información' — le llega solo al asesor, con la
    cotización en PDF adjunta."""
    asunto, cuerpo = _cargar_plantilla(
        "nuevo_interesado.txt",
        asesor_nombre=asesor_nombre or "asesor",
        cliente_nombre=cotizacion["cliente_nombre"],
        motivo=cotizacion.get("notas_cliente") or "—",
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        paquete=cotizacion.get("paquete") or "—",
        tipo_paquete=cotizacion.get("tipo_paquete") or "—",
        prima_total=f"${cotizacion['prima_total']:,.2f} MXN" if cotizacion.get("prima_total") else "—",
        codigo_postal=cotizacion["codigo_postal"],
        forma_pago=cotizacion.get("forma_pago") or "—",
        rfc=cotizacion.get("rfc") or "— (no lo dejó, pídeselo antes de que se emita)",
        cliente_correo=cotizacion["cliente_correo"],
        cliente_telefono=cotizacion["cliente_telefono"],
    )
    return enviar_correo(correo_asesor, asunto, cuerpo, adjuntos=[cotizacion.get("pdf_cotizacion_path")] if cotizacion.get("pdf_cotizacion_path") else [])


def notificar_cliente_confirmacion_contratacion(cotizacion: dict, correo_asesor: str | None = None):
    """Se dispara cuando el cliente elige 'Sí, quiero contratar' — le
    llega al propio cliente confirmando que se recibió su solicitud,
    con copia (CC) al asesor asignado para que también quede
    enterado."""
    asunto, cuerpo = _cargar_plantilla(
        "confirmacion_contratacion_cliente.txt",
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
    )
    return enviar_correo(
        cotizacion["cliente_correo"], asunto, cuerpo, copia_a=correo_asesor,
    )


def notificar_admin_confirmacion_asesor(cotizacion: dict, asesor_nombre: str):
    asunto, cuerpo = _cargar_plantilla(
        "confirmacion_asesor.txt",
        asesor_nombre=asesor_nombre,
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        paquete=cotizacion["paquete"],
        tipo_paquete=cotizacion["tipo_paquete"],
        prima_total=f"${cotizacion['prima_total']:,.2f} MXN",
        forma_pago=cotizacion.get("forma_pago") or "—",
        rfc=cotizacion.get("rfc") or "⚠️ no lo dejó — pídeselo antes de emitir",
        notas=cotizacion.get("notas") or "—",
    )
    return enviar_correo(ADMIN_EMAIL, asunto, cuerpo)


def notificar_asesor_poliza_emitida(cotizacion: dict, correo_asesor: str, ruta_poliza: str):
    asunto, cuerpo = _cargar_plantilla(
        "poliza_emitida.txt",
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        paquete=cotizacion["paquete"],
    )
    return enviar_correo(correo_asesor, asunto, cuerpo, adjuntos=[ruta_poliza])


LIGA_PAGO_BASE = "https://rby-apim-produccion.azure-api.net/insurance/home/payment/Zurich/r/{numero_poliza}"


def _construir_info_pago(cotizacion: dict) -> str:
    """
    Arma el texto de la sección de pago del correo de entrega de
    póliza, según la forma de pago que eligió el cliente:

      - Domiciliado mensual / Contado: liga única para registrar sus
        datos bancarios, construida con el número de póliza (nombre
        del PDF subido), su nómina/matrícula (sin el prefijo L0/A0) y
        su correo.
      - Nómina: el monto que se le descontará quincenalmente,
        capturado por el administrador al subir la póliza.

    Si falta algún dato necesario (por ejemplo, el administrador
    todavía no sube la póliza con su número, o no capturó el monto de
    nómina), regresa un texto genérico en vez de tronar o mandar una
    liga rota.
    """
    forma_pago = (cotizacion.get("forma_pago") or "").strip()
    generico = (
        "Un asesor se pondrá en contacto contigo con las instrucciones "
        "de pago correspondientes a tu forma de pago."
    )

    if forma_pago == "Nómina":
        monto = cotizacion.get("monto_descuento_nomina")
        if not monto:
            return generico
        return f"Se te estará descontando ${float(monto):,.2f} MXN quincenalmente vía nómina."

    if forma_pago in ("Domiciliado mensual", "Contado"):
        numero_poliza = cotizacion.get("numero_poliza")
        correo = cotizacion.get("cliente_correo")
        nomina = (cotizacion.get("nomina") or "").strip()
        if nomina[:2].upper() in ("L0", "A0"):
            nomina = nomina[2:]
        if not (numero_poliza and correo):
            return generico
        liga = (
            LIGA_PAGO_BASE.format(numero_poliza=quote(str(numero_poliza), safe=""))
            + f"?nomina={quote(nomina, safe='')}&correo={quote(correo, safe='@.')}"
        )
        return f"Para registrar tus datos bancarios, ingresa a la siguiente liga: {liga}"

    return generico


def notificar_cliente_poliza_entregada(cotizacion: dict, ruta_poliza: str, asesor_nombre: str,
                                        correo_asesor: str | None = None):
    """
    Se dispara cuando el asesor da clic en "Marcar como entregada al
    cliente": le manda al cliente su póliza en PDF, junto con la
    cuponera de asistencias y la guía del asegurado, y le manda una
    copia (CC) al propio asesor como respaldo de que ya se la
    entregó.

    El cuerpo del correo vive en
    assets/plantillas_correo/poliza_entregada_cliente.txt — edítalo
    cuando quieras cambiar la redacción, no hace falta tocar código.

    $info_pago se calcula automáticamente según la forma de pago del
    cliente -- ver _construir_info_pago().
    """
    info_pago = _construir_info_pago(cotizacion)

    asunto, cuerpo = _cargar_plantilla(
        "poliza_entregada_cliente.txt",
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        paquete=cotizacion.get("paquete") or "—",
        asesor_nombre=asesor_nombre,
        info_pago=info_pago,
    )
    adjuntos = [ruta_poliza] + [str(p) for p in ADJUNTOS_ENTREGA_POLIZA if p.exists()]
    return enviar_correo(
        cotizacion["cliente_correo"], asunto, cuerpo,
        adjuntos=adjuntos, copia_a=correo_asesor,
    )


def notificar_cliente_cotizacion(cotizacion: dict, ruta_pdf: str | None):
    """Envía al propio cliente el PDF de su cotización recién generada,
    de forma automática, en cuanto la calcula (sin que tenga que
    pedirlo). No aplica a solicitudes manuales, que no tienen PDF."""
    tipo_legible = _NOMBRE_TIPO_PAQUETE.get(cotizacion.get("tipo_paquete"), cotizacion.get("tipo_paquete") or "—")
    asunto, cuerpo = _cargar_plantilla(
        "cotizacion_cliente.txt",
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        paquete=cotizacion.get("paquete"),
        tipo_paquete=tipo_legible,
        prima_total=f"${cotizacion['prima_total']:,.2f} MXN",
        dias_restantes=cotizacion.get("dias_restantes"),
    )
    return enviar_correo(
        cotizacion["cliente_correo"], asunto, cuerpo,
        adjuntos=[ruta_pdf] if ruta_pdf else [],
    )


def notificar_solicitud_manual(cotizacion: dict):
    """El cliente pidió una suma asegurada mayor a los paquetes: no hay
    prima automática, se le avisa al administrador para que un asesor
    lo cotice manualmente."""
    asunto, cuerpo = _cargar_plantilla(
        "solicitud_manual.txt",
        cliente_nombre=cotizacion["cliente_nombre"],
        folio=cotizacion.get("folio") or f"{cotizacion['id']:05d}",
        suma_deseada=f"${cotizacion['suma_deseada']:,.2f}",
        tipo_cliente="Propietario" if cotizacion["tipo_cliente"] == "propietario" else "Arrendatario",
        codigo_postal=cotizacion["codigo_postal"],
        nomina=cotizacion.get("nomina") or "—",
        cliente_correo=cotizacion["cliente_correo"],
        cliente_telefono=cotizacion["cliente_telefono"],
    )
    return enviar_correo(ADMIN_EMAIL, asunto, cuerpo)
