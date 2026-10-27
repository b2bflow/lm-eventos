"""Repetição de compromissos, no mesmo modelo do Google Agenda.

A regra trafega na API como dicionário:
    {"freq": "daily|weekly|monthly|yearly", "interval": 1, "by_weekday": [0..6] (Seg=0, só semanal),
     "monthly": "day|weekday|last_weekday" (só mensal), "until": "AAAA-MM-DD" | None, "count": int | None}
e vira RRULE (RFC 5545) para o Google. As datas são expandidas no horário de Brasília; a semana começa
no domingo (WKST=SU) dos dois lados, para "a cada 2 semanas" cair nos mesmos dias aqui e no Google.
"""
from datetime import date, datetime, time, timedelta

from dateutil import rrule as dr

from crm.services.business_hours import to_local, to_utc_naive

FREQS = {"daily": dr.DAILY, "weekly": dr.WEEKLY, "monthly": dr.MONTHLY, "yearly": dr.YEARLY}
MONTHLY_MODES = ("day", "weekday", "last_weekday")
WEEKDAYS = [dr.MO, dr.TU, dr.WE, dr.TH, dr.FR, dr.SA, dr.SU]
RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_COUNT = 730
MAX_INTERVAL = 99


def clean_rule(rule: dict | None, start_utc: datetime) -> dict | None:
    """Valida e normaliza a regra vinda do formulário. None = não se repete."""
    if not rule:
        return None
    if not isinstance(rule, dict) or rule.get("freq") not in FREQS:
        raise ValueError("Repetição inválida.")
    local = to_local(start_utc)
    try:
        interval = int(rule.get("interval") or 1)
    except (TypeError, ValueError):
        raise ValueError("Intervalo da repetição inválido.")
    if not 1 <= interval <= MAX_INTERVAL:
        raise ValueError(f"O intervalo da repetição vai de 1 a {MAX_INTERVAL}.")
    clean = {"freq": rule["freq"], "interval": interval, "until": None, "count": None}
    if rule["freq"] == "weekly":
        days = sorted({int(d) for d in (rule.get("by_weekday") or [local.weekday()]) if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            raise ValueError("Escolha ao menos um dia da semana.")
        clean["by_weekday"] = days
    if rule["freq"] == "monthly":
        mode = rule.get("monthly") or "day"
        if mode not in MONTHLY_MODES:
            raise ValueError("Repetição mensal inválida.")
        clean["monthly"] = mode
    if rule.get("until") and rule.get("count"):
        raise ValueError("Escolha só uma forma de terminar a repetição.")
    if rule.get("until"):
        try:
            until = date.fromisoformat(str(rule["until"])[:10])
        except ValueError:
            raise ValueError("Data final da repetição inválida.")
        if until < local.date():
            raise ValueError("A repetição não pode terminar antes do primeiro dia.")
        clean["until"] = until.isoformat()
    if rule.get("count"):
        try:
            count = int(rule["count"])
        except (TypeError, ValueError):
            raise ValueError("Número de ocorrências inválido.")
        if not 1 <= count <= MAX_COUNT:
            raise ValueError(f"O número de ocorrências vai de 1 a {MAX_COUNT}.")
        clean["count"] = count
    return clean


def _nth_weekday(day: date) -> int:
    return (day.day - 1) // 7 + 1


def _rrule(rule: dict, start_local: datetime) -> dr.rrule:
    kwargs = {"dtstart": start_local, "interval": rule.get("interval") or 1, "wkst": dr.SU}
    freq = rule["freq"]
    if freq == "weekly":
        kwargs["byweekday"] = [WEEKDAYS[d] for d in rule.get("by_weekday") or [start_local.weekday()]]
    elif freq == "monthly":
        mode = rule.get("monthly") or "day"
        weekday = WEEKDAYS[start_local.weekday()]
        if mode == "weekday":
            kwargs["byweekday"] = weekday(+_nth_weekday(start_local.date()))
        elif mode == "last_weekday":
            kwargs["byweekday"] = weekday(-1)
        else:
            kwargs["bymonthday"] = start_local.day
    elif freq == "yearly":
        kwargs.update(bymonth=start_local.month, bymonthday=start_local.day)
    if rule.get("until"):
        kwargs["until"] = datetime.combine(date.fromisoformat(rule["until"]), time(23, 59, 59))
    if rule.get("count"):
        kwargs["count"] = rule["count"]
    return dr.rrule(FREQS[freq], **kwargs)


def occurrence_starts(rule: dict, first_start_utc: datetime, until_utc: datetime,
                      after_utc: datetime | None = None) -> list[datetime]:
    """Inícios (UTC) das ocorrências até `until_utc`, só os depois de `after_utc` se informado.
    O primeiro início é o primeiro dia que bate com a regra (como o Google faz)."""
    start_local = to_local(first_start_utc).replace(tzinfo=None)
    window_start = to_local(after_utc).replace(tzinfo=None) if after_utc else start_local
    window_end = to_local(until_utc).replace(tzinfo=None)
    if window_end < window_start:
        return []
    starts = [to_utc_naive(dt) for dt in _rrule(rule, start_local).between(window_start, window_end, inc=True)]
    return [s for s in starts if after_utc is None or s > after_utc]


def to_rrule(rule: dict, start_utc: datetime, all_day: bool = False) -> list[str]:
    """Regra -> campo `recurrence` do evento no Google."""
    local = to_local(start_utc)
    parts = [f"FREQ={rule['freq'].upper()}", "WKST=SU"]
    if (rule.get("interval") or 1) > 1:
        parts.append(f"INTERVAL={rule['interval']}")
    if rule["freq"] == "weekly":
        parts.append("BYDAY=" + ",".join(RRULE_DAYS[d] for d in rule.get("by_weekday") or [local.weekday()]))
    elif rule["freq"] == "monthly":
        mode = rule.get("monthly") or "day"
        day = RRULE_DAYS[local.weekday()]
        if mode == "weekday":
            parts.append(f"BYDAY={_nth_weekday(local.date())}{day}")
        elif mode == "last_weekday":
            parts.append(f"BYDAY=-1{day}")
        else:
            parts.append(f"BYMONTHDAY={local.day}")
    if rule.get("until"):
        until = date.fromisoformat(rule["until"])
        if all_day:
            parts.append(f"UNTIL={until:%Y%m%d}")
        else:
            parts.append(f"UNTIL={to_utc_naive(datetime.combine(until, time(23, 59, 59))):%Y%m%dT%H%M%SZ}")
    if rule.get("count"):
        parts.append(f"COUNT={rule['count']}")
    return ["RRULE:" + ";".join(parts)]


def instance_id(master_id: str, original_start_utc: datetime, all_day: bool = False) -> str:
    """Id da ocorrência no Google: id do evento repetido + início original (UTC, ou a data se dia inteiro)."""
    if all_day:
        return f"{master_id}_{to_local(original_start_utc):%Y%m%d}"
    return f"{master_id}_{original_start_utc:%Y%m%dT%H%M%SZ}"


def truncate_before(rule: dict, cut_utc: datetime) -> dict:
    """Regra que para na véspera de `cut_utc` (o "este e os seguintes" do Google corta a série ali)."""
    return {**rule, "count": None, "until": (to_local(cut_utc).date() - timedelta(days=1)).isoformat()}


def remaining_count(rule: dict, first_start_utc: datetime, cut_utc: datetime) -> dict:
    """Mesma regra a partir de `cut_utc`: se terminava após N ocorrências, desconta as que ficaram antes."""
    if not rule.get("count"):
        return dict(rule)
    before = len(occurrence_starts(rule, first_start_utc, cut_utc - timedelta(seconds=1)))
    return {**rule, "count": max(1, rule["count"] - before)}
