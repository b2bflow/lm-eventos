"""Carga inicial do estoque (idempotente).

Quantidades da contagem de 22/01/2025 (aproximada), sem o que foi vendido em 2026. Itens já
existentes não têm a quantidade sobrescrita, a menos que se use --reset-counts.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from inventory.models import InventoryItem
from sales.catalog import CATALOG

COUNTED_AT = datetime(2025, 1, 22)


class Command(BaseCommand):
    help = "Cria/atualiza os itens de estoque a partir do catálogo (contagem de 22/01/2025)."

    def add_arguments(self, parser):
        parser.add_argument("--reset-counts", action="store_true", help="Volta as quantidades para a contagem de 2025.")
        parser.add_argument("--only-missing", action="store_true",
                            help="Só cria os itens novos do catálogo; não mexe nos que já existem.")

    def handle(self, *args, **options):
        created = updated = 0
        for entry in CATALOG:
            item = InventoryItem.objects(code=entry["code"]).first()
            fields = {
                "line": entry["line"], "name": entry["name"], "size": entry["size"],
                "billing_unit": entry["billing_unit"], "owned": entry["owned"], "rentable": entry["rentable"],
                "note": entry["note"],
            }
            if item is None:
                InventoryItem(code=entry["code"], qty_total=entry["qty"], approximate_count=True,
                              counted_at=COUNTED_AT if entry["qty"] is not None else None, **fields).save()
                created += 1
                continue
            if options["only_missing"]:
                continue
            for key, value in fields.items():
                setattr(item, key, value)
            if options["reset_counts"]:
                item.qty_total = entry["qty"]
                item.counted_at = COUNTED_AT if entry["qty"] is not None else None
                item.approximate_count = True
            item.updated_at = datetime.utcnow()
            item.save()
            updated += 1
        self.stdout.write(f"Estoque: {created} itens criados, {updated} atualizados.")
