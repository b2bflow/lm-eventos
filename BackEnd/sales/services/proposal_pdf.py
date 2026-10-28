"""PDF da proposta comercial, igual aos três modelos do Canva da LM.

Os modelos (estrutura, corporativo e casamento) foram exportados do Canva e cada página virou imagem em
`sales/pdf_assets/canva/<modelo>/pagina<N>.jpg` (ver `devtools/build_canva_pages.py`): capa, missão,
referências, preços e contato. Capa e página de preços vêm sem os textos; a plataforma escreve por cima
nome, data, cabeçalho do evento, itens por bloco, incluso e não incluso, forma de pagamento, total e
condições, nas posições, fontes (Montserrat) e cores do Canva (LAYOUTS). Porta e produto único usam o
modelo de estrutura; corporativo o corporativo; social o de casamento (evento social que não é casamento
usa a missão sem texto, com o texto genérico por cima). Para mudar o visual, mude no Canva, exporte em PDF
e rode o script de novo.

Se os itens não cabem no quadro, o texto da página de preços diminui até caber (TEXT_SCALES).

Valores dos itens: só aparecem com `inputs.show_item_prices` (desligado por padrão). Ligado, cada item
sai com quantidade, preço unitário e subtotal (o preço editado na proposta, se houver), e um bloco de
valores mostra itens, serviços, nota e ajustes antes do total.

`build_pdf_context` é pura (testável sem banco) e `render_pdf` desenha com ReportLab, que não
depende de bibliotecas nativas (WeasyPrint exigiria GTK/Pango na imagem de deploy).
"""
from collections import OrderedDict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas

from sales.formatting import format_brl

# As páginas do Canva entram como JPEG (~1,4 MB por PDF). Com ASCII85 ligado (padrão do ReportLab), cada
# byte passa por um laço em Python puro (sem o acelerador em C): segundos de CPU por PDF em produção,
# segurando os outros pedidos. Sem ele o JPEG vai binário no PDF, como é o normal.
rl_config.useA85 = 0

ASSETS = Path(__file__).resolve().parent.parent / "pdf_assets"
CANVA = ASSETS / "canva"
PAGE = (810, 1440)  # tamanho da página exportada do Canva (story 9:16)
COPPER = HexColor("#D3986B")
TEXT = white

MODE_TITLES = {
    "porta": "Locação de estrutura",
    "corporativo": "Evento corporativo",
    "social": "Evento social",
    "produto_unico": "Locação de equipamento",
}

# Modelo do Canva usado por cada modo da proposta
MODE_MODELS = {"porta": "estrutura", "produto_unico": "estrutura", "corporativo": "corporativo", "social": "casamento"}


MISSION_ESTRUTURA = [
    "Nossa missão é planejar, organizar e produzir um espetáculo de diferentes linguagens com foco na "
    "excelência e qualidade.",
    "Com atendimento personalizado oferecemos uma ampla gama de serviços para transformar seu evento em "
    "realidade.",
    "Para isso, listamos o que será feito no seu evento nas páginas abaixo.",
    "Tudo o que executamos é impulsionado com excelência e compromisso, desenvolvendo os melhores "
    "resultados do mercado.",
]
MISSION_CORPORATIVO = [
    "Nossa missão é dar vida ao planejamento do seu evento, transformando em realidade.",
    "Proporcionamos um atendimento personalizado e único, garantindo uma experiência inesquecível.",
    "Para isso, listamos o que será feito no seu evento nas páginas abaixo.",
    "Tudo o que executamos é impulsionado com excelência e compromisso, desenvolvendo os melhores "
    "resultados do mercado.",
    "Transformamos o seu evento em um ambiente envolvente e inspirador, onde os participantes possam se "
    "conectar, aprender e compartilhar ideias!",
]
MISSION_CASAMENTO = [
    "Nossa missão é dar vida ao planejamento do seu casamento, transformando o sonho de um dia perfeito "
    "em realidade.",
    "Com atendimento personalizado, queremos que seu casamento seja único e traga as melhores experiências "
    "para você e seus convidados.",
    "Para isso, listamos o que será feito nas páginas abaixo.",
    "Tudo o que fazemos é impulsionado pela excelência e compromisso de desenvolver os melhores serviços "
    "do mercado.",
    "Transformaremos seu casamento em uma experiência inesquecível!",
]
MISSION_SOCIAL = [text.replace("casamento", "evento") for text in MISSION_CASAMENTO]

