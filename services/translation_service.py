"""
Translation service - 統一翻譯服務（協調 Google 和 DeepL）
"""
from translations import google_translator, deepl_translator
import config


def translate_text(text, target_lang, group_id=None):
    """
    統一翻譯入口。翻譯策略：
    1. 優先嘗試 Google
    2. Google 失敗 -> fallback 到 DeepL
    3. Google 和 DeepL 都失敗 -> 回傳錯誤訊息
    
    Args:
        text: 要翻譯的文本
        target_lang: 目標語言代碼
        group_id: 群組 ID（用於統計）
    
    Returns:
        翻譯後的文本或錯誤訊息
    """
    # 如果是純數字、純符號或空白，直接返回原文
    if not text or text.strip().replace(' ', '').replace('.', '').replace(',', '').isdigit():
        return text

    # 1. 優先嘗試 Google
    translated, google_reason = google_translator.translate(text, target_lang)
    
    if translated:
        # Google 成功
        if group_id:
            from services.tenant_service import update_tenant_stats_by_group
            update_tenant_stats_by_group(group_id, translate_count=1, char_count=len(text))
        return translated
    
    # 2. Google 失敗，嘗試 DeepL fallback
    print(f"⚠️ [翻譯] Google 失敗 ({google_reason})，嘗試 DeepL fallback，語言: {target_lang}")
    translated, deepl_reason = deepl_translator.translate(text, target_lang)
    
    if translated:
        # DeepL 成功
        if group_id:
            from services.tenant_service import update_tenant_stats_by_group
            update_tenant_stats_by_group(group_id, translate_count=1, char_count=len(text))
        return translated
    
    # 3. DeepL 也失敗，判斷原因
    if deepl_reason == 'unsupported_language':
        print(f"ℹ️ [翻譯] DeepL 也不支援 {target_lang}")
    
    # 4. Google 和 DeepL 都失敗
    print(f"❌ [翻譯] Google ({google_reason}) 和 DeepL ({deepl_reason}) 都失敗，語言: {target_lang}")
    return "翻譯暫時失敗，請稍後再試"


def format_translation_results(text, langs, group_id=None):
    """
    將多語言翻譯結果組成一段文字。
    
    Args:
        text: 要翻譯的文本
        langs: 目標語言集合
        group_id: 群組 ID
    
    Returns:
        格式化的翻譯結果
    """
    results = []
    for lang in langs:
        translated = translate_text(text, lang, group_id=group_id)
        results.append(f"[{lang}] {translated}")
    return '\n'.join(results)
