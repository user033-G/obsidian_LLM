import os
import sys
import json
import re
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env from script directory
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# Configuration
VAULT_DIR = os.getenv("VAULT_DIR")
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.3-70b-instruct:free"

PROMPT_TEMPLATE = """
あなたは優秀なライター兼情報整理のアシスタントです。
渡されたノートのコンテンツを分析し、トピックごとに要約して、指定されたJSON形式で出力してください。

## 入力情報
- source_type: {source_type}
- source_path: {source_path}
- date: {date}

## コンテンツ
{content}

## 出力要件
以下のJSON形式のみを出力してください。
```json
{{
  "source_type": "{source_type}",
  "source_path": "{source_path}",
  "date": "{date}",
  "topics": [
    {{
      "title": "短い日本語タイトル",
      "summary": "日本語で2〜4文の要約。",
      "tags": ["#topic/仕事"]
    }}
  ]
}}
```

注意事項:
- tagsは、コンテンツの内容に合わせて適切なものを付与してください。#topic/仕事, #topic/アイデア, #topic/振り返り など。
- topicsは複数あっても構いません。話題が変わるごとに分割してください。
- タイトルはファイル名に使用するため、簡潔にしてください。
- summaryは日本語で2〜4文程度で要約してください。
"""

MARKDOWN_TEMPLATE = """---
tags: {tags}
source_type: {source_type}
source_path: {source_path}
created: {date}
index: {index}
---

# {title}

{summary}
"""

def get_meta_info(filepath_str):
    """
    パスとファイル名からメタ情報を推定する
    """
    path = Path(filepath_str)
    filename = path.name

    source_type = "unknown"
    date_str = "0000-00-00"

    # source_type logic
    if "Voicememo" in str(path) or "Voicememo" in path.parts:
        source_type = "voicememo"
    elif "Manual" in str(path) or "Manual" in path.parts:
        source_type = "manual"

    # date logic
    if source_type == "voicememo":
        # Expecting YYYY-MM-DD in filename
        match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if match:
            date_str = match.group(1)
    elif source_type == "manual":
        # Expecting YYYYMMDD_...
        match = re.search(r"^(\d{4})(\d{2})(\d{2})_", filename)
        if match:
            date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return source_type, date_str

def generate_slug(title):
    """
    title からファイル名に使えない文字を取り除き、全角スペースを半角スペースかアンダースコアに置き換える
    """
    # Replace full-width space with underscore (user choice: space or underscore)
    slug = title.replace("　", "_").replace(" ", "_")

    # Remove invalid characters for filenames (simple approach)
    # Keep alphanumeric, underscores, hyphens, and japanese chars
    # Remove: / \ : * ? " < > |
    slug = re.sub(r'[\\/:*?"<>|]', '', slug)

    return slug

def get_unique_filepath(directory, filename):
    """
    同名のファイルが存在する場合は、末尾に連番を振って衝突を避ける
    Example: file.md -> file_1.md -> file_2.md
    """
    base_path = directory / filename
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix

    counter = 1
    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = directory / new_filename
        if not new_path.exists():
            return new_path
        counter += 1

