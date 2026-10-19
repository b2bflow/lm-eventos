"""Telefones de contato: normalização e variantes para não duplicar o mesmo número.

O WhatsApp (Z-API) manda números brasileiros só com dígitos e DDI ("5562999991111"), mas
celulares antigos às vezes chegam sem o nono dígito ("556299991111"). As duas formas são o
mesmo contato.
"""
import re


def normalize_phone(raw) -> str | None:
    """Só dígitos, com DDI. Número brasileiro sem DDI (10 ou 11 dígitos) ganha o 55.
    Devolve None se não parecer um telefone."""
    digits = re.sub(r"\D", "", str(raw or "")).lstrip("0")
    if len(digits) in (10, 11):
        digits = "55" + digits
    if digits.startswith("55"):
        return digits if len(digits) in (12, 13) else None
    return digits if 11 <= len(digits) <= 15 else None


def phone_variants(phone: str | None) -> list[str]:
    """Formas equivalentes do número (com e sem o nono dígito do celular brasileiro)."""
    if not phone:
        return []
    variants = [phone]
    if phone.isdigit() and phone.startswith("55"):
        if len(phone) == 13 and phone[4] == "9":
            variants.append(phone[:4] + phone[5:])
        elif len(phone) == 12 and phone[4] in "6789":
            variants.append(phone[:4] + "9" + phone[4:])
    return variants
