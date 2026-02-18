def only_numbers(value: str) -> str:
    if not value:
        return value

    return "".join(filter(str.isdigit, value))


def format_phone(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return value


def format_cpf(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return value


def format_cnpj(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return value


def format_date(value: str) -> str:
    if not value:
        return value

    try:
        year, month, day = map(int, value.split("-"))
        return f"{day:02d}/{month:02d}/{year:04d}"
    except ValueError:
        return value
