import os
import argparse
import datetime
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Configuration
VAULT_DIR = os.getenv("VAULT_DIR")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

try:
    from newspaper import Article
except ImportError:
    USE_MOCK = True

if USE_MOCK:
    print("Using Mock Newspaper3k")
    from mocks import MockArticle as Article

def fetch_raindrop_body():
    parser = argparse.ArgumentParser(description="Fetch article body for Raindrop notes.")
    parser.add_argument("start_date", nargs="?", help="Start date (YYYY-MM-DD) to filter files by created date.")
    args = parser.parse_args()

    if not VAULT_DIR:
        print("Error: VAULT_DIR is not set in .env")
        return

    raindrop_dir = Path(VAULT_DIR) / "20_inputs/Resource_Raindrop"
    if not raindrop_dir.exists():
        print(f"Directory not found: {raindrop_dir}")
        return

    start_date = None
    if args.start_date:
        try:
            start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD.")
            return

    files = list(raindrop_dir.glob("*.md"))
    if not files:
        print("No files found.")
        return

    for file_path in files:
        try:
            # Parse Frontmatter
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                continue

            # Split frontmatter
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue

            frontmatter_str = parts[1]
            body_text = parts[2]

            try:
                fm = yaml.safe_load(frontmatter_str)
            except yaml.YAMLError:
                print(f"Failed to parse YAML for {file_path.name}")
                continue

            if not fm:
                continue

            # Check date filter
            created_val = fm.get("created")
            if start_date:
                if not created_val:
                    continue
                # Handle various date formats if necessary, assuming string or date obj
                if isinstance(created_val, datetime.date):
                    file_date = created_val
                elif isinstance(created_val, str):
                    try:
                        file_date = datetime.datetime.strptime(created_val, "%Y-%m-%d").date()
                    except ValueError:
                        # Try parsing as ISO format or others if needed
                         file_date = None
                else:
                    file_date = None

                if not file_date or file_date < start_date:
                    continue

            url = fm.get("link")
            if not url:
                continue

            print(f"Processing: {file_path.name} ({url})")

            # Fetch body
            article = Article(url)
            article.download()
            article.parse()

            extracted_text = article.text.strip()

            # Append section
            header = "\n\n## 本文（newspaper3k）\n"

            # Check if header already exists
            if "## 本文（newspaper3k）" in body_text:
                # Replace existing section (regex or split)
                # Simple approach: split by header and keep first part
                pre_existing = body_text.split("## 本文（newspaper3k）")[0]
                new_body = pre_existing + header + extracted_text
            else:
                new_body = body_text + header + extracted_text

            # Reconstruct file
            new_content = "---\n" + frontmatter_str + "---" + new_body

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print("Updated.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error processing {file_path.name}: {e}")

if __name__ == "__main__":
    fetch_raindrop_body()
