from enum import Enum

class Role(str, Enum):
    ACCOUNTANT = "accountant"
    WAREHOUSE  = "warehouse"
    AUDITOR    = "auditor"
    ADMIN      = "admin"

# Các trường nhạy cảm (tên tuỳ schema thật của bạn)
SENSITIVE_FIELDS = {
    "bank_account", "so_tai_khoan", "bank_account_number",
    "iban", "card_number", "cvv",
}

ROLE_CAN_VIEW_SENSITIVE = {
    Role.ACCOUNTANT: True,
    Role.WAREHOUSE:  False,
    Role.AUDITOR:    True,
    Role.ADMIN:      True,
}

def _mask(value) -> str:
    s = str(value)
    return "••••" + s[-4:] if len(s) > 4 else "••••"

def mask_record(record: dict, role: str) -> dict:
    try:
        allowed = ROLE_CAN_VIEW_SENSITIVE.get(Role(role), False)
    except ValueError:
        allowed = False
    if allowed:
        return record
    out = {}
    for k, v in record.items():
        out[k] = _mask(v) if k.lower() in SENSITIVE_FIELDS else v
    return out

def mask_records(records: list, role: str) -> list:
    return [mask_record(r, role) for r in records]
