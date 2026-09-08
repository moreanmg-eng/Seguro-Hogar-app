"""
Genera el PDF de cotización que se le entrega al cliente potencial.
"""

from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

BASE_DIR = Path(__file__).parent
SALIDA_DIR = BASE_DIR / "pdfs_generados"
SALIDA_DIR.mkdir(exist_ok=True)

ASSETS_DIR = BASE_DIR / "assets"
LOGO_BROKER = ASSETS_DIR / "logo_raspberry.png"      # Raspberry — el broker que cotiza
LOGO_ASEGURADORA = ASSETS_DIR / "logo_zurich.png"      # Zurich — la aseguradora que emite

styles = getSampleStyleSheet()
titulo_style = ParagraphStyle("TituloSeguro", parent=styles["Title"], textColor=colors.HexColor("#1a3d6d"))
subtitulo_style = ParagraphStyle("Subtitulo", parent=styles["Heading2"], textColor=colors.HexColor("#1a3d6d"))

TIPO_PAQUETE_LEGIBLE = {
    "propietario": "Propietario (inmueble + contenidos)",
    "arrendatario": "Arrendatario (solo contenidos)",
    "estandar": "Estándar (solo contenidos, sin fenómenos naturales)",
}


def _logo_encabezado():
    """
    Renglón con el logo del broker (Raspberry, izquierda) y el de la
    aseguradora (Zurich, derecha). Si algún archivo no existe (por
    ejemplo, se borró sin querer de assets/), simplemente se omite ese
    logo sin tronar la generación del PDF.
    """
    from PIL import Image as PILImage

    def _imagen(ruta: Path, alto_cm: float):
        if not ruta.exists():
            return ""
        with PILImage.open(ruta) as im:
            ancho_px, alto_px = im.size
        ancho_cm = alto_cm * (ancho_px / alto_px)
        return Image(str(ruta), width=ancho_cm * cm, height=alto_cm * cm)

    celda_izq = _imagen(LOGO_BROKER, 1.1)
    celda_der = _imagen(LOGO_ASEGURADORA, 1.5)

    t = Table([[celda_izq, celda_der]], colWidths=[8 * cm, 7.5 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def generar_pdf_cotizacion(datos_cliente: dict, cotizacion: dict, cotizacion_id: int) -> str:
    """
    datos_cliente: nombre, nomina, correo, telefono, tipo_cliente,
                   calle, numero_ext, numero_int, colonia,
                   es_para_otro, beneficiario_nombre, beneficiario_relacion
    cotizacion: dict como el que regresa cotizador.calcular_prima()
    Regresa la ruta del PDF generado.
    """
    nombre_archivo = f"cotizacion_{cotizacion_id:05d}.pdf"
    ruta = SALIDA_DIR / nombre_archivo

    doc = SimpleDocTemplate(str(ruta), pagesize=letter,
                             topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    elementos = []

    elementos.append(_logo_encabezado())
    elementos.append(Spacer(1, 0.4 * cm))
    elementos.append(Paragraph("Cotización de Seguro de Hogar", titulo_style))
    elementos.append(Paragraph(
        f"Folio: {cotizacion_id:05d} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Fecha de cotización: {cotizacion['fecha_cotizacion'].strftime('%d/%m/%Y')} "
        f"&nbsp;&nbsp;|&nbsp;&nbsp; Vigente hasta: {cotizacion['fecha_fin_vigencia'].strftime('%d/%m/%Y')}",
        styles["Normal"]
    ))
    elementos.append(Spacer(1, 0.5 * cm))

    # Datos del cliente
    elementos.append(Paragraph("Datos del solicitante", subtitulo_style))
    datos_tabla = [
        ["Nombre", datos_cliente.get("nombre") or "—"],
        ["Nómina / Matrícula", datos_cliente.get("nomina") or "—"],
        ["Correo", datos_cliente.get("correo") or "—"],
        ["Teléfono", datos_cliente.get("telefono") or "—"],
        ["Es", "Propietario" if datos_cliente.get("tipo_cliente") == "propietario" else "Arrendatario"],
        ["Forma de pago deseada", datos_cliente.get("forma_pago") or "—"],
    ]
    if datos_cliente.get("es_para_otro"):
        datos_tabla.append([
            "Beneficio extendido a",
            f"{datos_cliente.get('beneficiario_nombre') or '—'} "
            f"({datos_cliente.get('beneficiario_relacion') or '—'})"
        ])
    direccion = ", ".join(filter(None, [
        datos_cliente.get("calle"),
        f"Ext. {datos_cliente.get('numero_ext')}" if datos_cliente.get("numero_ext") else None,
        f"Int. {datos_cliente.get('numero_int')}" if datos_cliente.get("numero_int") else None,
        datos_cliente.get("colonia"),
        f"CP {cotizacion['codigo_postal']}",
    ]))
    datos_tabla.append(["Dirección del inmueble", direccion or "—"])

    t1 = Table(datos_tabla, colWidths=[5 * cm, 10.5 * cm])
    t1.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a3d6d")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elementos.append(t1)
    elementos.append(Spacer(1, 0.5 * cm))

    # Coberturas del paquete
    tipo_paquete = cotizacion["tipo_paquete"]
    elementos.append(Paragraph(
        f"Paquete cotizado: {cotizacion['paquete']} — {TIPO_PAQUETE_LEGIBLE.get(tipo_paquete, tipo_paquete)}",
        subtitulo_style
    ))
    filas_cobertura = []
    if cotizacion.get("suma_edificio_incendio"):
        filas_cobertura.append(["Incendio todo riesgo — Edificio", f"${cotizacion['suma_edificio_incendio']:,.0f}"])
    filas_cobertura.append(["Incendio todo riesgo — Contenidos", f"${cotizacion['suma_contenidos_incendio']:,.0f}"])
    if cotizacion.get("suma_edificio_remocion_escombros"):
        filas_cobertura.append(["Remoción de escombros — Edificio", f"${cotizacion['suma_edificio_remocion_escombros']:,.0f}"])
    filas_cobertura.append(["Remoción de escombros — Contenidos", f"${cotizacion['suma_contenidos_remocion_escombros']:,.0f}"])
    if cotizacion.get("suma_edificio_gastos_extra"):
        filas_cobertura.append(["Gastos extraordinarios — Edificio", f"${cotizacion['suma_edificio_gastos_extra']:,.0f}"])
    filas_cobertura.append(["Gastos extraordinarios — Contenidos", f"${cotizacion['suma_contenidos_gastos_extra']:,.0f}"])
    filas_cobertura.append(["Rotura accidental de cristales", f"${cotizacion['suma_cristales']:,.0f}"])
    filas_cobertura.append(["Equipo electrónico y electrodoméstico", f"${cotizacion['suma_equipo_electronico']:,.0f}"])
    filas_cobertura.append(["Equipo electrónico móvil y/o portátil", f"${cotizacion['suma_equipo_electronico_movil']:,.0f}"])
    filas_cobertura.append(["Robo de menaje", f"${cotizacion['suma_robo_menaje']:,.0f}"])
    filas_cobertura.append(["Robo de objetos en tránsito", f"${cotizacion['suma_robo_transito']:,.0f}"])
    if cotizacion.get("suma_rc_privada_familiar"):
        filas_cobertura.append(["Responsabilidad civil privada y familiar", f"${cotizacion['suma_rc_privada_familiar']:,.0f}"])
    if cotizacion.get("suma_rc_arrendatario"):
        filas_cobertura.append(["Responsabilidad civil arrendatario", f"${cotizacion['suma_rc_arrendatario']:,.0f}"])
    filas_cobertura.append(["Mascotas", f"${cotizacion['suma_mascotas']:,.0f}"])
    filas_cobertura.append(["Zurich Asistencia", "Amparado"])
    filas_cobertura.append(["Fenómenos hidrometeorológicos", cotizacion["zona_hidro_nombre"]])
    filas_cobertura.append(["Terremoto y/o erupción volcánica", "Incluida" if cotizacion["incluye_terremoto"] else "No incluida"])

    t2 = Table([["Cobertura", "Suma asegurada"]] + filas_cobertura, colWidths=[10 * cm, 5.5 * cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5fa")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.append(t2)
    elementos.append(Spacer(1, 0.5 * cm))

    # Desglose de la prima
    elementos.append(Paragraph("Desglose de la prima", subtitulo_style))
    desglose = [
        ["Concepto", "Monto"],
        ["Prima neta anual base", f"${cotizacion['prima_base_anual']:,.2f}"],
    ]
    if cotizacion["hidro_adder"]:
        desglose.append(["+ Fenómenos hidrometeorológicos", f"${cotizacion['hidro_adder']:,.2f}"])
    if cotizacion["tev_adder"]:
        desglose.append(["+ Terremoto y/o erupción volcánica", f"${cotizacion['tev_adder']:,.2f}"])
    desglose.append(["= Prima neta anual total", f"${cotizacion['prima_anual_total']:,.2f}"])
    desglose.append(["Prima diaria (anual ÷ 365)", f"${cotizacion['prima_diaria']:,.4f}"])
    desglose.append([f"Días de vigencia restantes ({cotizacion['dias_restantes']} días)",
                      f"${cotizacion['prima_neta_prorateada']:,.2f}"])
    desglose.append(["+ IVA (16%)", f"${cotizacion['iva']:,.2f}"])
    desglose.append(["+ Derecho de emisión", f"${cotizacion['derecho_emision']:,.2f}"])

    t3 = Table(desglose, colWidths=[10 * cm, 5.5 * cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.append(t3)
    elementos.append(Spacer(1, 0.4 * cm))

    prima_data = [["Prima total a pagar", f"${cotizacion['prima_total']:,.2f} MXN"]]
    t4 = Table(prima_data, colWidths=[10 * cm, 5.5 * cm])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8b23a")),
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(t4)
    elementos.append(Spacer(1, 0.8 * cm))

    elementos.append(Paragraph(
        "Esta cotización es informativa, no constituye una póliza vigente y está sujeta a "
        "validación final. La prima está prorrateada desde la fecha de cotización hasta el "
        "fin de la vigencia de la póliza de flotilla indicada arriba.",
        styles["Italic"]
    ))

    doc.build(elementos)
    return str(ruta)
