"""Horários livres na agenda da Erica para a IA oferecer ao cliente (reunião com o time técnico).

Regra (reunião com o Marcelo, 28/10): sempre dois horários. Candidatos de meia em meia hora, dentro do
horário comercial (LmSettings.business_hours), a partir de 1 h depois de agora, sem cair em bloqueio,
reunião, visita ou compromisso do Google. O segundo fica pelo menos 2 h depois do primeiro, para o
cliente ter opções diferentes de verdade.
"""
from datetime import date, datetime, time, timedelta

from crm.models.lm_settings_model import LmSettings
from crm.services.business_hours import day_window, to_local, to_utc_naive
from utils.logger import logger

MEETING_MINUTES = 40
LEAD_TIME = timedelta(hours=1)
STEP = timedelta(minutes=30)
GAP_BETWEEN_OPTIONS = timedelta(hours=2)
SEARCH_DAYS = 10

WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def _round_up(local_dt: datetime) -> datetime:
    extra = local_dt.minute % 30
    rounded = local_dt.replace(second=0, microsecond=0)
    if extra or local_dt.second or local_dt.microsecond:
        rounded += timedelta(minutes=30 - extra)
    return rounded


def _candidates(business_hours: dict, now_utc: datetime, duration: timedelta):
    """Inícios possíveis (UTC sem fuso), em ordem, dentro do horário comercial."""
    earliest = _round_up(to_local(now_utc + LEAD_TIME))
    for offset in range(SEARCH_DAYS):
        day = earliest.date() + timedelta(days=offset)
        window = day_window(business_hours, datetime.combine(day, time()))
        if not window:
            continue
        start = datetime.combine(day, window[0], tzinfo=earliest.tzinfo)
        close = datetime.combine(day, window[1], tzinfo=earliest.tzinfo)
        start = max(start, earliest)
        while start + duration <= close:
            yield to_utc_naive(start)
            start += STEP


def next_free_slots(count: int = 2, now: datetime | None = None, minutes: int = MEETING_MINUTES,
                    agenda=None) -> list[datetime]:
    """Até `count` inícios livres (UTC sem fuso). Lista vazia se a agenda não puder ser lida."""
    now = now or datetime.utcnow()
    duration = timedelta(minutes=minutes)
    try:
        if agenda is None:
            from agenda.services.agenda_service import AgendaService
            agenda = AgendaService()
        business_hours = LmSettings.get().business_hours or {}
        found: list[datetime] = []
        for start in _candidates(business_hours, now, duration):
            if found and start < found[-1] + GAP_BETWEEN_OPTIONS:
                continue
            if agenda.conflicts(start, start + duration):
                continue
            found.append(start)
            if len(found) == count:
                break
        return found
    except Exception as e:
        logger.error(f"[FreeSlots] Não foi possível ler a agenda: {e}")
        return []


def _hour(local_dt: datetime) -> str:
    return f"{local_dt.hour}h" if local_dt.minute == 0 else f"{local_dt.hour}h{local_dt.minute:02d}"


def describe_slot(start_utc: datetime, now: datetime | None = None) -> str:
    """'hoje às 15h', 'amanhã às 9h30', 'quinta-feira (30/10) às 10h' (horário de Brasília)."""
    local = to_local(start_utc)
    today: date = to_local(now or datetime.utcnow()).date()
    if local.date() == today:
        day = "hoje"
    elif local.date() == today + timedelta(days=1):
        day = "amanhã"
    else:
        day = f"{WEEKDAYS[local.weekday()]} ({local:%d/%m})"
    return f"{day} às {_hour(local)}"
