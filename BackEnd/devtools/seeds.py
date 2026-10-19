"""Seeds extras da demo (funil, estoque, propostas), executados pelo rundemo."""
from datetime import datetime, timedelta
from io import StringIO

from django.core.management import call_command


def seed_funnel():
    from crm.container import CrmContainer
    from crm.models.custumer_model import Customer
    from crm.models.lm_settings_model import LmSettings
    from sales.services.proposal_service import ProposalService

    if Customer.objects(product__ne=None).count():
        return
    cfg = LmSettings.get()
    cfg.sdr_phone = "5562900000001"
    cfg.erica_phone = "5562900000002"
    cfg.save()

    qualification = CrmContainer.get_lead_qualification_service()
    proposals = ProposalService()
    customers = list(Customer.objects.order_by("name")[:12])
    plan = [
        ("estrutura_porta", "NEW_LEAD"), ("corporativo", "NEW_LEAD"), ("social", "NEW_LEAD"),
        ("estrutura_porta", "QUALIFIED"), ("corporativo", "QUALIFIED"), ("estrutura_montagem", "QUALIFIED"),
        ("estrutura_porta", "PROPOSAL_SENT"), ("corporativo", "PROPOSAL_SENT"),
        ("estrutura_porta", "PROPOSAL_ACCEPTED"), ("corporativo", "LOCKED"), ("produto_unico", "LOST"),
        ("social", "HUMAN"),
    ]
    in_two_weeks = (datetime.utcnow() + timedelta(days=14)).date()
    for customer, (product, target) in zip(customers, plan):
        cid = str(customer.id)
        qualification.start_lead(cid, product)
        qualification.save_field(cid, "data_evento", in_two_weeks.isoformat())
        qualification.save_field(cid, "publico", "250")
        qualification.save_field(cid, "local", "Centro de Convenções de Goiânia")
        if product == "estrutura_porta":
            qualification.save_field(cid, "lista_pecas", "não sei")
            qualification.add_attachment(cid, "https://placehold.co/800x600/png", "lista_pecas", "foto-estrutura.png")
        if target == "NEW_LEAD":
            continue
        if target == "HUMAN":
            qualification.mark_human_operator(cid, "Cerimonialista parceira")
            continue
        qualification.qualify_lead(cid, needs_erica=(product == "estrutura_montagem"))
        if target == "LOST":
            CrmContainer.get_pipeline_service().change_stage(cid, "LOST", lost_reason="preco")
            continue
        if target == "QUALIFIED":
            continue
        if product == "estrutura_porta":
            inputs = {"pickup_date": (in_two_weeks - timedelta(days=1)).isoformat(),
                      "return_date": (in_two_weeks + timedelta(days=1)).isoformat(),
                      "items": [{"code": "q30_torre_5m", "qty": 30}, {"code": "q30_cubo_5_faces", "qty": 8},
                                {"code": "q30_sapata", "qty": 8}]}
            proposal = proposals.save(cid, "porta", inputs)
        else:
            inputs = {"guests": 2000 if target == "LOCKED" else 250, "stage_m2": 12,
                      "lights": {"luz_moving_beam": 4, "luz_par_led": 8},
                      "operational": ["carga", "descarga", "frete", "alimentacao"],
                      "margin": 0.35, "with_invoice": True}
            proposal = proposals.save(cid, "corporativo", inputs)
        if target == "LOCKED":
            continue
        # O corporativo enviado há 3 dias mostra o follow-up D+3 na fila da SDR.
        sent_at = datetime.utcnow() - timedelta(days=3) if (product, target) == ("corporativo", "PROPOSAL_SENT") else None
        proposals.send(proposal["id"], now=sent_at)
        if target == "PROPOSAL_ACCEPTED":
            proposals.accept(proposal["id"])
    CrmContainer.get_sdr_task_service().run_proposal_cadence()

    # Contato recorrente: um evento fechado no ano passado e um lead novo agora (página Contatos).
    returning = Customer(name="Cliente Recorrente", phone="5562988880000", company="Construtora Alfa",
                         product="corporativo", customer_state_now="CONTRACT_SIGNED", contract_value=9800,
                         event_date=datetime.utcnow() - timedelta(days=300),
                         created_at=datetime.utcnow() - timedelta(days=330)).save()
    CrmContainer.get_contact_service().start_new_lead(str(returning.id), "social")
    CrmContainer.get_contact_service().import_partners("Nome;Telefone\nCerimonial Lírio;(62) 97777-0000\n")


def run_all():
    call_command("seed_inventory", stdout=StringIO())
    seed_funnel()
