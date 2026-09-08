"""
Genera el PDF de cotización que se le entrega al cliente potencial.
"""

from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

BASE_DIR = Path(__file__).parent
SALIDA_DIR = BASE_DIR / "pdfs_generados"
SALIDA_DIR.mkdir(exist_ok=True)

styles = getSampleStyleSheet()
titulo_style = ParagraphStyle("TituloSeguro", parent=styles["Title"], textColor=colors.HexColor("#1a3d6d"))
subtitulo_style = ParagraphStyle("Subtitulo", parent=styles["Heading2"], textColor=colors.HexColor("#1a3d6d"))


def _si_no(valor: bool) -> str:
    return "Sí" if valor else "No"


def generar_pdf_cotizacion(cliente_nombre: str, cliente_correo: str,
                            cliente_telefono: str, cotizacion: dict,
                            cotizacion_id: int) -> str:
    """
    cotizacion: dict como el que regresa cotizador.calcular_prima()
    Regresa la ruta del PDF generado.
    """
    nombre_archivo = f"cotizacion_{cotizacion_id:05d}.pdf"
    ruta = SALIDA_DIR / nombre_archivo

    doc = SimpleDocTemplate(str(ruta), pagesize=letter,
                             topMargin=2 * cm, bottomMargin=2 * cm)
    elementos = []

    elementos.append(Paragraph("Cotización de Seguro de Hogar", titulo_style))
    elementos.append(Paragraph(
        f"Folio: {cotizacion_id:05d} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Fecha: {datetime.now().strftime('%d/%m/%Y')}",
        styles["Normal"]
    ))
    elementos.append(Spacer(1, 0.6 * cm))

    # Datos del cliente
    elementos.append(Paragraph("Datos del cliente", subtitulo_style))
    datos_cliente = [
        ["Nombre", cliente_nombre],
        ["Correo", cliente_correo],
        ["Teléfono", cliente_telefono or "—"],
        ["Código postal", cotizacion["codigo_postal"]],
        ["Ubicación", f"{cotizacion['municipio']}, {cotizacion['estado']}"],
    ]
    t1 = Table(datos_cliente, colWidths=[5 * cm, 10 * cm])
    t1.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a3d6d")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    elementos.append(t1)
    elementos.append(Spacer(1, 0.6 * cm))

    # Detalle del paquete
    elementos.append(Paragraph(f"Paquete cotizado: {cotizacion['paquete']}", subtitulo_style))
    datos_paquete = [
        ["Concepto", "Detalle"],
        ["Suma asegurada (contenidos)", f"${cotizacion['suma_asegurada_contenidos']:,.0f}"],
        ["Suma asegurada (resp. civil)", f"${cotizacion['suma_asegurada_rc']:,.0f}"],
        ["Cobertura incendio", _si_no(cotizacion["cobertura_incendio"])],
        ["Cobertura robo", _si_no(cotizacion["cobertura_robo"])],
        ["Cobertura cristales", _si_no(cotizacion["cobertura_cristales"])],
        ["Cobertura responsabilidad civil", _si_no(cotizacion["cobertura_responsabilidad_civil"])],
        ["Deducible", f"{cotizacion['deducible_pct']}%"],
        ["Zona de riesgo (CP)", cotizacion["zona_riesgo"]],
    ]
    t2 = Table(datos_paquete, colWidths=[9 * cm, 6 * cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5fa")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(t2)
    elementos.append(Spacer(1, 0.8 * cm))

    # Prima total
    prima_data = [["Prima total anual", f"${cotizacion['prima_total_anual']:,.2f} MXN"]]
    t3 = Table(prima_data, colWidths=[9 * cm, 6 * cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8b23a")),
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(t3)
    elementos.append(Spacer(1, 1 * cm))

    elementos.append(Paragraph(
        "Esta cotización es informativa, no constituye una póliza vigente y "
        "está sujeta a validación final. Vigencia de la cotización: 15 días.",
        styles["Italic"]
    ))

    doc.build(elementos)
    return str(ruta)
