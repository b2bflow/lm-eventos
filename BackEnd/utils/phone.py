import os
import re


def normalize_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and not digits.startswith("55"):
        return f"55{digits}"
    return digits


def get_employee_phones() -> set[str]:
    raw_phones = os.getenv("EMPLOYEE_PHONES", "")
    return {
        normalized
        for normalized in (normalize_phone(phone.strip()) for phone in raw_phones.split(","))
        if normalized
    }


def is_employee_phone(phone: str | None) -> bool:
    normalized_phone = normalize_phone(phone)
    return bool(normalized_phone and normalized_phone in get_employee_phones())
