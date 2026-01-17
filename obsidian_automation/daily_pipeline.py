import os
import argparse
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Load .env from script directory
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# Configuration
VAULT_DIR = os.getenv("VAULT_DIR")
API_KEY = os.getenv("GEMINI_API_KEY")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

# Imports
if not USE_MOCK:
    try:
        from google import genai
        from google.genai import types
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        USE_MOCK = True

if USE_MOCK:
    print("Using Mocks")
    from mocks import MockGenAIClient, mock_convert_from_path, mock_image_to_string
    convert_from_path = mock_convert_from_path

    # Mock pytesseract module
    class MockPyTesseract:
        def image_to_string(self, image, lang='jpn'):
            return mock_image_to_string(image, lang)
    pytesseract = MockPyTesseract()

    class MockGenAIModule:
        Client = MockGenAIClient
    genai = MockGenAIModule()

client = genai.Client(api_key=API_KEY)

COACHING_PROMPT_TEMPLATE = """
あなたは行動レベルに落とし込むコーチです。
以下は、ある1日の振り返りメモです。

- 「今日のスキャン」（その日の出来事・事実）
- 「感情と気づき」
- 「感謝と自己肯定」

これらを読んで、次の形式でMarkdownを出力してください。

1. その日の反省から読み取れる「改善ポイント」を1〜2個だけ、短く箇条書き。
2. 明日実行できる具体的な行動を3つまで。
   - それぞれ5〜15分で終わる小さな行動にすること。
   - チェックボックス付きのMarkdownリスト形式にすること。
3. 自分を責める表現は避け、「こうするともっと良くなりそう」というトーンにすること。

出力フォーマット:

```markdown
## 改善ポイント（AIコーチ）
- ...

## 明日のアクション（AIコーチ）
- [ ] ...
- [ ] ...
- [ ] ...
```
上記フォーマット以外の文章は一切書かないでください。

以下が今日のメモです：

[今日のスキャン]
{scan}

[感情と気づき]
{emotion}

[感謝と自己肯定]
{gratitude}
"""

def extract_section(text, label):
    # Heuristic to find text between labels
    # Labels: #1, #2, #3, #4
    # Note: OCR might produce varied spacing or symbols.
    # We'll use regex to find lines starting with label.

    # Mapping
    # #1 -> 今日のスキャン
    # #2 -> 感情と気づき
    # #3 -> 感謝と自己肯定
    # #4 -> 明日の一歩

    pattern_map = {
        "scan": r"#\s*1",
        "emotion": r"#\s*2",
        "gratitude": r"#\s*3",
        "step": r"#\s*4"
    }

    # Find start indices
    indices = {}
    for key, pat in pattern_map.items():
        match = re.search(pat, text)
        if match:
            indices[key] = match.start()
        else:
            indices[key] = -1

    # Sort indices
    sorted_indices = sorted([(v, k) for k, v in indices.items() if v != -1])

    if not sorted_indices:
        return ""

    # Extract content
    target_idx = -1
    for i, (idx, key) in enumerate(sorted_indices):
        if key == label:
            target_idx = idx
            next_idx = sorted_indices[i+1][0] if i+1 < len(sorted_indices) else len(text)
            return text[target_idx:next_idx].strip() # This includes the label line

    return ""

def clean_section_text(text):
    # Remove the label line (first line)
    lines = text.split('\n')
    if len(lines) > 0:
        return '\n'.join(lines[1:]).strip()
    return text

