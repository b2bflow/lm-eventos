"""Catálogo único da LM: o mesmo código identifica o item na tabela de preços, no estoque e na
calculadora. Preços de venda (seção 5 do documento) são o padrão; a Erica edita em
LmSettings.price_table sem deploy.

Quantidades: contagem de 22/01/2025 (MATERIAIS CONTADOS NO ESTOQUE EM 22.pdf), sem o que foi
vendido em 2026 (escada de palco, gradis 1,60 e 2,20, mãos francesas, pés de palco, pé de
guarda-corpo, pirulito, tábuas e travessas). `qty=None` = item ainda não contado.
"""

# Preço por metro das torres (peças de 2 m a 5 m; a de 2,5 m conta como 3 m)
METRO_PRICE = {"Q30": 15.0, "Q15": 13.0}

LINES = ("Q30", "Q15", "Som", "Iluminação", "Vídeo", "Palco e praticáveis", "Acessórios")


def _item(code, line, name, billing_unit, sale_price, qty=None, size=None, length_m=None, billed_length_m=None,
          owned=True, cost=None, block=None, note=None, rentable=True):
    return {
        "code": code, "line": line, "name": name, "size": size, "billing_unit": billing_unit,
        "sale_price": sale_price, "cost": cost, "qty": qty, "owned": owned,
        "length_m": length_m, "billed_length_m": billed_length_m, "block": block, "note": note,
        "rentable": rentable,
    }


