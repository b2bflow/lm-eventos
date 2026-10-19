from celery import shared_task

from utils.logger import logger


@shared_task
def expire_proposals():
    """Proposta enviada há mais de 5 dias (validade) passa para vencida."""
    from sales.services.proposal_service import ProposalService
    count = ProposalService().expire()
    logger.info(f"[sales.tasks] Propostas vencidas: {count}")
    return count