def daily_pipeline(date_str):
    if not VAULT_DIR:
        print("Error: VAULT_DIR is not set in .env")
        return

    # File paths
    pdf_dir = Path(VAULT_DIR) / "50_daily_pdf"
    daily_dir = Path(VAULT_DIR) / "50_daily"

    # Find PDF
    pdf_path = pdf_dir / f"{date_str}_daily_filled.pdf"
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return

    print(f"Processing PDF: {pdf_path}")

    # OCR
    try:
        images = convert_from_path(str(pdf_path))
        full_text = ""
        for img in images:
            text = pytesseract.image_to_string(img, lang='jpn')
            full_text += text + "\n"
    except Exception as e:
        print(f"OCR Failed: {e}")
        return

    print("OCR Complete.")

    # Extract sections
    # Assuming text contains labels like #1, #2, ...
    # We need to parse robustly.

    raw_scan = extract_section(full_text, "scan")
    raw_emotion = extract_section(full_text, "emotion")
    raw_gratitude = extract_section(full_text, "gratitude")
    raw_step = extract_section(full_text, "step")

    scan_text = clean_section_text(raw_scan)
    emotion_text = clean_section_text(raw_emotion)
    gratitude_text = clean_section_text(raw_gratitude)
    step_text = clean_section_text(raw_step)

    # Call AI
    prompt = COACHING_PROMPT_TEMPLATE.format(
        scan=scan_text,
        emotion=emotion_text,
        gratitude=gratitude_text
    )

    try:
        if USE_MOCK:
             response = client.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
        else:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
        ai_response = response.text

        # Clean markdown fences
        if ai_response.startswith("```markdown"):
            ai_response = ai_response.replace("```markdown", "", 1)
            if ai_response.endswith("```"):
                ai_response = ai_response[:-3]
        elif ai_response.startswith("```"):
            ai_response = ai_response.replace("```", "", 1)
            if ai_response.endswith("```"):
                ai_response = ai_response[:-3]
        ai_response = ai_response.strip()

    except Exception as e:
        print(f"AI Failed: {e}")
        ai_response = "AI Generation Failed."

    # Update Daily Note
    daily_note_path = daily_dir / f"{date_str}.md"

    # Construct Content
    # If exists, read and replace sections. If not, create new.
    # The requirement says:
    # "replace content under specific headers if they exist, otherwise append."
    # Headers: ## 今日のスキャン, ## 感情と気づき, ## 感謝と自己肯定, ## 明日の一歩, ## 明日のアクション（AIコーチ） (and 改善ポイント?)

    # AI response contains ## 改善ポイント（AIコーチ） and ## 明日のアクション（AIコーチ）

    new_sections = {
        "## 今日のスキャン": scan_text,
        "## 感情と気づき": emotion_text,
        "## 感謝と自己肯定": gratitude_text,
        "## 明日の一歩": step_text
    }

    if daily_note_path.exists():
        with open(daily_note_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = f"# {date_str} Daily Note\n"

    # Helper to replace or append
    for header, body in new_sections.items():
        pattern = re.compile(f"({re.escape(header)}).*?(?=\n## |$)", re.DOTALL)
        replacement = f"{header}\n{body}\n"
        if pattern.search(content):
            content = pattern.sub(replacement, content, count=1)
        else:
            content += f"\n\n{replacement}"

    # Handle AI response parts
    # The AI response comes as a block with headers.
    # We should replace/append them individually or as a block?
    # User said: "## 明日のアクション（AIコーチ） は毎回AIで再生成して丸ごと置き換えで問題なし。"
    # The AI response includes "## 改善ポイント..." and "## 明日のアクション..."

    # Let's split AI response by header
    # But wait, the prompt output format is fixed.
    # It outputs:
    # ## 改善ポイント（AIコーチ）
    # ...
    # ## 明日のアクション（AIコーチ）
    # ...

    # We can just append/replace these two headers similarly.

    # Extract from AI response
    ai_sections = {}

    # Regex to find headers in AI response
    ai_headers = ["## 改善ポイント（AIコーチ）", "## 明日のアクション（AIコーチ）"]

    current_header = None
    buffer = []

    for line in ai_response.split('\n'):
        line = line.strip()
        is_header = False
        for h in ai_headers:
            if line.startswith(h):
                if current_header:
                    ai_sections[current_header] = '\n'.join(buffer).strip()
                current_header = h
                buffer = []
                is_header = True
                break
        if not is_header and current_header:
            buffer.append(line)

    if current_header:
        ai_sections[current_header] = '\n'.join(buffer).strip()

    # Now merge AI sections into file content
    for header, body in ai_sections.items():
        pattern = re.compile(f"({re.escape(header)}).*?(?=\n## |$)", re.DOTALL)
        replacement = f"{header}\n{body}\n"
        if pattern.search(content):
            content = pattern.sub(replacement, content, count=1)
        else:
            content += f"\n\n{replacement}"

    with open(daily_note_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated {daily_note_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python daily_pipeline.py YYYY-MM-DD")
    else:
        daily_pipeline(sys.argv[1])
