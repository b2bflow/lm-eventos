from celery import shared_task

from utils.logger import logger


@shared_task
def create_stale_lead_tasks():
    """Lead em NEW_LEAD sem mensagem do cliente há 24 h: tarefa `retomar_lead_parado` para a SDR."""
    from crm.container import CrmContainer
    created = CrmContainer.get_sdr_task_service().create_stale_lead_tasks()
    logger.info(f"[crm.tasks] Tarefas de lead parado criadas: {created}")
    return created


@shared_task
def run_sdr_cadence():
    """Cadência depois da proposta (D+1, D+3, D+5, perda em D+7) e tarefa de reunião amanhã."""
    from crm.container import CrmContainer
    service = CrmContainer.get_sdr_task_service()
    result = service.run_proposal_cadence()
    result["meetings"] = service.create_meeting_tasks()
    logger.info(f"[crm.tasks] Cadência da SDR: {result}")
    return result
