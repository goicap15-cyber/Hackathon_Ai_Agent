# mock_crm/main.py
from fastapi import FastAPI, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import datetime
import json
import os
import csv
import io

from fastapi.middleware.cors import CORSMiddleware
from mock_crm.data import CUSTOMERS, OPPORTUNITIES, INTERACTIONS, CAMPAIGNS

app = FastAPI(title="Bank A CRM Sandbox API", version="1.0.0")

# Enable CORS for frontend client-side API requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Schemas
class InteractionCreate(BaseModel):
    customer_id: str
    type: str  # Call, Email, Meeting
    notes: str
    result: str
    rm_name: str

class OpportunityUpdate(BaseModel):
    stage: str

class EmailDraftCreate(BaseModel):
    customer_id: str
    subject: str
    body: str
    rm_name: str

class CallScriptCreate(BaseModel):
    customer_id: str
    script_content: str
    rm_name: str

# Live customer loader
CUSTOMERS_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "customers.json"))
UNIFIED_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "unified_db.json"))

def _extract_records_from_db(db):
    """Lấy list records từ bất kỳ cấu trúc JSON nào (list, dict với key bất kỳ)."""
    if isinstance(db, list):
        return db
    if isinstance(db, dict):
        # Ưu tiên key quen biết
        for key in ["customers", "records", "data", "items", "rows", "patients", "users"]:
            if key in db and isinstance(db[key], list):
                return db[key]
        # Fallback: lấy list lớn nhất trong dict
        all_lists = [(k, v) for k, v in db.items() if isinstance(v, list)]
        if all_lists:
            return max(all_lists, key=lambda x: len(x[1]))[1]
    return []

def get_live_customers():
    if os.path.exists(UNIFIED_DB_PATH):
        try:
            with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
                return _extract_records_from_db(db)
        except Exception:
            pass
    if os.path.exists(CUSTOMERS_JSON_PATH):
        try:
            with open(CUSTOMERS_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return CUSTOMERS

def find_customer_in_db(customer_id: str):
    db_data = get_database()
    records = _extract_records_from_db(db_data)
    cid_clean = str(customer_id).strip().upper()
    for r in records:
        if not isinstance(r, dict):
            continue
        # Quét toàn bộ value — không cần biết tên cột
        for val in r.values():
            if str(val).strip().upper() == cid_clean:
                return r
    return None

def get_database():
    if os.path.exists(UNIFIED_DB_PATH):
        try:
            with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    fallback_db = {
        "customers": get_live_customers(),
        "products": get_products_fallback(),
        "templates": get_templates_fallback()
    }
    return fallback_db

# Routes
@app.get("/api/customers")
def get_customers(due_within_days: Optional[int] = None):
    """
    Get all customers or filter by savings due date.
    Example: GET /api/customers?due_within_days=7
    """
    live_customers = get_live_customers()
    if due_within_days is None:
        return live_customers
        
    filtered = []
    today = datetime.date(2026, 7, 10)
    
    for c in live_customers:
        if c.get("savings_due_date"):
            try:
                due_date = datetime.datetime.strptime(c["savings_due_date"], "%Y-%m-%d").date()
                delta = (due_date - today).days
                if 0 <= delta <= due_within_days:
                    filtered.append(c)
            except Exception:
                pass
    return filtered

@app.get("/api/customers/{customer_id}")
def get_customer_detail(customer_id: str):
    c = find_customer_in_db(customer_id)
    if c:
        return c
    raise HTTPException(status_code=404, detail="Customer not found")

@app.get("/api/customers/{customer_id}/opportunities")
def get_customer_opportunities(customer_id: str):
    opps = [opp for opp in OPPORTUNITIES if opp["customer_id"] == customer_id]
    return opps

@app.get("/api/customers/{customer_id}/interactions")
def get_customer_interactions(customer_id: str):
    ints = [i for i in INTERACTIONS if i["customer_id"] == customer_id]
    return ints

@app.post("/api/interactions", status_code=status.HTTP_201_CREATED)
def create_interaction(interaction: InteractionCreate):
    new_int = {
        "id": f"INT{len(INTERACTIONS) + 1:03d}",
        "customer_id": interaction.customer_id,
        "type": interaction.type,
        "notes": interaction.notes,
        "result": interaction.result,
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "rm_name": interaction.rm_name
    }
    INTERACTIONS.append(new_int)
    return new_int

@app.patch("/api/opportunities/{opp_id}")
def update_opportunity(opp_id: str, payload: OpportunityUpdate):
    for opp in OPPORTUNITIES:
        if opp["id"] == opp_id:
            opp["stage"] = payload.stage
            return opp
    raise HTTPException(status_code=404, detail="Opportunity not found")

@app.get("/api/campaigns")
def get_campaigns(active_only: bool = True):
    if active_only:
        return [c for c in CAMPAIGNS if c["active"]]
    return CAMPAIGNS

@app.post("/api/draft-email", status_code=status.HTTP_201_CREATED)
def create_draft_email(payload: EmailDraftCreate):
    """
    Simulates saving a generated email draft back into the CRM.
    """
    # Create an interaction entry of type 'Email' to simulate CRM update
    new_int = {
        "id": f"INT{len(INTERACTIONS) + 1:03d}",
        "customer_id": payload.customer_id,
        "type": "Email",
        "notes": f"Bản nháp Email: {payload.subject}\nNội dung: {payload.body[:100]}...",
        "result": "Draft Created",
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "rm_name": payload.rm_name
    }
    INTERACTIONS.append(new_int)
    return {
        "status": "success",
        "message": "Đã lưu bản nháp email vào CRM thành công!",
        "interaction_id": new_int["id"]
    }

@app.post("/api/call-script", status_code=status.HTTP_201_CREATED)
def create_call_script(payload: CallScriptCreate):
    """
    Simulates saving a generated call script back into the CRM.
    """
    # Create an interaction entry of type 'Call' to simulate CRM update
    new_int = {
        "id": f"INT{len(INTERACTIONS) + 1:03d}",
        "customer_id": payload.customer_id,
        "type": "Call",
        "notes": f"Kịch bản cuộc gọi: {payload.script_content[:100]}...",
        "result": "Script Generated",
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "rm_name": payload.rm_name
    }
    INTERACTIONS.append(new_int)
    return {
        "status": "success",
        "message": "Đã lưu kịch bản cuộc gọi vào CRM thành công!",
        "interaction_id": new_int["id"]
    }

PRODUCTS_KB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "products_kb.json"))
TEMPLATES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates.json"))

