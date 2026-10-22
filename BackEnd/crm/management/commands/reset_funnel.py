"""Zera o funil para o início do atendimento pela plataforma. Idempotente.

Tira todos os contatos do quadro (limpa `funnel_entered_at`) sem apagar nada: os leads continuam
no banco e na página Contatos. A partir daí só entra no funil quem for atendido ou qualificado pela
IA, ou quem tiver um lead aberto à mão (ver crm.services.funnel_entry).
"""
from django.core.management.base import BaseCommand

from crm.models.custumer_model import Customer


class Command(BaseCommand):
    help = "Tira todos os contatos do funil (o quadro fica vazio). Não apaga nada."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só mostra quantos sairiam do funil.")

    def handle(self, *args, **options):
        in_funnel = Customer.objects(funnel_entered_at__ne=None)
        total = in_funnel.count()
        if options["dry_run"]:
            self.stdout.write(f"{total} contato(s) sairiam do funil.")
            return
        in_funnel.update(unset__funnel_entered_at=True)
        self.stdout.write(self.style.SUCCESS(f"Funil zerado: {total} contato(s) saíram do quadro."))
