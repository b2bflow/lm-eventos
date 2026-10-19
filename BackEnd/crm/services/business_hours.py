"""Horário comercial da LM. Datas entram e saem em UTC sem fuso (padrão do banco); as regras
são avaliadas no horário de Brasília (settings.LM_TIMEZONE)."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from django.conf import settings as django_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(getattr(django_settings, "LM_TIMEZONE", "America/Sao_Paulo"))


def to_local(utc_naive: datetime) -> datetime:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(local_tz())


def to_utc_naive(local_dt: datetime) -> datetime:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=local_tz())
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def day_window(business_hours: dict, day: datetime) -> tuple[time, time] | None:
    window = business_hours.get(str(day.weekday()))
    if not window:
        return None
    return _parse_hhmm(window[0]), _parse_hhmm(window[1])


def is_business_time(business_hours: dict, utc_naive: datetime) -> bool:
    local = to_local(utc_naive)
    window = day_window(business_hours, local)
    return bool(window) and window[0] <= local.time() < window[1]


def business_slot(business_hours: dict, local_day: date, preferred_hour: str = "09:00",
                  not_before_utc: datetime | None = None) -> datetime | None:
    """Primeiro horário útil a partir de `local_day` (às `preferred_hour`, ou na abertura se o
    dia abrir depois disso), posterior a `not_before_utc`. Devolve UTC sem fuso."""
    preferred = _parse_hhmm(preferred_hour)
    not_before = to_local(not_before_utc) if not_before_utc else None
    for offset in range(0, 8):
        day = local_day + timedelta(days=offset)
        window = day_window(business_hours, datetime.combine(day, time()))
        if not window:
            continue
        start = max(preferred, window[0])
        if start >= window[1]:
            start = window[0]
        candidate = datetime.combine(day, start, tzinfo=local_tz())
        if not_before is None or candidate > not_before:
            return to_utc_naive(candidate)
    return None


def first_call_due(business_hours: dict, now_utc: datetime, sla_minutes: int, first_call_hour: str = "09:00") -> datetime:
    """Prazo da primeira ligação: agora + SLA no horário comercial; fora dele, a primeira
    ligação do próximo dia útil (às 9h, ou na abertura se o dia abrir depois disso)."""
    if is_business_time(business_hours, now_utc):
        return now_utc + timedelta(minutes=sla_minutes)
    slot = business_slot(business_hours, to_local(now_utc).date(), first_call_hour, not_before_utc=now_utc)
    return slot or now_utc + timedelta(minutes=sla_minutes)
