"""PDF da proposta comercial, no visual do modelo atual da LM (`Proposta Comercial .pdf`).

Páginas: capa (nome do cliente e data), missão, referências, página do evento (itens por bloco,
incluso e não incluso, pagamento, validade e cancelamento; continua em mais páginas se precisar)
e contato. Missão, referências e contato são as páginas do modelo atual, guardadas como imagem em
`sales/pdf_assets/`; para trocar, substitua os arquivos mantendo os nomes. Capa e página do evento usam
`fundo_capa.jpg` e `fundo_preco.jpg` (luz quente da referência do Canva). As fotos de referências mudam
com o tipo de proposta (`referencias_<tipo>.jpg`, ver REFERENCE_ASSETS); sem o arquivo do tipo, vale
`referencias.jpg`.

Valores dos itens: só aparecem com `inputs.show_item_prices` (desligado por padrão). Ligado, cada item
sai com quantidade, preço unitário e subtotal (o preço editado na proposta, se houver), e o quadro
de valores mostra itens, serviços, nota e ajustes antes do total.

`build_pdf_context` é pura (testável sem banco) e `render_pdf` desenha com ReportLab, que não
depende de bibliotecas nativas (WeasyPrint exigiria GTK/Pango na imagem de deploy).
"""
from collections import OrderedDict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

from sales.formatting import format_brl

ASSETS = Path(__file__).resolve().parent.parent / "pdf_assets"
PAGE = (540, 960)  # 9:16, como o modelo atual
COPPER = HexColor("#D4935A")
COPPER_DARK = HexColor("#C98340")
TEXT = white
MUTED = Color(1, 1, 1, alpha=0.72)

MODE_TITLES = {
    "porta": "Locação de estrutura",
    "corporativo": "Evento corporativo",
    "social": "Evento social",
    "produto_unico": "Locação de equipamento",
}

# Fotos da página de referências por modo da proposta
REFERENCE_ASSETS = {
    "corporativo": "referencias_corporativo.jpg",
    "social": "referencias_social.jpg",
    "porta": "referencias_estrutura.jpg",
    "produto_unico": "referencias_produto.jpg",
}


def asset(name: str, fallback: str) -> str:
    """Caminho do asset, ou do fallback quando o arquivo ainda não foi colocado em pdf_assets/."""
    path = ASSETS / name
    return str(path if path.exists() else ASSETS / fallback)


BLOCK_ORDER = OrderedDict([
    ("estrutura", "Estrutura"),
    ("palco", "Palco e praticáveis"),
    ("som", "Som"),
    ("iluminacao", "Iluminação"),
    ("video", "Vídeo"),
    ("outros", "Outros itens"),
])

# Custos operacionais que aparecem como serviço da equipe
TEAM_COSTS = OrderedDict([
    ("montagem", "Montagem"),
    ("desmontagem", "Desmontagem"),
    ("adicional_noturno", "Desmontagem na mesma noite"),
    ("tecnico_som", "Técnico de som"),
    ("tecnico_banda", "Técnico de banda"),
    ("tecnico_luz", "Técnico de luz"),
    ("dj", "DJ"),
])

NUMBER_WORDS = {1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito",
                9: "nove", 10: "dez", 15: "quinze", 30: "trinta"}

MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro")


