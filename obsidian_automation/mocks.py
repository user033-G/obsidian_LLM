from unittest.mock import MagicMock
import json

class MockGenAIClient:
    def __init__(self, api_key=None):
        pass

    def generate_content(self, model, contents, config=None):
        prompt = contents[0] if isinstance(contents, list) else contents
        response = MagicMock()

        # Simple heuristic to determine which mock response to return
        if "Kindle本のハイライト" in prompt:
            # Kindle Classification
            response.text = '{"theme": "健康"}'
        elif "行動レベルに落とし込むコーチ" in prompt:
            # Daily Coaching
            response.text = """## 改善ポイント（AIコーチ）
- もっと早く寝るべきでした。

## 明日のアクション（AIコーチ）
- [ ] 朝7時に起きる
- [ ] 水を一杯飲む
- [ ] ストレッチする"""
        elif "1週間分の振り返り" in prompt:
            # Weekly Review
            response.text = """## 今週のハイライト
- プロジェクトA完了
- 家族で公園に行った
- 本を1冊読了

## 繰り返し出てきたパターン
- 夜更かし気味
- 運動不足

## プロジェクト別の振り返り
- Kindle本: 1冊読了
- 家づくり: 間取り検討中
- 健康: 運動不足気味
- 子育て: 子供と遊べた

## 来週のフォーカス
- テーマ: 早寝早起き

## 来週の行動（AIコーチ）
- [ ] 22時に布団に入る
- [ ] スマホをリビングに置く
- [ ] 朝散歩する"""
        else:
            response.text = "Mock response"

        return response

class MockArticle:
    def __init__(self, url):
        self.url = url
        self.text = "これは記事の本文です。\nNewspaper3kで取得された想定のテキストです。"
        self.title = "記事タイトル"

    def download(self):
        pass

    def parse(self):
        pass

def mock_convert_from_path(pdf_path):
    # Returns a list of dummy PIL images
    from PIL import Image
    return [Image.new('RGB', (100, 100), color = 'white')]

def mock_image_to_string(image, lang='jpn'):
    return """
#1 今日のスキャン
朝起きてご飯を食べた。
仕事が忙しかった。

#2 感情と気づき
少し疲れたけれど充実していた。

#3 感謝と自己肯定
同僚に助けてもらって感謝。
よく頑張った。

#4 明日の一歩
早く寝る。
"""
