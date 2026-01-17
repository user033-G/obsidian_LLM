# Obsidian Automation System

Obsidian Vaultを「第二の脳」として活用するための自動化スクリプト群です。
Kindleハイライトの分類、Raindrop記事の本文取得、日次・週次の振り返りとAIコーチングを自動化します。

## 必要要件

### システム要件
以下のツールがシステムにインストールされている必要があります。

- **Python 3.11+**
- **Tesseract OCR** (日次振り返りPDFのOCR用)
  - macOS: `brew install tesseract tesseract-lang`
  - Windows: Tesseractインストーラーを使用し、日本語データ(`jpn`)を含めてください。
- **Poppler** (PDFを画像に変換するため)
  - macOS: `brew install poppler`
  - Windows: Popplerのバイナリをダウンロードし、PATHを通してください。

### Python ライブラリ
プロジェクトのルートディレクトリで以下を実行して依存関係をインストールします。

```bash
pip install -r requirements.txt
```

## 設定

`obsidian_automation` フォルダ内の `.env.template` をコピーして `.env` を作成し、環境変数を設定してください。

```bash
cp .env.template .env
```

`.env` の内容:

```ini
# Obsidian Vaultのルートディレクトリへの絶対パス
VAULT_DIR=/Users/username/ObsidianVault

# Google Gemini APIキー
GEMINI_API_KEY=your_api_key_here

# テスト用（APIキーがない場合やTesseractがない場合にモックを使用するか）
# 本番利用時は false にしてください
USE_MOCK=false
```

## 使い方

全てのスクリプトは `obsidian_automation` ディレクトリ、またはルートディレクトリから実行できます。
以下はルートディレクトリからの実行例です。

### 1. Kindleハイライト分類 (`classify_kindle.py`)

`20_inputs/Resource_Kindle読書/_inbox/` にあるKindleハイライトのMarkdownファイルを読み込み、Geminiを使ってテーマ別フォルダ（健康、家づくり、など）に自動移動します。

```bash
python obsidian_automation/classify_kindle.py
```

### 2. Raindrop記事本文取得 (`fetch_raindrop_body.py`)

`20_inputs/Resource_Raindrop/` にあるMarkdownファイルのFrontmatterからURLを取得し、記事本文を抽出して追記します。

**オプション:** 日付を指定すると、その日以降に作成されたファイルのみを処理します。

```bash
# 全件処理（既に取得済み・新しいファイルを確認）
python obsidian_automation/fetch_raindrop_body.py

# 指定日以降（YYYY-MM-DD）に作成されたファイルのみ処理
python obsidian_automation/fetch_raindrop_body.py 2024-01-01
```

### 3. デイリーノート生成 & AIコーチング (`daily_pipeline.py`)

手書きの振り返りPDF (`50_daily_pdf/YYYY-MM-DD_daily_filled.pdf`) をOCR処理し、テキスト化してGeminiに送信します。AIからのフィードバックと「明日のアクション」を含むデイリーノート (`50_daily/YYYY-MM-DD.md`) を生成（または更新）します。

```bash
# 日付を指定して実行
python obsidian_automation/daily_pipeline.py 2026-01-11
```

### 4. 週次レビュー生成 (`weekly_review.py`)

指定した週（ISO週番号）のデイリーノートを集計し、週のハイライト、パターン、プロジェクト別の進捗、来週のテーマなどをGeminiに生成させます。

```bash
# 週番号を指定して実行 (例: 2026年の第2週)
python obsidian_automation/weekly_review.py 2026-W02
```

## ディレクトリ構成（想定）

```text
VAULT_DIR/
├── 20_inputs/
│   ├── Resource_Kindle読書/
│   │   ├── _inbox/          <-- Kindle分類の入力元
│   │   ├── Kindle_健康/      <-- Kindle分類の出力先
│   │   └── ...
│   └── Resource_Raindrop/   <-- Raindrop記事の場所
├── 50_daily/                <-- デイリーノート (出力先)
├── 50_daily_pdf/            <-- 手書きPDF (入力元)
└── 60_weekly/               <-- 週次レビュー (出力先)
```
