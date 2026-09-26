"""Invoice PDF rendering.

Built with ReportLab's platypus flowables rather than absolute coordinates, so
long invoices paginate correctly and a client with 40 line items does not
overflow off the bottom of page one.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D1D5DB")
POSITIVE = colors.HexColor("#047857")

styles = getSampleStyleSheet()

S_TITLE = ParagraphStyle(
    "title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=20, textColor=ACCENT
)
S_LABEL = ParagraphStyle(
    "label", parent=styles["Normal"], fontName="Helvetica", fontSize=8, textColor=MUTED
)
S_BODY = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, textColor=ACCENT)
S_BODY_RIGHT = ParagraphStyle("bodyright", parent=S_BODY, alignment=TA_RIGHT)
S_TOTAL = ParagraphStyle(
    "total", parent=S_BODY, fontName="Helvetica-Bold", fontSize=11, alignment=TA_RIGHT
)
S_MUTED_RIGHT = ParagraphStyle("mutedright", parent=S_BODY_RIGHT, textColor=MUTED)
S_SECTION = ParagraphStyle(
    "section", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=MUTED
)


def _money(value, currency: str) -> str:
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
    symbol = symbols.get(currency, f"{currency} ")
    return f"{symbol}{float(value):,.2f}"


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 12 * mm, doc.invoice.number)
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def render_invoice_pdf(invoice) -> bytes:
    owner = invoice.owner
    client = invoice.client
    cur = invoice.currency

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Invoice {invoice.number}",
        author=owner.business_name or owner.get_full_name() or owner.username,
    )

    story = []

    # -- header -----------------------------------------------------------
    business = owner.business_name or owner.get_full_name() or owner.username
    story.append(Paragraph(business, S_TITLE))
    contact_bits = [b for b in [owner.email, owner.business_name] if b]
    if contact_bits:
        story.append(Paragraph(" &nbsp;|&nbsp; ".join(contact_bits), S_LABEL))
    story.append(Spacer(1, 6 * mm))

    meta = [
        [Paragraph("INVOICE", S_SECTION), Paragraph("BILL TO", S_SECTION)],
        [
            Paragraph(
                f"<b>{invoice.number}</b><br/>Issued {invoice.issued_on:%d %b %Y}<br/>"
                f"Due {invoice.due_on:%d %b %Y}",
                S_BODY,
            ),
            Paragraph(
                f"<b>{client.name}</b><br/>"
                + (f"{client.company}<br/>" if client.company else "")
                + (f"{client.email}" if client.email else "No email on file"),
                S_BODY,
            ),
        ],
    ]
    meta_tbl = Table(meta, colWidths=[doc.width / 2] * 2)
    meta_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 4 * mm))

    # -- line items -------------------------------------------------------
    header = [
        Paragraph("Description", S_SECTION),
        Paragraph("Qty", ParagraphStyle("h", parent=S_SECTION, alignment=TA_RIGHT)),
        Paragraph("Rate", ParagraphStyle("h2", parent=S_SECTION, alignment=TA_RIGHT)),
        Paragraph("Amount", ParagraphStyle("h3", parent=S_SECTION, alignment=TA_RIGHT)),
    ]
    rows = [header]
    for line in invoice.lines.all():
        rows.append(
            [
                Paragraph(line.description, S_BODY),
                Paragraph(f"{float(line.quantity):g}", S_BODY_RIGHT),
                Paragraph(_money(line.unit_price, cur), S_BODY_RIGHT),
                Paragraph(_money(line.amount, cur), S_BODY_RIGHT),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                Paragraph("No line items on this invoice.", S_MUTED_RIGHT),
                Paragraph("", S_BODY),
                Paragraph("", S_BODY),
                Paragraph("", S_BODY),
            ]
        )

    items = Table(rows, colWidths=[doc.width * 0.52, doc.width * 0.12, doc.width * 0.18, doc.width * 0.18])
    items.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.6 * mm),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(items)
    story.append(Spacer(1, 3 * mm))

    # -- totals -----------------------------------------------------------
    totals = [
        ["Subtotal", _money(invoice.subtotal, cur)],
    ]
    if float(invoice.discount or 0) > 0:
        totals.append(["Discount", f"-{_money(invoice.discount, cur)}"])
    if float(invoice.tax_rate or 0) > 0:
        totals.append([f"Tax ({float(invoice.tax_rate):g}%)", _money(invoice.tax_amount, cur)])
    totals.append(["Total", _money(invoice.total, cur)])
    if float(invoice.amount_paid) > 0:
        totals.append(["Paid", _money(invoice.amount_paid, cur)])
    totals.append(["Balance due", _money(invoice.balance_due, cur)])

    rendered = []
    for idx, (label, value) in enumerate(totals):
        style = S_TOTAL if label in {"Total", "Balance due"} else S_MUTED_RIGHT
        rendered.append([Paragraph(label, style), Paragraph(value, style)])

    totals_tbl = Table(rendered, colWidths=[doc.width * 0.7, doc.width * 0.3], hAlign="RIGHT")
    totals_tbl.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("LINEABOVE", (0, len(totals) - 2), (-1, len(totals) - 2), 0.75, RULE),
            ]
        )
    )
    story.append(totals_tbl)

    if float(invoice.amount_paid or 0) >= float(invoice.total or 0) and float(invoice.total or 0) > 0:
        story.append(Spacer(1, 3 * mm))
        story.append(
            KeepTogether(
                Table(
                    [[Paragraph("PAID IN FULL - thank you.", S_TOTAL)]],
                    colWidths=[doc.width],
                    style=TableStyle(
                        [
                            ("TEXTCOLOR", (0, 0), (-1, -1), POSITIVE),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
                        ]
                    ),
                )
            )
        )

    if invoice.notes:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("NOTES", S_SECTION))
        story.append(Paragraph(invoice.notes.replace("\n", "<br/>"), S_BODY))

    doc.invoice = invoice  # read back by _footer() during build
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