def _day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        text = value[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _fmt_day(value) -> str:
    day = _day(value)
    return day.strftime("%d/%m/%Y") if day else "a definir"


def _long_day(value) -> str:
    day = _day(value)
    return f"{day.day:02d} de {MONTHS[day.month - 1]} de {day.year}" if day else ""


def _qty(value, unit: str) -> str:
    number = float(value or 0)
    text = f"{int(number):02d}" if number.is_integer() else f"{number:g}".replace(".", ",")
    if unit in ("m²", "metro"):
        return f"{text} {'m²' if unit == 'm²' else 'm'}"
    return text


def _validity_text(days: int, valid_until) -> str:
    words = NUMBER_WORDS.get(days)
    span = f"{days:02d} ({words}) dias" if words else f"{days} dias"
    until = f", até {_fmt_day(valid_until)}" if valid_until else ""
    return f"Esta proposta tem validade de {span}{until}."


def build_pdf_context(proposal: dict, customer: dict, settings: dict, valid_until=None,
                      issued_at: datetime | None = None) -> dict:
    """Dados da proposta já formatados para o PDF (sem banco: recebe dicionários)."""
    issued_at = issued_at or datetime.utcnow()
    inputs = proposal.get("inputs") or {}
    qualification = customer.get("qualification") or {}
    mode = proposal.get("mode")
    lines = proposal.get("lines") or []
    costs = proposal.get("costs") or []
    codes = {line.get("code") for line in lines}
    cost_codes = {c.get("code") for c in costs}

    show_prices = bool(inputs.get("show_item_prices"))
    periods = int(proposal.get("periods") or 1)

    # Itens por bloco; peças de um kit (gol, grid) aparecem como a estrutura montada
    blocks: "OrderedDict[str, OrderedDict]" = OrderedDict((key, OrderedDict()) for key in BLOCK_ORDER)
    for line in lines:
        block = line.get("block") if line.get("block") in blocks else "outros"
        subtotal = float(line.get("subtotal") or 0)
        if line.get("kit"):
            kit = blocks[block].setdefault(f"kit:{line['kit']}", {"qty": 1, "unit": "unidade", "name": line["kit"],
                                                                  "subtotal": 0.0, "unit_price": None})
            kit["subtotal"] += subtotal
            continue
        key = line.get("code")
        entry = blocks[block].setdefault(key, {"qty": 0, "unit": line.get("unit") or "unidade", "name": line.get("name"),
                                               "subtotal": 0.0, "unit_price": line.get("unit_price")})
        entry["qty"] += float(line.get("qty") or 0)
        entry["subtotal"] += subtotal

    def item_text(v: dict) -> str:
        text = f"{_qty(v['qty'], v['unit'])} {v['name']}"
        if not show_prices:
            return text
        unit_price = v["unit_price"] if v["unit_price"] is not None else v["subtotal"]
        if float(v["qty"]) == 1 and periods == 1:
            return f"{text}: {format_brl(v['subtotal'])}"
        weeks = f" x {periods} semanas" if periods > 1 else ""
        return f"{text}: {format_brl(unit_price)} cada{weeks} = {format_brl(v['subtotal'])}"

    block_list = [
        {"title": BLOCK_ORDER[key], "items": [item_text(v) for v in items.values()]}
        for key, items in blocks.items() if items
    ]

    team = []
    if {"montagem", "desmontagem"} <= cost_codes:
        team.append("Montagem e desmontagem")
    for code, label in TEAM_COSTS.items():
        if code in cost_codes and not (code in ("montagem", "desmontagem") and "Montagem e desmontagem" in team):
            team.append(label)
    for cost in costs:
        if cost.get("code") == "mao_de_obra_avulsa":
            team.append(cost.get("name") or "Montagem")
    if team:
        block_list.append({"title": "Equipe", "items": team})

    included = []
    if cost_codes & {"carga", "descarga", "frete"}:
        included.append("Transporte, carga e descarga em Goiânia")
    if "entrega_praticavel" in cost_codes:
        included.append("Entrega e retirada no local")
    if "frete_manual" in cost_codes:
        included.append("Deslocamento até o local do evento")
    if "alimentacao" in cost_codes:
        included.append("Alimentação da equipe")
    if "video_led_social" in codes:
        included.append("Técnico do painel de LED")
    if "projeto" in cost_codes:
        included.append("Projeto")
    if "palco_forrado" in codes:
        included.append("Forração do palco")
    if proposal.get("with_invoice"):
        included.append("Nota fiscal")

    not_included = []
    if mode == "porta":
        not_included += ["Montagem e desmontagem", "Transporte: retirada e devolução pelo cliente na LM"]
    elif mode == "produto_unico" and inputs.get("delivery") != "entrega":
        not_included.append("Transporte: retirada e devolução pelo cliente na LM")
    if mode == "produto_unico" and not inputs.get("assembly"):
        not_included.append("Montagem")
    if mode != "produto_unico" and "palco_forrado" not in codes:
        not_included.append("Forração")
    if "projeto" not in cost_codes and mode != "produto_unico":
        not_included.append("Projeto")
    if "frete_manual" not in cost_codes:
        not_included.append("Deslocamento fora de Goiânia")
    if not proposal.get("with_invoice") and mode in ("corporativo", "social"):
        not_included.append("Nota fiscal")

    if mode == "porta":
        header = [f"Retirada: {_fmt_day(inputs.get('pickup_date') or proposal.get('period_start'))}",
                  f"Devolução: {_fmt_day(inputs.get('return_date'))}",
                  "Retirada e devolução na LM"]
    elif mode == "produto_unico":
        header = [f"Data de uso: {_fmt_day(inputs.get('event_date') or proposal.get('period_start'))}",
                  "Entrega no local" if inputs.get("delivery") == "entrega" else "Retirada na LM"]
        if inputs.get("end_date"):
            header.insert(1, f"Devolução: {_fmt_day(inputs.get('end_date'))}")
    else:
        event_day = inputs.get("event_date") or customer.get("event_date") or proposal.get("period_start")
        header = [f"Data do evento: {_fmt_day(event_day)}",
                  f"Local: {customer.get('venue') or qualification.get('local') or 'a definir'}",
                  f"Horário: {qualification.get('horario') or qualification.get('horario_evento') or 'a definir'}"]
        if inputs.get("guests"):
            header.append(f"Público: {int(inputs['guests'])} pessoas")

    price_summary = []
    if show_prices:
        price_summary.append(f"Itens: {format_brl(proposal.get('items_total') or 0)}")
        if proposal.get("costs_total"):
            price_summary.append(f"Serviços e operação: {format_brl(proposal['costs_total'])}")
        margin_value = (proposal.get("items_total") or 0) + (proposal.get("costs_total") or 0)
        if proposal.get("margin_pct"):
            price_summary.append(f"Margem: {format_brl(margin_value * proposal['margin_pct'])}")
        if proposal.get("invoice_value"):
            price_summary.append(f"Nota fiscal: {format_brl(proposal['invoice_value'])}")
        if proposal.get("discount"):
            price_summary.append(f"Desconto: -{format_brl(proposal['discount'])}")
        if proposal.get("manual_adjustment"):
            adjustment = proposal["manual_adjustment"]
            price_summary.append(f"Ajuste: {'-' if adjustment < 0 else '+'}{format_brl(abs(adjustment))}")

    validity_days = int(settings.get("proposal_validity_days") or 5)
    payment = [settings.get("payment_terms_text") or "Forma de pagamento a combinar.",
               settings.get("down_payment_text") or "Sinal a combinar."]
    return {
        "client_name": customer.get("name") or customer.get("company") or "Cliente",
        "company": customer.get("company") if customer.get("name") else None,
        "issued_at": _long_day(issued_at),
        "version": proposal.get("version") or 1,
        "title": MODE_TITLES.get(mode, "Proposta"),
        "mode": mode,
        "header": header,
        "blocks": block_list,
        "included": included,
        "not_included": not_included,
        "payment": [p for p in payment if p],
        "total": format_brl(proposal.get("total")),
        "price_summary": price_summary,
        "invoice_note": None if proposal.get("with_invoice") or mode not in ("corporativo", "social")
        else "Valor sem nota fiscal.",
        "validity": _validity_text(validity_days, valid_until),
        "cancellation": settings.get("cancellation_text") or "Condições de cancelamento a combinar.",
    }


# --- Desenho -----------------------------------------------------------------------------

def _style(name, size, color=TEXT, leading=None, font="Helvetica", space_after=0):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading or size * 1.3, textColor=color,
                          alignment=TA_CENTER, spaceAfter=space_after)


