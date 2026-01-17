import os
import json
import shutil
import glob
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Configuration
VAULT_DIR = os.getenv("VAULT_DIR")
API_KEY = os.getenv("GEMINI_API_KEY")

# Check if we should use mocks (if package missing or env var set)
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"
if not USE_MOCK:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        USE_MOCK = True

if USE_MOCK:
    print("Using Mock GenAI Client")
    from mocks import MockGenAIClient
    # Mimic the client structure: client = genai.Client(api_key=...)
    # In my mock, MockGenAIClient is the client class itself.
    # So I need a wrapper or just assign it directly if the constructor signature matches.
    # The real genai.Client takes api_key. My MockGenAIClient takes api_key.
    # So:
    class MockGenAIModule:
        Client = MockGenAIClient
    genai = MockGenAIModule()

    # Mock types
    class MockTypes:
        def GenerateContentConfig(self, response_mime_type=None):
            return None
    types = MockTypes()

client = genai.Client(api_key=API_KEY)

KINDLE_PROMPT_TEMPLATE = """
あなたは読書メモ整理アシスタントです。
以下は、あるKindle本のハイライトノートの一部です（タイトルといくつかの抜粋を含みます）。
この本が主に扱っているテーマを、次の候補から最も近いものを1つだけ選んでください。

- 健康
- 家づくり
- 子育て
- 仕事
- お金
- その他

出力は次のJSON形式のみとし、余計な説明は一切書かないでください。

```json
{{"theme": "健康"}}
```
のように、"theme" に上記の候補のいずれか1つを入れてください。

以下がハイライトノートです：
{highlight_extract}
"""

def classify_kindle_notes():
    if not VAULT_DIR:
        print("Error: VAULT_DIR is not set in .env")
        return

    inbox_path = Path(VAULT_DIR) / "20_inputs/Resource_Kindle読書/_inbox"
    if not inbox_path.exists():
        print(f"Directory not found: {inbox_path}")
        return

    files = list(inbox_path.glob("*.md"))
    if not files:
        print("No files found in inbox.")
        return

    for file_path in files:
        try:
            print(f"Processing: {file_path.name}")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract title and first few lines (e.g., first 2000 chars)
            extract = content[:2000]

            prompt = KINDLE_PROMPT_TEMPLATE.format(highlight_extract=extract)

            # Call API
            if USE_MOCK:
                 response = client.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            else:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

            # Parse JSON
            try:
                # Handle code block wrapping if present (though prompt asks for JSON)
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text.split("```json")[1].split("```")[0].strip()
                elif text.startswith("```"):
                    text = text.split("```")[1].split("```")[0].strip()

                print(f"DEBUG: Response text: {text}")
                data = json.loads(text)
                print(f"DEBUG: Parsed data: {data}, type: {type(data)}")
                theme = data.get("theme", "その他")
            except json.JSONDecodeError:
                print(f"Failed to parse JSON for {file_path.name}. Response: {response.text}")
                continue

            # Move file
            target_dir = Path(VAULT_DIR) / f"20_inputs/Resource_Kindle読書/Kindle_{theme}"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / file_path.name

            shutil.move(str(file_path), str(target_path))
            print(f"Moved to: {target_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error processing {file_path.name}: {e}")

if __name__ == "__main__":
    classify_kindle_notes()