def get_products_fallback(category: Optional[str] = None):
    if not os.path.exists(PRODUCTS_KB_PATH):
        return []
    with open(PRODUCTS_KB_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)
    if category:
        return [p for p in products if p.get("category", "").lower() == category.lower()]
    return products

def get_templates_fallback(type: Optional[str] = None):
    if not os.path.exists(TEMPLATES_PATH):
        return []
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        templates = json.load(f)
    if type:
        return [t for t in templates if t.get("type", "").lower() == type.lower()]
    return templates

@app.get("/api/products")
def get_products(category: Optional[str] = None):
    if os.path.exists(UNIFIED_DB_PATH):
        try:
            with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
                if isinstance(db, dict) and "products" in db:
                    products = db["products"]
                elif isinstance(db, list):
                    products = db
                else:
                    products = []
                if category:
                    return [p for p in products if str(p.get("category", "")).lower() == category.lower()]
                return products
        except Exception:
            pass
    return get_products_fallback(category)

@app.get("/api/templates")
def get_templates(type: Optional[str] = None):
    if os.path.exists(UNIFIED_DB_PATH):
        try:
            with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
                if isinstance(db, dict) and "templates" in db:
                    templates = db["templates"]
                else:
                    templates = []
                if type:
                    return [t for t in templates if str(t.get("type", "")).lower() == type.lower()]
                return templates
        except Exception:
            pass
    return get_templates_fallback(type)

@app.get("/api/database")
def get_database_route():
    return get_database()

