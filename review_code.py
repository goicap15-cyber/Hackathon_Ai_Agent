import os
from pathlib import Path
from openai import OpenAI

project = Path.cwd()

files_to_review = [
    "README.md",
    "ARCHITECTURE.md",
    "run.py",
]

sections = []

for relative_path in files_to_review:
    file_path = project / relative_path

    if not file_path.is_file():
        print(f"Bỏ qua vì không tìm thấy: {relative_path}")
        continue

    content = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    # Tránh gửi file quá lớn
    content = content[:30_000]

    sections.append(
        f"\n===== FILE: {relative_path} =====\n{content}\n"
    )

if not sections:
    raise SystemExit(
        "Không tìm thấy README.md, ARCHITECTURE.md hoặc run.py "
        f"trong {project}"
    )

api_key = os.getenv("NOTIONCHAT_API_KEY")

if not api_key:
    raise SystemExit(
        "Chưa có NOTIONCHAT_API_KEY. "
        "Hãy chạy: set -a; source ~/Notion-AI-to-OpenAI-Compatible/.env; set +a"
    )

client = OpenAI(
    base_url="http://127.0.0.1:1994/v1",
    api_key=api_key,
)

models = client.models.list().data

if not models:
    raise SystemExit("NotionChat không trả về model nào.")

print("Model khả dụng:")
for model in models:
    print("-", model.id)

model_id = os.getenv("NOTIONCHAT_MODEL") or models[0].id
print(f"\nĐang sử dụng model: {model_id}")

prompt = f"""
Hãy review project dựa trên các file dưới đây.

Yêu cầu:
1. Tóm tắt mục tiêu và kiến trúc hiện tại.
2. Chỉ ra điểm mạnh.
3. Chỉ ra lỗi, technical debt và rủi ro bảo mật.
4. Đánh giá mức độ AI-first và AI-native.
5. Đề xuất theo ba nhóm: Must fix, High impact, Nice to have.
6. Không suy đoán nội dung của những file chưa được cung cấp.
7. Trả lời bằng tiếng Việt.

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

print("\n===== KẾT QUẢ REVIEW =====\n")
print(response.choices[0].message.content)