def get_processed_sources(fleeting_dir):
    """
    10_fleeting フォルダ内のファイルをスキャンし、すでに処理済みの source_path のセットを返す
    """
    processed = set()
    if not fleeting_dir.exists():
        return processed

    for filepath in fleeting_dir.glob("*.md"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                # Read first few lines looking for 'source_path:'
                for _ in range(10): # Check first 10 lines
                    line = f.readline()
                    if not line:
                        break
                    match = re.match(r"^source_path:\s*(.+)$", line.strip())
                    if match:
                        processed.add(match.group(1).strip())
                        break
        except Exception:
            pass # Skip unreadable files
    return processed

def process_file(vault_path, source_rel_path):
    """
    Processes a single file. Returns True if successful, False otherwise.
    """
    source_full_path = vault_path / source_rel_path

    # 2. Estimate meta info
    source_type, date_str = get_meta_info(source_rel_path)

    # Optional: Skip files with unknown source type in batch?
    # Keeping it as is, but logic inside might produce "unknown" in output.

    # 3. Read content
    try:
        with open(source_full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {source_rel_path}: {e}")
        return False

    # 4. Call LLM
    prompt = PROMPT_TEMPLATE.format(
        source_type=source_type,
        source_path=source_rel_path,
        date=date_str,
        content=content
    )

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/obsidian-automation",
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ]
        # "response_format": {"type": "json_object"} # Not supported by free Llama 3.3 providers
    }

    response = None
    try:
        response = requests.post(API_ENDPOINT, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        # Extract content from response
        if "choices" in result and len(result["choices"]) > 0:
            ai_content = result["choices"][0]["message"]["content"]
        else:
            print(f"Error for {source_rel_path}: No choices in API response")
            # print(result)
            return False

    except requests.exceptions.RequestException as e:
        print(f"API Request Error for {source_rel_path}: {e}")
        if response is not None:
             print(response.text)
        return False

    # 5. Parse JSON
    try:
        # Clean up markdown code blocks if present
        clean_json = ai_content.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.replace("```json", "", 1)
        if clean_json.startswith("```"):
            clean_json = clean_json.replace("```", "", 1)
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]

        clean_json = clean_json.strip()

        parsed_data = json.loads(clean_json)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON for {source_rel_path}.")
        # print(f"Raw response: {ai_content}")
        # print(f"JSON Error: {e}")
        return False

    # Validate topics
    topics = parsed_data.get("topics", [])
    if not topics:
        print(f"No topics found for {source_rel_path}. Skipping generation.")
        return True

    # 6. Generate Markdown files
    fleeting_dir = vault_path / "10_fleeting"
    fleeting_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for i, topic in enumerate(topics):
        index = i + 1
        title = topic.get("title", "No Title")
        summary = topic.get("summary", "")
        tags = topic.get("tags", [])

        slug = generate_slug(title)

        # Filename: {date}_{index:02d}_{slug}.md
        filename = f"{date_str}_{index:02d}_{slug}.md"

        # Resolve collision
        output_path = get_unique_filepath(fleeting_dir, filename)

        # Markdown Content
        md_content = MARKDOWN_TEMPLATE.format(
            tags=json.dumps(tags, ensure_ascii=False),
            source_type=parsed_data.get("source_type", source_type),
            source_path=parsed_data.get("source_path", str(source_rel_path)),
            date=parsed_data.get("date", date_str),
            index=index,
            title=title,
            summary=summary
        )

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            count += 1
        except Exception as e:
            print(f"Error writing file {output_path}: {e}")

    print(f"Created {count} notes for {source_rel_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Summarize Obsidian note(s) using LLM.")
    parser.add_argument("filepath", help="Path to the source note or directory (relative to VAULT_DIR)")
    args = parser.parse_args()

    if not VAULT_DIR:
        print("Error: VAULT_DIR is not set in .env")
        sys.exit(1)

    if not API_KEY:
        print("Error: OPENROUTER_API_KEY is not set in .env")
        sys.exit(1)

    # Resolve paths
    vault_path = Path(VAULT_DIR)
    input_rel_path = Path(args.filepath)
    input_full_path = vault_path / input_rel_path

    if not input_full_path.exists():
        print(f"Error: Path not found: {input_full_path}")
        sys.exit(1)

    fleeting_dir = vault_path / "10_fleeting"

    if input_full_path.is_dir():
        # Directory mode
        print(f"Processing directory: {input_rel_path}")
        processed_sources = get_processed_sources(fleeting_dir)

        files = sorted(input_full_path.glob("*.md"))
        print(f"Found {len(files)} markdown files.")

        for file_path in files:
            rel_path = file_path.relative_to(vault_path)

            # Skip if already processed
            # Check for exact string match or ensuring string format match
            if str(rel_path) in processed_sources:
                print(f"Skipping {rel_path} (Already processed)")
                continue

            # Optional: strict source_type checking to skip readme.md etc?
            # get_meta_info returns "unknown". Let's process it and let user decide or skip inside?
            # User wants convenience. Let's process.

            process_file(vault_path, rel_path)

    else:
        # Single file mode
        process_file(vault_path, input_rel_path)

if __name__ == "__main__":
    main()
