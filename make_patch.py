import os
from pathlib import Path
from openai import OpenAI

project = Path.cwd()

# Chỉ những file trong danh sách này mới được gửi cho AI
files_to_edit = [
    "README.md",
    "ARCHITECTURE.md",
    "run.py",
]

sections = []

for relative_path in files_to_edit:
    file_path = project / relative_path

    if not file_path.is_file():
        print(f"Bỏ qua vì không tìm thấy: {relative_path}")
        continue

    content = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    # Giới hạn kích thước từng file
    content = content[:30_000]

    sections.append(
        f"\n===== FILE: {relative_path} =====\n{content}\n"
    )

if not sections:
    raise SystemExit("Không tìm thấy file nào để chỉnh sửa.")

api_key = os.getenv("NOTIONCHAT_API_KEY")

if not api_key:
    raise SystemExit(
        "Chưa có NOTIONCHAT_API_KEY. Hãy source file .env trước."
    )

client = OpenAI(
    base_url="http://127.0.0.1:1994/v1",
    api_key=api_key,
)

models = client.models.list().data

if not models:
    raise SystemExit("Không tìm thấy model khả dụng.")

model_id = os.getenv("NOTIONCHAT_MODEL") or models[0].id
print(f"Đang sử dụng model: {model_id}")

prompt = f"""
Hãy sửa những lỗi quan trọng trong các file được cung cấp dưới đây.

Quy định bắt buộc:
1. Chỉ sửa những file được cung cấp.
2. Không tạo hoặc suy đoán nội dung file khác.
3. Chỉ trả về Git unified diff hợp lệ.
4. Không đặt diff bên trong Markdown code fence.
5. Không giải thích trước hoặc sau diff.
6. Đường dẫn phải ở dạng:
   --- a/path/to/file
   +++ b/path/to/file
7. Giữ thay đổi nhỏ, rõ ràng và có thể kiểm tra được.

Nội dung các file:

{''.join(sections)}
"""

response = client.chat.completions.create(
    model=model_id,
    messages=[
        {
            "role": "user",
            "content": prompt,
        }
    ],
    stream=False,
)

patch = response.choices[0].message.content or ""
patch = patch.strip()

# Xóa Markdown fence nếu model vẫn thêm vào
lines = patch.splitlines()

if lines and lines[0].strip().startswith("```"):
    lines = lines[1:]

if lines and lines[-1].strip() == "```":
    lines = lines[:-1]

patch = "\n".join(lines).strip()

if "--- " not in patch or "+++ " not in patch:
    output = project / "ai_invalid_response.txt"
    output.write_text(patch + "\n", encoding="utf-8")

    raise SystemExit(
        "AI không trả về unified diff hợp lệ. "
        f"Đã lưu câu trả lời tại {output}"
    )

patch_file = project / "ai_changes.patch"
patch_file.write_text(patch + "\n", encoding="utf-8")

print(f"Đã tạo patch: {patch_file}")
print("Chưa có file code nào bị thay đổi.")