CATALOG = [
    # --- Q30 (locação de porta) ---------------------------------------------------------
    _item("q30_torre_5m", "Q30", "Torre Q30 5 m", "metro", None, 113, "5 m", 5, 5, block="estrutura"),
    _item("q30_torre_4m", "Q30", "Torre Q30 4 m", "metro", None, 70, "4 m", 4, 4, block="estrutura"),
    _item("q30_torre_3m", "Q30", "Torre Q30 3 m", "metro", None, 127, "3 m", 3, 3, block="estrutura"),
    _item("q30_torre_2_5m", "Q30", "Torre Q30 2,5 m", "metro", None, 10, "2,5 m", 2.5, 3, block="estrutura",
          note="Conta como 3 m"),
    _item("q30_torre_2m", "Q30", "Torre Q30 2 m", "metro", None, 152, "2 m", 2, 2, block="estrutura"),
    _item("q30_torre_1_70m", "Q30", "Peça Q30 1,70 m", "unidade", 20.0, 0, "1,70 m", block="estrutura",
          note="Preço a validar com a Erica"),
    _item("q30_torre_1m", "Q30", "Torre Q30 1 m", "unidade", 20.0, 121, "1 m", block="estrutura"),
    _item("q30_torre_0_5m", "Q30", "Torre Q30 0,50 m", "unidade", 20.0, 89, "0,50 m", block="estrutura"),
    _item("q30_adaptador_10", "Q30", "Adaptador Q30 10 cm", "unidade", 20.0, 15, "10 cm", block="estrutura"),
    _item("q30_adaptador_20", "Q30", "Adaptador Q30 20 cm", "unidade", 20.0, 36, "20 cm", block="estrutura"),
    _item("q30_adaptador_30", "Q30", "Adaptador Q30 30 cm", "unidade", 20.0, 15, "30 cm", block="estrutura"),
    _item("q30_cubo_5_faces", "Q30", "Cubo 5 faces Q30", "unidade", 20.0, 215, block="estrutura"),
    _item("q30_cubo_15", "Q30", "Cubo 15° Q30", "unidade", 20.0, 31, block="estrutura"),
    _item("q30_cubo_45", "Q30", "Cubo 45° Q30", "unidade", 20.0, 2, block="estrutura"),
    _item("q30_dobradica", "Q30", "Dobradiça Q30", "unidade", 20.0, 0, block="estrutura", note="Fora da contagem de 2025"),
    _item("q30_cumeeira", "Q30", "Cumeeira Q30", "unidade", 60.0, 5, block="estrutura"),
    _item("q30_sleeve", "Q30", "Sleeve", "unidade", 50.0, 10, block="estrutura"),
    _item("q30_pau_carga_ferro", "Q30", "Pau de carga (ferro)", "unidade", 15.0, 12, block="estrutura"),
    _item("q30_pau_carga_aluminio", "Q30", "Pau de carga (alumínio)", "unidade", 15.0, 4, block="estrutura"),
    _item("q30_sapata", "Q30", "Sapata Q30", "unidade", 15.0, 20, block="estrutura"),
    # --- Q15 ----------------------------------------------------------------------------
    _item("q15_torre_3m", "Q15", "Torre Q15 3 m", "metro", None, 8, "3 m", 3, 3, block="estrutura"),
    _item("q15_torre_2_5m", "Q15", "Torre Q15 2,5 m", "metro", None, 6, "2,5 m", 2.5, 3, block="estrutura",
          note="Conta como 3 m"),
    _item("q15_torre_2m", "Q15", "Torre Q15 2 m", "metro", None, 13, "2 m", 2, 2, block="estrutura"),
    _item("q15_torre_1m", "Q15", "Torre Q15 1 m", "unidade", 13.0, 14, "1 m", block="estrutura"),
    _item("q15_torre_0_5m", "Q15", "Torre Q15 0,50 m", "unidade", 13.0, 7, "0,50 m", block="estrutura"),
    _item("q15_cubo", "Q15", "Cubo Q15 (5 faces / 15°)", "unidade", 13.0, 15, block="estrutura"),
    _item("q15_sapata", "Q15", "Sapata Q15", "unidade", 13.0, 10, block="estrutura"),
    _item("q15_cumeeira", "Q15", "Cumeeira Q15", "unidade", 20.0, 0, block="estrutura", note="Fora da contagem de 2025"),
    # --- Acessórios sem preço (pendência com a Erica: travam a calculadora) --------------
    _item("ac_cubo_22", "Acessórios", "Cubo 22°", "unidade", None, 20, block="estrutura"),
    _item("ac_talha_5m", "Acessórios", "Talha 5 m", "unidade", None, 6, "5 m", block="estrutura"),
    _item("ac_talha_7_5m", "Acessórios", "Talha 7,5 m", "unidade", None, 1, "7,5 m", block="estrutura"),
    _item("ac_talha_8m", "Acessórios", "Talha 8 m", "unidade", None, 1, "8 m", block="estrutura"),
    _item("ac_talha_10m", "Acessórios", "Talha 10 m", "unidade", None, 8, "10 m", block="estrutura"),
    _item("ac_talha_15m", "Acessórios", "Talha 15 m", "unidade", None, 2, "15 m", block="estrutura"),
    _item("ac_gradil_3m", "Acessórios", "Gradil 3 m", "unidade", None, 32, "3 m", block="estrutura"),
    _item("ac_cinta_branca", "Acessórios", "Cinta branca", "unidade", None, 28, block="estrutura"),
    _item("ac_cinta_carga", "Acessórios", "Cinta de carga", "unidade", None, 54, block="estrutura"),
    _item("ac_cinta_estanhar", "Acessórios", "Cinta para estanhar", "unidade", None, 85, block="estrutura"),
    _item("ac_catraca_grande", "Acessórios", "Catraca grande", "unidade", None, 77, block="estrutura"),
    _item("ac_catraca_pequena", "Acessórios", "Catraca pequena", "unidade", None, 31, block="estrutura"),
    _item("ac_grampo_aluminio", "Acessórios", "Grampo (alumínio)", "unidade", None, 102, block="estrutura"),
    _item("ac_grampo_ferro", "Acessórios", "Grampo (ferro)", "unidade", None, 52, block="estrutura"),
    _item("ac_ponta_eixo", "Acessórios", "Ponta de eixo", "unidade", None, 52, block="estrutura"),
    _item("ac_arco_geo", "Acessórios", "Arco de GEO", "unidade", None, 4, block="estrutura"),
    # Equipamento de apoio (uso interno, não alugado)
    _item("int_bombona", "Acessórios", "Bombona", "unidade", None, 15, rentable=False),
    _item("int_carretinha", "Acessórios", "Carretinha", "unidade", None, 1, rentable=False),
    _item("int_carretona", "Acessórios", "Carretona", "unidade", None, 1, rentable=False),
    _item("int_carrinho_carga", "Acessórios", "Carrinho de carga", "unidade", None, 4, rentable=False),
    _item("int_escada_aluminio", "Acessórios", "Escada de alumínio", "unidade", None, 2, rentable=False),
    _item("int_marreta", "Acessórios", "Marreta", "unidade", None, 3, rentable=False),
    # --- Som ----------------------------------------------------------------------------
    _item("som_ate_150", "Som", "Som até 150 pessoas (4 caixas + 1 microfone sem fio)", "sistema", 1300.0, block="som"),
    _item("som_150_200", "Som", "Som de 150 a 200 pessoas", "sistema", 2500.0, block="som"),
    _item("som_200_500", "Som", "Som de 200 a 500 pessoas (com par de sub)", "sistema", 3500.0, block="som"),
    _item("som_500_1500", "Som", "Som de 500 a 1.500 pessoas (com sub)", "sistema", 6000.0, block="som"),
    _item("som_acima_1500", "Som", "Som acima de 1.500 pessoas", "sistema", 8000.0, block="som",
          note="Faixa R$ 8.000 a 10.000; exige visita técnica"),
    _item("som_sub_duplo", "Som", "Sub duplo", "par", 500.0, block="som"),
    _item("som_backline", "Som", "Backline (banda)", "conjunto", 1800.0, block="som"),
    _item("som_mic_sem_fio", "Som", "Microfone sem fio adicional", "unidade", 150.0, block="som"),
    _item("som_mesa_digital", "Som", "Mesa de canais digital", "unidade", 150.0, block="som"),
    _item("som_cerimonia", "Som", "Som de cerimônia (4 caixas ativas, pedestais, mesa e microfone)", "sistema", 1300.0,
          block="som", note="Social"),
    # --- Iluminação ---------------------------------------------------------------------
    _item("luz_moving_beam", "Iluminação", "Moving beam (Move 9R)", "unidade", 150.0, block="iluminacao"),
    _item("luz_par_led", "Iluminação", "Par LED", "unidade", 50.0, block="iluminacao"),
    _item("luz_par_38", "Iluminação", "PAR 38", "unidade", 50.0, block="iluminacao"),
    _item("luz_ribalta", "Iluminação", "Ribalta", "unidade", 120.0, block="iluminacao"),
    _item("luz_atomic", "Iluminação", "Atomic", "unidade", 100.0, block="iluminacao"),
    _item("luz_p5", "Iluminação", "P5 (fachada)", "unidade", 120.0, block="iluminacao"),
    _item("luz_pontual", "Iluminação", "Pontual (vara pimbim)", "unidade", 80.0, block="iluminacao"),
    _item("luz_fumaca", "Iluminação", "Máquina de fumaça", "unidade", 120.0, block="iluminacao"),
    _item("luz_piso_microlampadas", "Iluminação", "Piso de microlâmpadas", "placa", 50.0, block="iluminacao",
          note="Sozinho, mínimo de cerca de R$ 1.300"),
    # --- Vídeo --------------------------------------------------------------------------
    _item("video_led_corporativo", "Vídeo", "Painel de LED (corporativo)", "m²", 300.0, owned=False, cost=200.0,
          block="video", note="Terceirizado: confirmar com o fornecedor"),
    _item("video_led_social", "Vídeo", "Painel de LED (social, técnico incluso)", "m²", 250.0, owned=False, cost=200.0,
          block="video", note="Terceirizado: confirmar com o fornecedor"),
    _item("video_tecnico_led", "Vídeo", "Técnico de LED", "cachê", 500.0, owned=False, block="video"),
    _item("video_estrutura_led", "Vídeo", "Estrutura para painel de LED", "unidade", 400.0, block="video"),
    _item("video_tp", "Vídeo", "TP (TV de retorno) 43\" ou 55\"", "unidade", 380.0, block="video"),
    _item("video_passador_slides", "Vídeo", "Passador de slides", "unidade", 150.0, block="video"),
    # --- Palco e praticáveis -----------------------------------------------------------
    _item("palco_forrado", "Palco e praticáveis", "Palco forrado", "m²", 95.0, block="palco"),
    _item("palco_sem_forracao", "Palco e praticáveis", "Palco sem forração", "m²", 70.0, block="palco"),
    _item("palco_praticavel_2x1", "Palco e praticáveis", "Praticável 2x1 m", "unidade", 150.0, block="palco"),
    _item("palco_backdrop", "Palco e praticáveis", "Backdrop (Q15, 4x2, 3x3 ou 2x2)", "unidade", 500.0, block="palco"),
    _item("palco_passa_cabo", "Palco e praticáveis", "Passa-cabo", "metro", 30.0, 5, block="palco",
          note="Contagem em peças"),
]