STYLES = {
    "header": _style("header", 15, leading=20),
    "block": _style("block", 15, COPPER, leading=19, space_after=3),
    "item": _style("item", 11.5, leading=15),
    "small": _style("small", 10, MUTED, leading=13),
    "pill": _style("pill", 12, white, leading=15),
    "total": _style("total", 21, leading=26, font="Helvetica-Bold"),
}


class PaymentBox(Flowable):
    """Quadro final: forma de pagamento (faixa cobre), valor total, validade e cancelamento."""

    def __init__(self, context: dict, width: float):
        super().__init__()
        self.context = context
        self.box_width = width
        self.parts = (
            [Paragraph(escape(p), STYLES["pill"]) for p in context["payment"]],
            [Paragraph(escape(t), STYLES["item"]) for t in context.get("price_summary") or []],
            Paragraph(f"VALOR TOTAL: {escape(context['total'])}", STYLES["total"]),
            [Paragraph(escape(t), STYLES["small"]) for t in
             filter(None, [context.get("invoice_note"), context["validity"], context["cancellation"]])],
        )

    def wrap(self, avail_width, avail_height):
        inner = self.box_width - 36
        pills, summary, total, notes = self.parts
        self._pill_h = sum(p.wrap(inner - 24, 1000)[1] for p in pills) + 16
        self._summary_h = sum(p.wrap(inner, 1000)[1] for p in summary) + (6 if summary else 0)
        self._total_h = total.wrap(inner, 1000)[1]
        self._notes_h = sum(p.wrap(inner, 1000)[1] + 3 for p in notes)
        self.height = 16 + self._pill_h + 10 + self._summary_h + self._total_h + 8 + self._notes_h + 14
        return self.box_width, self.height

    def draw(self):
        c = self.canv
        pills, summary, total, notes = self.parts
        c.setStrokeColor(COPPER)
        c.setLineWidth(1.2)
        c.roundRect(0, 0, self.box_width, self.height, 18, stroke=1, fill=0)
        y = self.height - 16
        c.setFillColor(COPPER_DARK)
        c.roundRect(18, y - self._pill_h, self.box_width - 36, self._pill_h, self._pill_h / 2 if self._pill_h < 40 else 14,
                    stroke=0, fill=1)
        py = y - 8
        for p in pills:
            _, h = p.wrap(self.box_width - 60, 1000)
            p.drawOn(c, 30, py - h)
            py -= h
        y -= self._pill_h + 10
        for p in summary:
            _, h = p.wrap(self.box_width - 36, 1000)
            p.drawOn(c, 18, y - h)
            y -= h
        if summary:
            y -= 6
        _, h = total.wrap(self.box_width - 36, 1000)
        total.drawOn(c, 18, y - h)
        y -= h + 8
        for p in notes:
            _, h = p.wrap(self.box_width - 36, 1000)
            p.drawOn(c, 18, y - h)
            y -= h + 3


