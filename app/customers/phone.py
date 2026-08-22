import re


class InvalidPhoneNumberError(ValueError):
    pass


_FORMATTING_CHARACTERS = re.compile(r"[\s().-]")
_E164_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(phone: str) -> str:
    """Return a formatted phone number in a conservative E.164 representation."""
    normalized = _FORMATTING_CHARACTERS.sub("", phone.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if not _E164_PHONE.fullmatch(normalized):
        raise InvalidPhoneNumberError(
            "Phone must be an international number with 8 to 15 digits"
        )
    return normalized
