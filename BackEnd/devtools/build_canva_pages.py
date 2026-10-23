"""Gera as páginas do PDF da proposta a partir dos PDFs exportados do Canva.

Uso (uma vez, quando a LM mudar um modelo no Canva; precisa de `pip install pymupdf`, que não vai
para o deploy):

    python devtools/build_canva_pages.py <Proposta Comercial.pdf> <...Corporativo.pdf> <...Casamento.pdf>

Cada modelo vira 5 imagens em `sales/pdf_assets/canva/<modelo>/pagina<N>.jpg`. Capa (nome do cliente e
data) e página de preços (todos os textos) saem sem os textos que a plataforma escreve; o resto do design
fica como está no Canva. A missão do casamento também sai sem texto (`pagina2_sem_texto.jpg`) para o
evento social que não é casamento, que recebe o texto genérico por cima.
"""
import sys
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent.parent / "sales" / "pdf_assets" / "canva"
MODELS = ("estrutura", "corporativo", "casamento")  # ordem dos arquivos na linha de comando
ZOOM = 2  # 810x1440 pt -> 1620x2880 px
QUALITY = 82

# Textos que ficam no design (o resto da capa é preenchido pela plataforma)
COVER_KEEP = {"PROPOSTA", "COMERCIAL"}


def clear_text(page, keep=frozenset()):
    """Apaga só os textos (fotos, formas e linhas ficam), menos os de `keep`."""
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip() and span["text"].strip() not in keep:
                    page.add_redact_annot(pymupdf.Rect(span["bbox"]), fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)


def save(page, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM)).save(str(path), jpg_quality=QUALITY)
    print(path.relative_to(OUT.parent), f"{path.stat().st_size // 1024} KB")


def build(model: str, source: str):
    doc = pymupdf.open(source)
    assert len(doc) == 5, f"{source}: esperava 5 páginas (capa, missão, referências, preços, contato)"
    clear_text(doc[0], keep=COVER_KEEP)
    clear_text(doc[3])
    for number, page in enumerate(doc, start=1):
        save(page, OUT / model / f"pagina{number}.jpg")
    if model == "casamento":
        mission = pymupdf.open(source)
        clear_text(mission[1])
        save(mission[1], OUT / model / "pagina2_sem_texto.jpg")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    for model, source in zip(MODELS, sys.argv[1:]):
        build(model, source)
