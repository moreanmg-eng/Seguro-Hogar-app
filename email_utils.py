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

import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime

from config import get_secret

BASE_DIR = Path(__file__).parent
SIMULADOS_DIR = BASE_DIR / "correos_simulados"
SIMULADOS_DIR.mkdir(exist_ok=True)

SMTP_HOST = get_secret("SMTP_HOST")
SMTP_PORT = int(get_secret("SMTP_PORT", "587"))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")
FROM_EMAIL = get_secret("FROM_EMAIL", SMTP_USER)
ADMIN_EMAIL = get_secret("ADMIN_EMAIL", "morean.mg@gmail.com")

MODO_SIMULADO = not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD])


def enviar_correo(destinatario: str, asunto: str, cuerpo: str, adjuntos: list[str] | None = None):
    """
    Envía un correo. Si no hay credenciales SMTP configuradas, lo
    simula guardándolo como .txt en correos_simulados/ y no falla.
    """
    adjuntos = adjuntos or []

    if MODO_SIMULADO:
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = SIMULADOS_DIR / f"{marca}_{destinatario.replace('@', '_at_')}.txt"
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"Para: {destinatario}\nAsunto: {asunto}\n\n{cuerpo}\n")
            if adjuntos:
                f.write(f"\nAdjuntos (rutas locales): {adjuntos}\n")
        return {"modo": "simulado", "ruta": str(ruta)}

    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    for ruta_adjunto in adjuntos:
        p = Path(ruta_adjunto)
        if p.exists():
            with open(p, "rb") as f:
                msg.add_attachment(
                    f.read(), maintype="application", subtype="pdf", filename=p.name
                )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)

    return {"modo": "enviado", "destinatario": destinatario}


# ---------------------------------------------------------------------
# Notificaciones específicas del flujo de negocio
# ---------------------------------------------------------------------

def notificar_asesor_nuevo_interesado(cotizacion: dict, correo_asesor: str):
    asunto = f"Nuevo prospecto interesado en contratar — Folio {cotizacion['id']:05d}"
    cuerpo = (
        f"Hola,\n\nEl cliente {cotizacion['cliente_nombre']} indicó que quiere "
        f"contratar el seguro de hogar que cotizó.\n\n"
        f"Folio: {cotizacion['id']:05d}\n"
        f"Paquete: {cotizacion['paquete']}\n"
        f"Prima total anual: ${cotizacion['prima_total_anual']:,.2f} MXN\n"
        f"Código postal: {cotizacion['codigo_postal']}\n\n"
        f"Datos de contacto del cliente:\n"
        f"  Correo: {cotizacion['cliente_correo']}\n"
        f"  Teléfono: {cotizacion['cliente_telefono']}\n\n"
        f"Por favor da seguimiento para confirmar la contratación. Cuando el "
        f"cliente esté listo, entra al portal (vista Asesor) y confirma la "
        f"emisión para que se le notifique al administrador.\n"
    )
    return enviar_correo(correo_asesor, asunto, cuerpo, adjuntos=[cotizacion.get("pdf_cotizacion_path")] if cotizacion.get("pdf_cotizacion_path") else [])


def notificar_admin_confirmacion_asesor(cotizacion: dict, asesor_nombre: str):
    asunto = f"Listo para emitir — Folio {cotizacion['id']:05d} (confirmó {asesor_nombre})"
    cuerpo = (
        f"Hola,\n\n{asesor_nombre} confirmó que el cliente "
        f"{cotizacion['cliente_nombre']} está listo para que emitas la póliza.\n\n"
        f"Folio: {cotizacion['id']:05d}\n"
        f"Paquete: {cotizacion['paquete']}\n"
        f"Prima total anual: ${cotizacion['prima_total_anual']:,.2f} MXN\n"
        f"Notas del asesor: {cotizacion.get('notas') or '—'}\n\n"
        f"Entra al portal (vista Administrador) para subir el PDF de la "
        f"póliza emitida y notificar automáticamente al asesor.\n"
    )
    return enviar_correo(ADMIN_EMAIL, asunto, cuerpo)


def notificar_asesor_poliza_emitida(cotizacion: dict, correo_asesor: str, ruta_poliza: str):
    asunto = f"Póliza emitida y lista para compartir — Folio {cotizacion['id']:05d}"
    cuerpo = (
        f"Hola,\n\nLa póliza del cliente {cotizacion['cliente_nombre']} ya fue "
        f"emitida. Descárgala del portal (vista Asesor) y compártela con el "
        f"cliente.\n\n"
        f"Folio: {cotizacion['id']:05d}\n"
        f"Paquete: {cotizacion['paquete']}\n"
    )
    return enviar_correo(correo_asesor, asunto, cuerpo, adjuntos=[ruta_poliza])
