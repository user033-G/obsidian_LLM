import os
import argparse
import sys
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from script directory
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# Configuration
VAULT_DIR = os.getenv("VAULT_DIR")
API_KEY = os.getenv("GEMINI_API_KEY")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

if not USE_MOCK:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        USE_MOCK = True

if USE_MOCK:
    print("Using Mocks")
    from mocks import MockGenAIClient
    class MockGenAIModule:
        Client = MockGenAIClient
    genai = MockGenAIModule()

client = genai.Client(api_key=API_KEY)

WEEKLY_PROMPT_TEMPLATE = """
あなたは1週間分の振り返りを手伝うコーチです。
以下は、ある1週間分のデイリーノートから抜き出したテキストです。

- 各日の「今日の出来事・反省」
- 各日の「明日のアクション（AIコーチ）」

これらを読んで、次の形式でMarkdownを出力してください。

1. 今週のハイライト（印象的な出来事や前進したこと）を3〜5個。
2. 繰り返し出てきたパターン（感情・行動・課題など）を2〜4個。
3. 次の4つのプロジェクト/領域ごとに、進み具合や気づきを一言ずつまとめること。
   - Kindle本
   - 家づくり
   - 健康
   - 子育て
   （何もなければ「特になし」と書いてください）
4. 来週のフォーカス（テーマ）を1つだけ決めてください。
5. そのテーマを進めるための具体的な行動を3つまで、チェックボックス付きMarkdownリストで提案してください。
   - いずれも30分以内でできる行動レベルにしてください。

出力フォーマット:

```markdown
## 今週のハイライト
- ...

## 繰り返し出てきたパターン
- ...

## プロジェクト別の振り返り
- Kindle本: ...
- 家づくり: ...
- 健康: ...
- 子育て: ...

## 来週のフォーカス
- テーマ: ...

## 来週の行動（AIコーチ）
- [ ] ...
- [ ] ...
- [ ] ...
```
上記フォーマット以外の文章は一切書かないでください。

以下が1週間分のテキストです：

{weekly_text}
"""

def get_week_range(iso_week_str):
    # iso_week_str like "2026-W02"
    try:
        # Parse year and week
        year, week = map(int, iso_week_str.split('-W'))

        # Calculate Monday
        # Python 3.8+ has datetime.fromisocalendar
        start_date = datetime.date.fromisocalendar(year, week, 1) # 1 = Monday
        end_date = datetime.date.fromisocalendar(year, week, 7)   # 7 = Sunday

        return start_date, end_date
    except ValueError:
        return None, None

def extract_daily_content(file_path):
    if not file_path.exists():
        return ""

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract "今日のスキャン" (Events/Reflection)
    # Extract "明日のアクション（AIコーチ）"
    # Simple parsing: find headers and take content until next header

    result = f"--- Date: {file_path.stem} ---\n"

    scan_header = "## 今日のスキャン"
    action_header = "## 明日のアクション（AIコーチ）"

    def get_section(text, header):
        if header not in text:
            return ""
        parts = text.split(header)
        if len(parts) < 2:
            return ""
        section = parts[1]
        # stop at next header (starts with ## )
        # split by newline, check if line starts with ##
        lines = section.split('\n')
        extracted_lines = []
        for line in lines:
            if line.strip() == "": # Skip empty first line usually
                continue
            if line.startswith("## "):
                break
            extracted_lines.append(line)
        return '\n'.join(extracted_lines).strip()

    scan_content = get_section(content, scan_header)
    action_content = get_section(content, action_header)

    if scan_content:
        result += f"[今日の出来事・反省]\n{scan_content}\n\n"
    if action_content:
        result += f"[明日のアクション（AIコーチ）]\n{action_content}\n\n"

    return result

def weekly_review(iso_week_str):
    if not VAULT_DIR:
        print("Error: VAULT_DIR is not set in .env")
        return

    start_date, end_date = get_week_range(iso_week_str)
    if not start_date:
        print(f"Invalid ISO week format: {iso_week_str}")
        return

    print(f"Generating review for {iso_week_str} ({start_date} to {end_date})")

    daily_dir = Path(VAULT_DIR) / "50_daily"
    weekly_dir = Path(VAULT_DIR) / "60_weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)

    # Collect texts
    weekly_text = ""
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        file_path = daily_dir / f"{date_str}.md"
        weekly_text += extract_daily_content(file_path)
        current += datetime.timedelta(days=1)

    if not weekly_text.strip():
        print("No daily notes found for this week.")
        return

    # Call AI
    prompt = WEEKLY_PROMPT_TEMPLATE.format(weekly_text=weekly_text)

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
        return

    # Write output
    output_path = weekly_dir / f"{iso_week_str}_Weekly_Review.md"

    # Create content
    content = f"# {iso_week_str} Weekly Review\n\n{ai_response}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Created: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python weekly_review.py YYYY-Www")
    else:
        weekly_review(sys.argv[1])