CATALOG_BY_CODE = {item["code"]: item for item in CATALOG}

# Bloco da proposta pela linha do estoque (itens criados pela tela de Estoque, fora do CATALOG)
LINE_BLOCKS = {
    "Q30": "estrutura", "Q15": "estrutura", "Acessórios": "estrutura", "Som": "som",
    "Iluminação": "iluminacao", "Vídeo": "video", "Palco e praticáveis": "palco",
}


def catalog_item_from_inventory(doc) -> dict:
    """Item criado no Estoque no formato do catálogo (cobrança por peça/unidade, sem metragem)."""
    return _item(doc.code, doc.line, doc.name, doc.billing_unit or "unidade", None, doc.qty_total, doc.size,
                 owned=doc.owned, block=LINE_BLOCKS.get(doc.line, "outros"), note=doc.note, rentable=doc.rentable)

# Custos operacionais (seção 5.3)
OPERATIONAL_COSTS = {
    "carga": {"label": "Carga (2 x R$ 150)", "price": 300.0},
    "montagem": {"label": "Montagem (3 pessoas)", "price": 1200.0},
    "desmontagem": {"label": "Desmontagem", "price": 1200.0},
    "descarga": {"label": "Descarga", "price": 250.0},
    "frete": {"label": "Frete (combustível, Goiânia)", "price": 300.0},
    "alimentacao": {"label": "Alimentação da equipe", "price": 300.0},
    "adicional_noturno": {"label": "Adicional noturno", "price": 500.0},
    "tecnico_som": {"label": "Técnico de som", "price": 500.0},
    "tecnico_banda": {"label": "Técnico de banda", "price": 500.0},
    "tecnico_luz": {"label": "Técnico de luz", "price": 500.0},
    "dj": {"label": "DJ", "price": 700.0},
    "mao_de_obra_avulsa": {"label": "Mão de obra avulsa (pessoa/dia)", "price": 225.0},
    "entrega_praticavel": {"label": "Entrega de praticável", "price": 150.0},
}

