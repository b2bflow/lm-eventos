"""Agenda do Celery beat.

Cada entrada aponta para uma task registrada com @shared_task em <app>/tasks.py
(o Celery descobre via app.autodiscover_tasks()). Horários em America/Sao_Paulo.
"""
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE: dict = {
    # Lead novo sem mensagem do cliente há 24 h vira tarefa da SDR
    "crm-stale-leads": {
        "task": "crm.tasks.create_stale_lead_tasks",
        "schedule": crontab(minute=5),  # de hora em hora
    },
    # Follow-up D+1/D+3/D+5 da proposta, perda automática em D+7 e reunião amanhã
    "crm-sdr-cadence": {
        "task": "crm.tasks.run_sdr_cadence",
        "schedule": crontab(minute="*/30"),
    },
    # Proposta enviada há mais de 5 dias vira vencida
    "sales-expire-proposals": {
        "task": "sales.tasks.expire_proposals",
        "schedule": crontab(minute=15),
    },
    # Google Agenda -> plataforma (incremental)
    "agenda-sync-google": {
        "task": "agenda.tasks.sync_google_calendar",
        "schedule": crontab(minute="*/10"),
    },
    # Lembretes de reunião e visita (24 h e 2 h antes)
    "agenda-reminders": {
        "task": "agenda.tasks.send_agenda_reminders",
        "schedule": crontab(minute="*/15"),
    },
}