def _draw_image_page(name, fallback: str | None = None):
    def draw(canvas, doc):
        canvas.drawImage(asset(name, fallback or name), 0, 0, width=PAGE[0], height=PAGE[1])
    return draw


def _draw_cover(context):
    def draw(canvas, doc):
        w, h = PAGE
        canvas.drawImage(asset("fundo_capa.jpg", "fundo.jpg"), 0, 0, width=w, height=h)
        canvas.setFillColor(COPPER)
        canvas.setFont("Helvetica", 54)
        canvas.drawCentredString(w / 2, h - 230, "PROPOSTA")
        canvas.drawCentredString(w / 2, h - 292, "COMERCIAL")
        size = 230
        canvas.drawImage(str(ASSETS / "logo.png"), (w - size) / 2, h / 2 - size / 2 - 40, width=size, height=size,
                         mask="auto")
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawCentredString(w / 2, 190, context["client_name"][:48])
        canvas.setFont("Helvetica", 13)
        y = 166
        if context.get("company"):
            canvas.drawCentredString(w / 2, y, context["company"][:60])
            y -= 20
        canvas.setFillColor(COPPER)
        canvas.drawCentredString(w / 2, y, context["title"])
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 11)
        canvas.drawCentredString(w / 2, y - 20, f"Proposta v{context['version']} · {context['issued_at']}")
    return draw