@app.post("/api/upload-database")
async def upload_database(append: bool = False, file: UploadFile = File(...)):
    import traceback
    try:
        contents = await file.read()
        filename = file.filename.lower()

        # Giới hạn kích thước file upload: tối đa 50MB
        MAX_UPLOAD_BYTES = 50 * 1024 * 1024
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File quá lớn! Chỉ hỗ trợ tối đa 50MB.")

        existing_data = None
        if append and os.path.exists(UNIFIED_DB_PATH):
            try:
                file_size = os.path.getsize(UNIFIED_DB_PATH)
                if file_size < 100 * 1024 * 1024:  # Chỉ load nếu < 100MB
                    with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
            except Exception:
                existing_data = None

        if filename.endswith(".csv"):
            try:
                decoded = contents.decode("utf-8-sig")
            except UnicodeDecodeError:
                decoded = contents.decode("latin-1")
            csv_file = io.StringIO(decoded)
            reader = csv.DictReader(csv_file)
            parsed = list(reader)
            
            if append and existing_data is not None:
                if isinstance(existing_data, list):
                    existing_data.extend(parsed)
                    parsed = existing_data
                elif isinstance(existing_data, dict):
                    list_keys = [k for k, v in existing_data.items() if isinstance(v, list)]
                    if list_keys:
                        existing_data[list_keys[0]].extend(parsed)
                    else:
                        existing_data["customers"] = parsed
                    parsed = existing_data
            
            with open(UNIFIED_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            
            if isinstance(parsed, list):
                count = len(parsed)
            else:
                count = sum(len(v) for v in parsed.values() if isinstance(v, list))
            
            return {"status": "success", "message": f"Đã nạp file CSV '{file.filename}' thành công! (Tổng cộng {count} bản ghi trong hệ thống)"}
            
        elif filename.endswith(".json"):
            try:
                parsed = json.loads(contents.decode("utf-8"))
            except json.JSONDecodeError as je:
                raise HTTPException(status_code=400, detail=f"File JSON không hợp lệ: {str(je)}")
            
            if append and existing_data is not None:
                if isinstance(existing_data, list) and isinstance(parsed, list):
                    existing_data.extend(parsed)
                    parsed = existing_data
                elif isinstance(existing_data, dict) and isinstance(parsed, dict):
                    for key, val in parsed.items():
                        if key in existing_data and isinstance(existing_data[key], list) and isinstance(val, list):
                            existing_data[key].extend(val)
                        else:
                            existing_data[key] = val
                    parsed = existing_data
                elif isinstance(existing_data, dict) and isinstance(parsed, list):
                    list_keys = [k for k, v in existing_data.items() if isinstance(v, list)]
                    if list_keys:
                        existing_data[list_keys[0]].extend(parsed)
                    else:
                        existing_data["customers"] = parsed
                    parsed = existing_data
                elif isinstance(existing_data, list) and isinstance(parsed, dict):
                    # Nếu data cũ là list, wrap lại thành dict
                    parsed["_legacy"] = existing_data
            
            with open(UNIFIED_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            
            if isinstance(parsed, list):
                count = len(parsed)
            elif isinstance(parsed, dict):
                count = sum(len(v) for v in parsed.values() if isinstance(v, list))
                if count == 0:
                    count = len(parsed)
            else:
                count = 1
            return {"status": "success", "message": f"Đã nạp file JSON '{file.filename}' thành công! (Tổng cộng {count} bản ghi trong hệ thống)"}
            
        else:
            raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tải lên file định dạng .json hoặc .csv")
    except HTTPException:
        raise  # Không bắt nhầm HTTPException – để FastAPI xử lý đúng status code
    except Exception as e:
        traceback.print_exc()  # In traceback ra server log để debug
        raise HTTPException(status_code=400, detail=f"Lỗi nạp file dữ liệu: {str(e)}")

@app.delete("/api/database")
def delete_database():
    deleted_any = False
    for path in [UNIFIED_DB_PATH, CUSTOMERS_JSON_PATH, PRODUCTS_KB_PATH, TEMPLATES_PATH]:
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted_any = True
            except Exception:
                pass
    if deleted_any:
        return {"status": "success", "message": "Đã xóa toàn bộ CSDL tùy biến. Hệ thống quay về dữ liệu mặc định của Bank A!"}
    return {"status": "success", "message": "Dữ liệu tùy biến trống. Đang sử dụng dữ liệu mặc định."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
