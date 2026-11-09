"""Horários livres na agenda da Erica para a IA oferecer ao cliente (reunião com o time técnico).

Regra (reunião com o Marcelo, 28/10): sempre dois horários. Candidatos de meia em meia hora, dentro do
horário de reuniões (MEETING_HOURS), a partir de 1 h depois de agora, sem cair em bloqueio, reunião,
visita ou compromisso do Google. O segundo fica pelo menos 2 h depois do primeiro, para o cliente ter
opções diferentes de verdade.

Folga (05/11): o horário oferecido fica a pelo menos 30 min do começo e do fim de qualquer compromisso
já marcado. Ex.: reunião às 12:00-13:00 -> não oferece 11:00 nem 13:00; oferece 10:30 e 13:30. Os inícios
são sempre em hora cheia ou meia hora.

Duração: para o cliente a reunião é de 40 min (MEETING_MINUTES, na mensagem), mas na agenda da Erica ela
ocupa 1 h (AGENDA_MINUTES): é essa duração que precisa caber no horário de reuniões e respeitar a folga.

Horário de reuniões (09/11): de segunda a sexta, das 9h às 19h (último início 18:00). Sábado e domingo não.
"""
from datetime import date, datetime, time, timedelta

from crm.services.business_hours import day_window, to_local, to_utc_naive
from utils.logger import logger

MEETING_MINUTES = 40  # o que a mensagem diz ao cliente
AGENDA_MINUTES = 60  # o que a reunião ocupa na agenda da Erica
LEAD_TIME = timedelta(hours=1)  # antecedência dos horários que a IA oferece
MIN_NOTICE = timedelta(minutes=30)  # antecedência mínima para marcar um horário que o cliente escolheu
STEP = timedelta(minutes=30)
GAP_BETWEEN_OPTIONS = timedelta(hours=2)
BUFFER = timedelta(minutes=30)  # distância mínima de compromissos já marcados, antes e depois
SEARCH_DAYS = 10

# Dia da semana (0 = segunda) -> [início, fim] das reuniões; None = sem reunião.
MEETING_HOURS = {
    "0": ["09:00", "19:00"], "1": ["09:00", "19:00"], "2": ["09:00", "19:00"],
    "3": ["09:00", "19:00"], "4": ["09:00", "19:00"], "5": None, "6": None,
}

# Período que o cliente pede ("só consigo à tarde"), pelo horário de início.
PERIODS = {"manha": (time(0), time(12)), "tarde": (time(12), time(18)), "noite": (time(18), time(23, 59))}
PERIOD_LABELS = {"manha": "manhã", "tarde": "tarde", "noite": "noite"}

WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")

# Motivos de check_slot.
PAST, CLOSED, NOT_ROUND, BUSY = "passado", "fora_do_horario", "minuto_quebrado", "ocupado"


def _round_up(local_dt: datetime) -> datetime:
    extra = local_dt.minute % 30
    rounded = local_dt.replace(second=0, microsecond=0)
    if extra or local_dt.second or local_dt.microsecond:
        rounded += timedelta(minutes=30 - extra)
    return rounded


def _window(day: date) -> tuple[time, time] | None:
    return day_window(MEETING_HOURS, datetime.combine(day, time()))


def _candidates(now_utc: datetime, duration: timedelta, day: date | None = None):
    """Inícios possíveis (UTC sem fuso), em ordem, dentro do horário de reuniões."""
    earliest = _round_up(to_local(now_utc + LEAD_TIME))
    days = [day] if day else [earliest.date() + timedelta(days=offset) for offset in range(SEARCH_DAYS)]
    for current in days:
        window = _window(current)
        if not window or current < earliest.date():
            continue
        start = datetime.combine(current, window[0], tzinfo=earliest.tzinfo)
        close = datetime.combine(current, window[1], tzinfo=earliest.tzinfo)
        start = max(start, earliest)
        while start + duration <= close:
            yield to_utc_naive(start)
            start += STEP


def _in_period(start_utc: datetime, period: str | None) -> bool:
    if not period or period not in PERIODS:
        return True
    begin, end = PERIODS[period]
    return begin <= to_local(start_utc).time() < end


def _agenda(agenda):
    if agenda is None:
        from agenda.services.agenda_service import AgendaService
        agenda = AgendaService()
    return agenda


def _busy(agenda, start: datetime, duration: timedelta) -> bool:
    return bool(agenda.conflicts(start - BUFFER, start + duration + BUFFER))


def next_free_slots(count: int = 2, now: datetime | None = None, minutes: int = AGENDA_MINUTES,
                    agenda=None, period: str | None = None, day: date | None = None,
                    exclude=()) -> list[datetime]:
    """Até `count` inícios livres (UTC sem fuso), opcionalmente só num período ("manha", "tarde", "noite")
    ou num dia (horário de Brasília), sem repetir `exclude`. Lista vazia se a agenda não puder ser lida."""
    now = now or datetime.utcnow()
    duration = timedelta(minutes=minutes)
    skip = set(exclude or ())
    try:
        agenda = _agenda(agenda)
        found: list[datetime] = []
        for start in _candidates(now, duration, day):
            if start in skip or not _in_period(start, period):
                continue
            if found and start < found[-1] + GAP_BETWEEN_OPTIONS:
                continue
            if _busy(agenda, start, duration):
                continue
            found.append(start)
            if len(found) == count:
                break
        return found
    except Exception as e:
        logger.error(f"[FreeSlots] Não foi possível ler a agenda: {e}")
        return []


def check_slot(start_utc: datetime, now: datetime | None = None, minutes: int = AGENDA_MINUTES,
               agenda=None) -> str | None:
    """None se dá para marcar a reunião nesse início; senão o motivo (PAST, CLOSED, NOT_ROUND, BUSY)."""
    now = now or datetime.utcnow()
    duration = timedelta(minutes=minutes)
    if start_utc < now + MIN_NOTICE:
        return PAST
    local = to_local(start_utc)
    if local.minute not in (0, 30) or local.second or local.microsecond:
        return NOT_ROUND
    window = _window(local.date())
    if not window or local.time() < window[0] or (local + duration).time() > window[1] \
            or (local + duration).date() != local.date():
        return CLOSED
    if _busy(_agenda(agenda), start_utc, duration):
        return BUSY
    return None


def _hour(local_dt: datetime) -> str:
    return f"{local_dt.hour}h" if local_dt.minute == 0 else f"{local_dt.hour}h{local_dt.minute:02d}"


def describe_day(day: date, now: datetime | None = None) -> str:
    """'hoje', 'amanhã' ou 'quinta-feira (30/10)'."""
    today: date = to_local(now or datetime.utcnow()).date()
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return "amanhã"
    return f"{WEEKDAYS[day.weekday()]} ({day:%d/%m})"


def describe_slot(start_utc: datetime, now: datetime | None = None) -> str:
    """'hoje às 15h', 'amanhã às 9h30', 'quinta-feira (30/10) às 10h' (horário de Brasília)."""
    local = to_local(start_utc)
    return f"{describe_day(local.date(), now)} às {_hour(local)}"
