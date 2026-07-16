from enum import Enum

class Role(str, Enum):
    ACCOUNTANT = "accountant"
    WAREHOUSE  = "warehouse"
    AUDITOR    = "auditor"
    ADMIN      = "admin"

# Trường nhạy cảm khớp schema thật của mock_crm/unified_db.json
SENSITIVE_FIELDS = {
    # thẻ / tài khoản
    "credit_card", "debit_card", "card_number",
    "bank_account", "bank_account_number", "iban", "cvv",
    # PII & tài chính cá nhân
    "date_of_birth",
    "monthly_income_vnd",
    "outstanding_balance_vnd",
    "principal_amount_vnd",
    "kyc_status",
    "occupation",
}

ROLE_CAN_VIEW_SENSITIVE = {
    Role.ACCOUNTANT: True,
    Role.WAREHOUSE:  False,   # kho KHÔNG xem dữ liệu tài chính/PII
    Role.AUDITOR:    True,    # kiểm toán read-only toàn bộ
    Role.ADMIN:      True,
}

def _mask(value) -> str:
    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:            # số thẻ/tài khoản -> giữ 4 số cuối
        return "••••" + s[-4:]
    return "[đã ẩn theo quyền]"     # PII khác -> ẩn hoàn toàn

def mask_record(record: dict, role: str) -> dict:
    try:
        allowed = ROLE_CAN_VIEW_SENSITIVE.get(Role(role), False)
    except ValueError:
        allowed = False
    if allowed:
        return record
    return {k: (_mask(v) if k.lower() in SENSITIVE_FIELDS else v)
            for k, v in record.items()}

def mask_records(records: list, role: str) -> list:
    return [mask_record(r, role) for r in records]
