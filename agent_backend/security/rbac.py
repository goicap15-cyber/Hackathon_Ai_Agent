from enum import Enum

class Role(str, Enum):
    RM         = "rm"          # Nhân viên QHKH — hạn chế
    MANAGER    = "manager"     # Quản lý — giám sát, xem rộng hơn
    ACCOUNTANT = "accountant"
    WAREHOUSE  = "warehouse"
    AUDITOR    = "auditor"
    ADMIN      = "admin"

# Trường nhạy cảm khớp schema thật của mock_crm/unified_db.json
SENSITIVE_FIELDS = {
    "credit_card", "debit_card", "card_number",
    "bank_account", "bank_account_number", "iban", "cvv",
    "date_of_birth",
    "monthly_income_vnd",
    "outstanding_balance_vnd",
    "principal_amount_vnd",
    "kyc_status",
    "occupation",
}

# Ai được xem GIÁ TRỊ THẬT của trường nhạy cảm.
# Least-privilege: vai trò không khai báo -> False (bị mask).
ROLE_CAN_VIEW_SENSITIVE = {
    Role.RM:         False,
    Role.MANAGER:    True,
    Role.ACCOUNTANT: True,
    Role.WAREHOUSE:  False,
    Role.AUDITOR:    True,
    Role.ADMIN:      True,
}

def _mask(value) -> str:
    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return "••••" + s[-4:]
    return "[đã ẩn theo quyền]"

def can_view_sensitive(role: str) -> bool:
    try:
        return ROLE_CAN_VIEW_SENSITIVE.get(Role(role), False)
    except ValueError:
        return False

def mask_record(record: dict, role: str) -> dict:
    if can_view_sensitive(role):
        return record
    return {k: (_mask(v) if k.lower() in SENSITIVE_FIELDS else v)
            for k, v in record.items()}

def mask_records(records: list, role: str) -> list:
    return [mask_record(r, role) for r in records]