# Texto da página de missão por modo (os três modelos do Canva); social só diz "casamento" para casamento
MISSION_TEXTS = {
    "porta": MISSION_ESTRUTURA,
    "produto_unico": MISSION_ESTRUTURA,
    "corporativo": MISSION_CORPORATIVO,
    "social": MISSION_SOCIAL,
}


def mission_text(mode: str | None, celebration_type: str | None = None) -> list[str]:
    if mode == "social" and "casamento" in (celebration_type or "").lower():
        return MISSION_CASAMENTO
    return MISSION_TEXTS.get(mode, MISSION_ESTRUTURA)


BLOCK_ORDER = OrderedDict([
    ("estrutura", "Estrutura"),
    ("palco", "Palco e praticáveis"),
    ("som", "Sonorização"),
    ("iluminacao", "Iluminação"),
    ("video", "Vídeo"),
    ("outros", "Extra"),
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


def _cover_day(value, model: str) -> str:
    """Data da capa como no Canva: "23 DE JULHO" (corporativo) ou "15/AGOSTO/2026" (casamento)."""
    day = _day(value)
    if not day:
        return ""
    month = MONTHS[day.month - 1].upper()
    return f"{day.day:02d} DE {month}" if model == "corporativo" else f"{day.day:02d}/{month}/{day.year}"


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


# Propostas salvas antes do microfone da banda ter nome próprio: a linha é reconhecida pela observação
LEGACY_LINE_NAMES = {("som_mic_sem_fio", "Voz e violão"): "Microfone sem fio (voz e violão)"}


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
        # Conjunto de som: o cliente vê as peças ("04 Caixa de som ativa"), nunca o nome do conjunto. Com
        # preço por item, as peças saem numa linha só com o preço do conjunto.
        if line.get("components"):
            if show_prices:
                pieces = ", ".join(f"{_qty(c.get('qty'), c.get('unit') or 'unidade')} {c.get('name')}"
                                   for c in line["components"])
                blocks[block][f"set:{len(blocks[block])}"] = {"text": pieces, "qty": 1, "unit": "unidade",
                                                              "subtotal": subtotal, "unit_price": None}
                continue
            for c in line["components"]:
                entry = blocks[block].setdefault((c.get("code"), c.get("name"), None), {
                    "qty": 0, "unit": c.get("unit") or "unidade", "name": c.get("name"), "subtotal": 0.0,
                    "unit_price": None})
                entry["qty"] += float(c.get("qty") or 0) * float(line.get("qty") or 1)
            continue
        # Só soma linhas do mesmo item, com o mesmo nome e preço: o microfone da banda não some dentro dos
        # extras e "cada x quantidade" sempre bate com o subtotal
        name = LEGACY_LINE_NAMES.get((line.get("code"), line.get("note")), line.get("name"))
        key = (line.get("code"), name, line.get("unit_price"))
        entry = blocks[block].setdefault(key, {"qty": 0, "unit": line.get("unit") or "unidade", "name": name,
                                               "subtotal": 0.0, "unit_price": line.get("unit_price")})
        entry["qty"] += float(line.get("qty") or 0)
        entry["subtotal"] += subtotal

    def item_text(v: dict) -> str:
        if v.get("text"):
            return f"{v['text']}: {format_brl(v['subtotal'])}"
        text = f"{_qty(v['qty'], v['unit'])} {v['name']}"
        if not show_prices:
            return text
        unit_price = v["unit_price"] if v["unit_price"] is not None else v["subtotal"]
        if float(v["qty"]) == 1 and periods == 1:
            return f"{text}: {format_brl(v['subtotal'])}"
        weeks = f" x {periods} semanas" if periods > 1 else ""
        per = {"m²": "o m²", "metro": "o metro"}.get(v["unit"], "cada")
        return f"{text}: {format_brl(unit_price)} {per}{weeks} = {format_brl(v['subtotal'])}"

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

    event_day = inputs.get("event_date") or customer.get("event_date") or proposal.get("period_start")
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
        header = [f"Data do evento: {_fmt_day(event_day)}",
                  f"Local: {customer.get('venue') or qualification.get('local') or 'a definir'}",
                  f"Horário: {qualification.get('horario') or qualification.get('horario_evento') or 'a definir'}"]

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

    model = MODE_MODELS.get(mode, "estrutura")
    validity_days = int(settings.get("proposal_validity_days") or 5)
    payment = [settings.get("payment_terms_text") or "Forma de pagamento a combinar.",
               settings.get("down_payment_text") or "Sinal a combinar."]
    return {
        "client_name": customer.get("name") or customer.get("company") or "Cliente",
        "company": customer.get("company") if customer.get("name") else None,
        "issued_at": _long_day(issued_at),
        "model": model,
        "cover_name": (customer.get("name") or customer.get("company") or "").upper() if model != "estrutura" else None,
        "cover_date": _cover_day(event_day, model) if model != "estrutura" else None,
        "issued_day": _fmt_day(issued_at),
        "mission_page": "pagina2.jpg" if mode != "social" or mission_text(mode, customer.get("celebration_type"))
        is MISSION_CASAMENTO else "pagina2_sem_texto.jpg",
        "mission": mission_text(mode, customer.get("celebration_type")),
        "total_label": "INVESTIMENTO" if mode == "social" else "CUSTO TOTAL",
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

FONT_FILES = {"Montserrat": "Montserrat-Regular.ttf", "Montserrat-SemiBold": "Montserrat-SemiBold.ttf"}
FONT_FALLBACK = {"Montserrat": "Helvetica", "Montserrat-SemiBold": "Helvetica-Bold"}


def _font(name: str) -> str:
    """Montserrat (a fonte do Canva) de pdf_assets/fonts; sem o arquivo, Helvetica."""
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    path = ASSETS / "fonts" / FONT_FILES[name]
    if not path.exists():
        return FONT_FALLBACK[name]
    pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


# Posições do Canva em pontos, com y medido do alto da página (como no PDF exportado).
# header: linhas de data/local/horário; content: área dos itens dentro do quadro; pill: faixa da forma de
# pagamento; total e terms: valor e condições embaixo; cover_*: linha de base do nome e da data na capa.
LAYOUTS = {
    "estrutura": {
        "header": {"size": 31, "base": 56.8, "step": 42.7},
        "content": {"top": 324.5, "bottom": 1180, "width": 560, "title": 40, "item": 31, "after_title": 17.6,
                    "between": 17.8},
        "pill": {"box": (138.5, 1209.4, 696.9, 1262.4), "size": 27},
        "total": {"base": 1310.7, "size": 35},
        "terms": {"top": 1334.7, "size": 22, "width": 600},
        "cover_name": None, "cover_date": None,
    },
    "corporativo": {
        "header": {"size": 25, "base": 67.2, "step": 34.5},
        "content": {"top": 334.7, "bottom": 1236, "width": 560, "title": 40, "item": 25, "after_title": 14,
                    "between": 17.6},
        "pill": {"box": (151.0, 1248.0, 664.8, 1290.0), "size": 13},
        "total": {"base": 1338.2, "size": 35},
        "terms": {"top": 1353.5, "size": 21.7, "width": 600},
        "cover_name": 123.0, "cover_date": 1350.7,
    },
    "casamento": {
        "header": {"size": 25, "base": 67.2, "step": 34.5},
        "content": {"top": 326.2, "bottom": 1162, "width": 560, "title": 40, "item": 25, "after_title": 0,
                    "between": 11},
        "pill": {"box": (124.5, 1174.2, 662.1, 1220.8), "size": 18},
        "total": {"base": 1264.5, "size": 29},
        "terms": {"top": 1303.7, "size": 15, "width": 560},
        "cover_name": 108.7, "cover_date": 1305.3,
    },
}
ASCENT = 0.968  # linha de base = topo da caixa de texto + ASCENT * tamanho (medido no PDF do Canva)
LEADING = 1.378  # entrelinha dos itens no Canva (42,7 pt para fonte de 31)
TEXT_SCALES = [1 - i * 0.05 for i in range(13)]  # de 100% até 40% para caber no quadro
MISSION = {"top": 376.3, "size": 25, "step": 34.5, "width": 480}
COVER_SIZE = 30
COVER_TRACKING = 2.4  # espaçamento entre letras do nome e da data na capa (medido no Canva)


class _Writer:
    """Escreve texto centralizado com y medido do alto da página; `trace` guarda o que foi escrito."""

    def __init__(self, canvas, trace: list | None):
        self.canvas = canvas
        self.trace = trace

    def line(self, text: str, base: float, size: float, color=TEXT, font="Montserrat", tracking: float = 0.0,
             max_width: float | None = None):
        font = _font(font)
        width = pdfmetrics.stringWidth(text, font, size) + tracking * max(len(text) - 1, 0)
        if max_width and width > max_width:  # encolhe para caber na largura
            size *= max_width / width
            width = max_width
        self.canvas.setFillColor(color)
        self.canvas.setFont(font, size)
        if tracking:
            obj = self.canvas.beginText((PAGE[0] - width) / 2, PAGE[1] - base)
            obj.setFont(font, size)
            obj.setCharSpace(tracking)
            obj.textOut(text)
            self.canvas.drawText(obj)
        else:
            self.canvas.drawCentredString(PAGE[0] / 2, PAGE[1] - base, text)
        if self.trace is not None:
            self.trace.append(text)


def _wrap(text: str, size: float, width: float, font="Montserrat") -> list[str]:
    return simpleSplit(text, _font(font), size, width) or [""]


def _price_sections(context: dict) -> list[dict]:
    sections = list(context["blocks"])
    # Incluso e não incluso em linha corrida, para não tomar o lugar dos itens no quadro
    for title, items in (("Incluso", context["included"]), ("Não está incluso", context["not_included"])):
        if items:
            sections.append({"title": title, "items": [" · ".join(items)]})
    if context.get("price_summary"):
        sections.append({"title": "Valores", "items": context["price_summary"]})
    return sections


def _layout_sections(sections: list[dict], spec: dict) -> tuple[float, list]:
    """Maior escala em que os blocos cabem no quadro: (escala, [(tipo, texto, linha de base, tamanho)])."""
    available = spec["bottom"] - spec["top"]
    for scale in TEXT_SCALES:
        title, item = spec["title"] * scale, spec["item"] * scale
        rows, y = [], spec["top"]
        for i, section in enumerate(sections):
            if i:
                y += spec["between"] * scale
            rows.append(("title", section["title"].upper(), y + ASCENT * title, title))
            y += title * 1.22 + spec["after_title"] * scale
            for text in section["items"]:
                for part in _wrap(text, item, spec["width"]):
                    rows.append(("item", part, y + ASCENT * item, item))
                    y += item * LEADING
        if y - spec["top"] <= available or scale == TEXT_SCALES[-1]:
            return scale, rows
    raise AssertionError("TEXT_SCALES vazio")


def _draw_page_image(canvas, model: str, name: str):
    canvas.drawImage(str(CANVA / model / name), 0, 0, width=PAGE[0], height=PAGE[1])


def _draw_cover(write: _Writer, context: dict, layout: dict):
    if layout["cover_name"] and context.get("cover_name"):
        write.line(context["cover_name"][:40], layout["cover_name"], COVER_SIZE, COPPER, "Montserrat-SemiBold",
                   COVER_TRACKING, max_width=PAGE[0] - 120)
    if layout["cover_date"] and context.get("cover_date"):
        write.line(context["cover_date"], layout["cover_date"], COVER_SIZE, COPPER, "Montserrat-SemiBold",
                   COVER_TRACKING, max_width=PAGE[0] - 120)


def _draw_mission(write: _Writer, context: dict):
    base = MISSION["top"] + ASCENT * MISSION["size"]
    for paragraph in context["mission"]:
        for part in _wrap(paragraph, MISSION["size"], MISSION["width"]):
            write.line(part, base, MISSION["size"])
            base += MISSION["step"]
        base += MISSION["step"]


def _draw_prices(write: _Writer, context: dict, layout: dict):
    header = layout["header"]
    for i, text in enumerate(context["header"][:3]):
        write.line(text, header["base"] + i * header["step"], header["size"], max_width=PAGE[0] - 80)

    _, rows = _layout_sections(_price_sections(context), layout["content"])
    for kind, text, base, size in rows:
        write.line(text, base, size, COPPER if kind == "title" else TEXT)

    # Forma de pagamento dentro da faixa: uma linha; se não couber legível, uma linha por texto
    x0, y0, x1, y1 = layout["pill"]["box"]
    size, inner = layout["pill"]["size"], (x1 - x0) - 40
    one_line = " · ".join(context["payment"])
    if pdfmetrics.stringWidth(one_line, _font("Montserrat"), size) * 0.65 <= inner or len(context["payment"]) == 1:
        write.line(one_line, (y0 + y1) / 2 + 0.35 * size, size, max_width=inner)
    else:
        small = min(size * 0.65, (y1 - y0 - 8) / 2.3)
        mid = (y0 + y1) / 2
        for text, base in zip(context["payment"][:2], (mid - 0.15 * small, mid + 1.05 * small)):
            write.line(text, base, small, max_width=inner)

    total = layout["total"]
    write.line(f"{context['total_label']}: {context['total']}", total["base"], total["size"], max_width=PAGE[0] - 100)

    terms = layout["terms"]
    lines = [t for t in (context.get("invoice_note"), context["validity"], context["cancellation"]) if t]
    if context["model"] == "corporativo":
        lines.append(f"Data: {context['issued_day']}")
    size = terms["size"]
    while True:  # diminui até as condições caberem até o fim da página
        parts = [part for text in lines for part in _wrap(text, size, terms["width"])]
        if terms["top"] + len(parts) * size * 1.25 <= PAGE[1] - 8 or size <= 9:
            break
        size -= 0.5
    base = terms["top"] + ASCENT * size
    for part in parts:
        write.line(part, base, size)
        base += size * 1.25


def render_pdf(context: dict, compress: bool = True, trace: list | None = None) -> bytes:
    """Desenha o PDF. `trace` (lista) recebe cada texto escrito por cima do Canva, para os testes."""
    buffer = BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=PAGE, pageCompression=1 if compress else 0, invariant=1)
    canvas.setTitle(f"Proposta comercial - {context['client_name']}")
    canvas.setAuthor("LM Eventos")
    model = context.get("model") or "estrutura"
    layout = LAYOUTS[model]
    write = _Writer(canvas, trace)

    _draw_page_image(canvas, model, "pagina1.jpg")
    _draw_cover(write, context, layout)
    canvas.showPage()
    _draw_page_image(canvas, model, context.get("mission_page") or "pagina2.jpg")
    if context.get("mission_page") == "pagina2_sem_texto.jpg":
        _draw_mission(write, context)
    canvas.showPage()
    _draw_page_image(canvas, model, "pagina3.jpg")
    canvas.showPage()
    _draw_page_image(canvas, model, "pagina4.jpg")
    _draw_prices(write, context, layout)
    canvas.showPage()
    _draw_page_image(canvas, model, "pagina5.jpg")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def file_name(context: dict) -> str:
    safe = "".join(ch for ch in context["client_name"] if ch.isalnum() or ch in " -_").strip().replace(" ", "_")
    return f"Proposta_LM_{safe or 'cliente'}_v{context['version']}.pdf"