# Faixas de som por público (limite superior inclusivo -> código do sistema)
SOUND_TIERS = [
    (150, "som_ate_150"),
    (200, "som_150_200"),
    (500, "som_200_500"),
    (1500, "som_500_1500"),
    (None, "som_acima_1500"),
]


# Estruturas montadas pela tabela Q30 (seção 5.2: "monte como kit de peças"). Editável em
# LmSettings.price_table["kits"].
STRUCTURE_KITS = {
    "gol_3x4": {
        "label": "Gol 3x4 m (Q30)",
        "pieces": [
            {"code": "q30_torre_3m", "qty": 2}, {"code": "q30_torre_4m", "qty": 1},
            {"code": "q30_cubo_5_faces", "qty": 2}, {"code": "q30_sapata", "qty": 2},
        ],
    },
    "grid_4x4x3": {
        "label": "Grid 4x4x3 m (Q30)",
        "pieces": [
            {"code": "q30_torre_3m", "qty": 4}, {"code": "q30_torre_4m", "qty": 4},
            {"code": "q30_cubo_5_faces", "qty": 4}, {"code": "q30_sapata", "qty": 4},
        ],
    },
}

# Pacote básico do social: gol 3x4 + LED 3x2 + som até 150 + luz + DJ (entradas do SocialInput).
SOCIAL_BASIC_PACKAGE = {
    "structure": "gol_3x4",
    "led_m2": 6,
    "dance_floor": True,
    "lights": {"luz_par_led": 8, "luz_moving_beam": 2, "luz_fumaca": 1},
    "dj": True,
    "operational": ["carga", "montagem", "desmontagem", "descarga", "frete", "alimentacao"],
}


def default_price_table() -> dict:
    return {
        "metro_price": dict(METRO_PRICE),
        "items": {code: {"sale_price": item["sale_price"], "cost": item["cost"]} for code, item in CATALOG_BY_CODE.items()},
        "operational_costs": {k: v["price"] for k, v in OPERATIONAL_COSTS.items()},
        "sound_tiers": [[limit, code] for limit, code in SOUND_TIERS],
        "kits": {k: {"label": v["label"], "pieces": [dict(p) for p in v["pieces"]]} for k, v in STRUCTURE_KITS.items()},
    }


def merge_price_table(overrides: dict | None) -> dict:
    """Tabela efetiva = padrões do catálogo + o que a Erica editou em LmSettings.price_table."""
    table = default_price_table()
    overrides = overrides or {}
    table["metro_price"].update(overrides.get("metro_price") or {})
    # Inclui códigos fora do CATALOG: itens criados pela tela de Estoque também têm preço
    for code, values in (overrides.get("items") or {}).items():
        table["items"].setdefault(code, {"sale_price": None, "cost": None}).update(values or {})
    table["operational_costs"].update(overrides.get("operational_costs") or {})
    if overrides.get("sound_tiers"):
        table["sound_tiers"] = overrides["sound_tiers"]
    table["kits"].update(overrides.get("kits") or {})
    return table
