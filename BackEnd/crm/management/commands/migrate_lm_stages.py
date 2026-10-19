"""Migra os leads para as etapas do processo com SDR. Idempotente: pode rodar várias vezes.

ANALYSIS -> NEW_LEAD; BUDGET sem proposal_sent_at -> QUALIFIED; BUDGET com proposal_sent_at
e NEGOTIATING -> PROPOSAL_SENT; WON -> CONTRACT_SIGNED; LOST continua LOST.
Também preenche os campos novos que faltarem (owner, contact_type, flags...), sem apagar nada.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog

FIELD_DEFAULTS = {
    "owner": "sdr",
    "contact_type": "lead",
    "human_operator": False,
    "needs_erica": False,
    "qualification": {},
    "pending_fields": [],
    "attachments": [],
    "flags": [],
}


class Command(BaseCommand):
    help = "Migra customer_state_now das etapas antigas para as novas e preenche campos novos."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só mostra o que mudaria.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        collection = Customer._get_collection()
        log_collection = ServiceLog._get_collection()
        now = datetime.utcnow()
        moved = {}
        filled = 0

        for doc in collection.find({}, {"customer_state_now": 1, "proposal_sent_at": 1, **{f: 1 for f in FIELD_DEFAULTS}}):
            updates = {f: v for f, v in FIELD_DEFAULTS.items() if f not in doc}
            old_stage = doc.get("customer_state_now")
            new_stage = domain.resolve_legacy_stage(old_stage, doc.get("proposal_sent_at"))
            if old_stage != new_stage:
                updates["customer_state_now"] = new_stage
                updates["stage_changed_at"] = now
                key = f"{old_stage or '(vazio)'} -> {new_stage}"
                moved[key] = moved.get(key, 0) + 1
            elif updates:
                filled += 1
            if not updates or dry_run:
                continue
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})
            if "customer_state_now" in updates:
                log_collection.insert_one({
                    "customer": doc["_id"], "operator_id": None, "action_type": "STAGE_CHANGED",
                    "description": f"Migração para o novo funil: {old_stage or '(vazio)'} -> {domain.STAGE_LABELS[new_stage]}.",
                    "metadata": {"from": old_stage, "to": new_stage, "migration": "migrate_lm_stages"},
                    "created_at": now,
                })

        prefix = "[dry-run] " if dry_run else ""
        if not moved:
            self.stdout.write(f"{prefix}Nenhum lead em etapa antiga.")
        for key, count in sorted(moved.items()):
            self.stdout.write(f"{prefix}{key}: {count}")
        self.stdout.write(f"{prefix}Leads só com campos novos preenchidos: {filled}")