FRAME = (36, 50, PAGE[0] - 72, PAGE[1] - 230)  # x, y, largura, altura do conteúdo


def _draw_content(context):
    def draw(canvas, doc):
        w, h = PAGE
        canvas.drawImage(asset("fundo_preco.jpg", "fundo.jpg"), 0, 0, width=w, height=h)
        x, y, fw, fh = FRAME
        canvas.setStrokeColor(COPPER)
        canvas.setLineWidth(1.4)
        canvas.roundRect(x - 12, y - 18, fw + 24, fh + 34, 26, stroke=1, fill=0)
        size = 96
        logo_y = y + fh + 16 - size / 2
        canvas.setFillColor(HexColor("#000000"))
        canvas.circle(w / 2, logo_y + size / 2, size / 2 + 4, stroke=0, fill=1)
        canvas.drawImage(str(ASSETS / "logo.png"), (w - size) / 2, logo_y, width=size, height=size, mask="auto")
        canvas.setFillColor(TEXT)
        canvas.setFont("Helvetica", 14)
        header = context["header"]
        top = h - 34
        for i, text in enumerate(header[:4]):
            canvas.drawCentredString(w / 2, top - i * 19, text)
    return draw


def render_pdf(context: dict, compress: bool = True) -> bytes:
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=PAGE, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
        title=f"Proposta comercial - {context['client_name']}", author="LM Eventos",
        pageCompression=1 if compress else 0, invariant=1,
    )
    full = Frame(0, 0, PAGE[0], PAGE[1], leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="full")
    x, y, fw, fh = FRAME
    content = Frame(x, y, fw, fh - 70, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="content")
    doc.addPageTemplates([
        PageTemplate(id="capa", frames=[full], onPage=_draw_cover(context)),
        PageTemplate(id="missao", frames=[full], onPage=_draw_image_page("missao.jpg")),
        PageTemplate(id="referencias", frames=[full], onPage=_draw_image_page(
            REFERENCE_ASSETS.get(context.get("mode"), "referencias.jpg"), "referencias.jpg")),
        PageTemplate(id="evento", frames=[content], onPage=_draw_content(context)),
        PageTemplate(id="contato", frames=[full], onPage=_draw_image_page("contato.jpg")),
    ])

    story = [Spacer(1, 1), NextPageTemplate("missao"), PageBreak(), Spacer(1, 1), NextPageTemplate("referencias"),
             PageBreak(), Spacer(1, 1), NextPageTemplate("evento"), PageBreak()]
    story.append(Paragraph(escape(context["title"].upper()), STYLES["block"]))
    story.append(Spacer(1, 6))
    for block in context["blocks"]:
        part = [Paragraph(escape(block["title"].upper()), STYLES["block"])]
        part += [Paragraph(escape(item), STYLES["item"]) for item in block["items"]]
        story.append(KeepTogether(part))
        story.append(Spacer(1, 7))
    # Incluso e não incluso lado a lado
    columns = [
        [Paragraph(escape(title.upper()), STYLES["block"])] + [Paragraph(escape(i), STYLES["item"]) for i in items]
        for title, items in (("Incluso", context["included"]), ("Não está incluso", context["not_included"])) if items
    ]
    if columns:
        table = Table([columns], colWidths=[fw / len(columns)] * len(columns))
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        story.append(table)
        story.append(Spacer(1, 7))
    story.append(Spacer(1, 4))
    story.append(PaymentBox(context, fw))
    story += [NextPageTemplate("contato"), PageBreak(), Spacer(1, 1)]
    doc.build(story)
    return buffer.getvalue()


def file_name(context: dict) -> str:
    safe = "".join(ch for ch in context["client_name"] if ch.isalnum() or ch in " -_").strip().replace(" ", "_")
    return f"Proposta_LM_{safe or 'cliente'}_v{context['version']}.pdf"
