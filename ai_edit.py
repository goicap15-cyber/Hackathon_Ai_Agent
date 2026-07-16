import os, sys, re
from pathlib import Path
from openai import OpenAI

if len(sys.argv) < 3:
    print('Cách dùng: python ai_edit.py <file> "<mô tả việc cần làm>"')
    sys.exit(1)

target = Path(sys.argv[1])
task = sys.argv[2]
if not target.exists():
    print(f"Không tìm thấy file: {target}"); sys.exit(1)

original = target.read_text(encoding="utf-8")
client = OpenAI(base_url="http://127.0.0.1:1994/v1",
                api_key=os.getenv("NOTIONCHAT_API_KEY", "notion"))
model_id = os.getenv("NOTIONCHAT_MODEL") or client.models.list().data[0].id
print(f"Model: {model_id}\nFile:  {target}\nViệc:  {task}")

START, END = "===FILE_START===", "===FILE_END==="
prompt = f"""Bạn là senior Python developer. Sửa file dưới đây theo ĐÚNG yêu cầu.

YÊU CẦU CỤ THỂ:
{task}

QUY ĐỊNH BẮT BUỘC:
1. KHÔNG xóa import/hàm/class/logic nào đang có. Giữ 100% chức năng cũ.
2. Chỉ thực hiện đúng yêu cầu trên, không tự ý làm thêm việc khác.
3. Xuất TOÀN BỘ nội dung file sau khi sửa, bọc giữa 2 mốc:
{START}
<toàn bộ file>
{END}
4. TUYỆT ĐỐI không viết giải thích/tóm tắt/markdown fence.

--- FILE: {target} ---
{original}
"""
resp = client.chat.completions.create(model=model_id,
        messages=[{"role": "user", "content": prompt}])
raw = resp.choices[0].message.content or ""
new = raw.split(START,1)[1].split(END,1)[0] if (START in raw and END in raw) else raw
new = re.sub(r"^```[a-zA-Z]*\n", "", new.strip())
new = re.sub(r"\n```$", "", new).strip() + "\n"
if len(new) < len(original) * 0.5:
    print(f"⚠️ Nội dung mới quá ngắn ({len(new)} vs {len(original)}). KHÔNG ghi.")
    print(raw[:500]); sys.exit(1)
target.write_text(new, encoding="utf-8")
print("Đã ghi lại file. Dùng 'git diff' để xem.")
