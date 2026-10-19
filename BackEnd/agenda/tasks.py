from celery import shared_task

from utils.logger import logger


@shared_task
def sync_google_calendar():
    """Lê a agenda principal da conta Contato LM (incremental) para a página Agenda."""
    from agenda.services.agenda_service import AgendaService
    from agenda.services.google_calendar_client import is_configured
    if not is_configured():
        return "google-nao-conectado"
    result = AgendaService().sync_from_google()
    logger.info(f"[agenda.tasks] Sincronização Google: {result}")
    return result


@shared_task
def send_agenda_reminders():
    """Lembretes de reunião e visita para cliente e Erica, 24 h e 2 h antes."""
    from agenda.services.agenda_service import AgendaService
    return AgendaService().send_reminders()
