"""
FanFan LINE Bot - 翻譯服務模組
提供 Google Translate 和 DeepL API 的統一翻譯介面
"""
import requests
import time
import threading
from config import (
    DEEPL_API_KEY, DEEPL_API_BASE_URL, DEFAULT_TRANSLATE_LANGS, MAX_CONCURRENT_TRANSLATIONS
)
from utils import get_data, save_data
from .tenant import get_tenant_by_group, update_tenant_stats

# 建立 requests.Session 重用連線，提升效能
deepl_session = requests.Session()
google_session = requests.Session()

# 翻譯並發控制信號量
translation_semaphore = threading.Semaphore(MAX_CONCURRENT_TRANSLATIONS)

# DeepL 支援的目標語言快取（啟動時載入）
DEEPL_SUPPORTED_TARGETS = set()


def _load_deepl_supported_languages():
    """啟動時載入 DeepL 支援的目標語言列表"""
    global DEEPL_SUPPORTED_TARGETS
    
    if not DEEPL_API_KEY:
        print("Warning: DEEPL_API_KEY not set, will use Google Translate only.")
        return
    
    try:
        url = f"{DEEPL_API_BASE_URL.rstrip('/')}/v2/languages"
        resp = deepl_session.get(
            url,
            params={'auth_key': DEEPL_API_KEY, 'type': 'target'},
            timeout=(3, 8)
        )
        
        if resp.status_code == 200:
            languages = resp.json()
            # 提取語言代碼，DeepL 回傳格式如 [{"language": "EN", "name": "English"}, ...]
            DEEPL_SUPPORTED_TARGETS = {lang['language'].upper() for lang in languages}
            print(f"[DeepL] Loaded {len(DEEPL_SUPPORTED_TARGETS)} supported languages")
        else:
            print(f"[DeepL] Failed to load languages (HTTP {resp.status_code}), using fallback")
            # Fallback: 使用常見語言
            DEEPL_SUPPORTED_TARGETS = {'EN', 'JA', 'RU', 'ZH', 'ZH-HANT', 'ZH-HANS', 'DE', 'FR', 'ES', 'IT', 'PT', 'NL', 'PL', 'KO'}
    except Exception as e:
        print(f"[DeepL] Error loading languages: {type(e).__name__}: {e}")
        # Fallback: 使用常見語言
        DEEPL_SUPPORTED_TARGETS = {'EN', 'JA', 'RU', 'ZH', 'ZH-HANT', 'ZH-HANS', 'DE', 'FR', 'ES', 'IT', 'PT', 'NL', 'PL', 'KO'}


def _translate_with_deepl(text, target_lang):
    """使用 DeepL API 翻譯。使用 Session 重用連線，timeout (3, 8)，最多 retry 1次"""

    if not DEEPL_API_KEY:
        return None, 'no_api_key'

    # 語言代碼轉換：將本系統代碼轉成 DeepL 格式
    lang_map = {
        'en': 'EN',
        'ja': 'JA',
        'ru': 'RU',
        'zh-TW': 'ZH-HANT',
        'zh-CN': 'ZH-HANS',
        'de': 'DE',
        'fr': 'FR',
        'es': 'ES',
        'it': 'IT',
        'pt': 'PT',
        'nl': 'NL',
        'pl': 'PL',
        'ko': 'KO',
        'th': 'TH',
        'vi': 'VI',
        'id': 'ID',
        'my': 'MY',
    }
    deepl_target = lang_map.get(target_lang, target_lang.upper())
    
    # 檢查是否在支援列表中（如果已載入）
    if DEEPL_SUPPORTED_TARGETS and deepl_target not in DEEPL_SUPPORTED_TARGETS:
        # 不支援的語言，不算失敗，直接回傳 unsupported
        return None, 'unsupported_language'

    url = f"{DEEPL_API_BASE_URL.rstrip('/')}/v2/translate"
    
    max_retries = 2  # 1 次原始 + 1 次 retry
    for attempt in range(1, max_retries + 1):
        try:
            resp = deepl_session.post(
                url,
                data={
                    'auth_key': DEEPL_API_KEY,
                    'text': text,
                    'target_lang': deepl_target,
                },
                timeout=(3, 8),  # (connect_timeout, read_timeout)
            )
        except requests.Timeout as e:
            print(f"[DeepL] Timeout (attempt {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                return None, 'timeout'
            time.sleep(0.3)
            continue
        except requests.RequestException as e:
            print(f"[DeepL] Network error (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'network_error'
            time.sleep(0.3)
            continue

        # 處理 429 Too Many Requests
        if resp.status_code == 429:
            print(f"[DeepL] HTTP 429 Rate limit (attempt {attempt}/{max_retries})")
            if attempt < max_retries:
                time.sleep(2)  # 429 需要較長等待
                continue
            return None, 'rate_limited'
        
        # 處理其他 HTTP 錯誤
        if resp.status_code != 200:
            preview = resp.text[:150] if hasattr(resp, 'text') else ''
            print(f"[DeepL] HTTP {resp.status_code} (attempt {attempt}/{max_retries}): {preview}")
            if attempt == max_retries:
                return None, f'http_{resp.status_code}'
            time.sleep(0.3)
            continue

        # 解析回應
        try:
            data_json = resp.json()
            translations = data_json.get('translations') or []
            if not translations:
                print(f"[DeepL] No translations field in response (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    return None, 'empty_response'
                time.sleep(0.3)
                continue
            
            translated_text = translations[0].get('text')
            if translated_text:
                return translated_text, 'success'
            else:
                print(f"[DeepL] No text field in translation response")
                return None, 'invalid_response'
                
        except Exception as e:
            print(f"[DeepL] JSON parse error (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.3)
            continue
    
    return None, 'unknown_error'


def _translate_with_google(text, target_lang):
    """使用 Google Translate 非官方 API。使用 Session 重用連線，timeout (2, 4)，最多 retry 1次"""

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        'client': 'gtx',
        'sl': 'auto',
        'tl': target_lang,
        'dt': 't',
        'q': text,
    }
    
    max_retries = 2  # 1 次原始 + 1 次 retry
    for attempt in range(1, max_retries + 1):
        try:
            res = google_session.get(
                url,
                params=params,
                timeout=(2, 4)  # (connect_timeout, read_timeout)
            )
        except requests.Timeout as e:
            print(f"[Google] Timeout (attempt {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                return None, 'timeout'
            time.sleep(0.3)
            continue
        except requests.RequestException as e:
            print(f"[Google] Network error (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'network_error'
            time.sleep(0.3)
            continue

        # 處理 429 Too Many Requests
        if res.status_code == 429:
            print(f"[Google] HTTP 429 Rate limit (attempt {attempt}/{max_retries})")
            if attempt < max_retries:
                time.sleep(2)  # 429 需要較長等待
                continue
            return None, 'rate_limited'
        
        # 處理其他 HTTP 錯誤
        if res.status_code != 200:
            preview = res.text[:150] if hasattr(res, 'text') else ''
            print(f"[Google] HTTP {res.status_code} (attempt {attempt}/{max_retries}): {preview}")
            if attempt == max_retries:
                return None, f'http_{res.status_code}'
            time.sleep(0.3)
            continue

        # 解析回應
        try:
            result = res.json()[0][0][0]
            if result:
                return result, 'success'
            else:
                print(f"[Google] No translation text in response")
                return None, 'empty_response'
        except (IndexError, KeyError, TypeError) as e:
            print(f"[Google] Unexpected JSON structure (attempt {attempt}/{max_retries}): {type(e).__name__}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.3)
            continue
        except Exception as e:
            print(f"[Google] JSON parse error (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.3)
            continue

    return None, 'unknown_error'


def translate_text(text, target_lang, prefer_deepl_first=False, group_id=None):
    """
    統一翻譯入口。翻譯策略：
    1. 優先嘗試 Google
    2. Google 失敗 -> fallback 到 DeepL
    3. Google 和 DeepL 都失敗 -> 回傳錯誤訊息
    """

    # 如果是純數字、純符號或空白，直接返回原文
    if not text or text.strip().replace(' ', '').replace('.', '').replace(',', '').isdigit():
        return text

    # 1. 優先嘗試 Google
    translated, google_reason = _translate_with_google(text, target_lang)
    
    if translated:
        # Google 成功
        if group_id:
            user_id, tenant = get_tenant_by_group(group_id)
            if user_id:
                update_tenant_stats(user_id, translate_count=1, char_count=len(text))
        return translated
    
    # 2. Google 失敗，嘗試 DeepL fallback
    print(f"[Translation] Google failed ({google_reason}), trying DeepL fallback for {target_lang}")
    translated, deepl_reason = _translate_with_deepl(text, target_lang)
    
    if translated:
        # DeepL 成功
        if group_id:
            user_id, tenant = get_tenant_by_group(group_id)
            if user_id:
                update_tenant_stats(user_id, translate_count=1, char_count=len(text))
        return translated
    
    # 3. DeepL 也失敗，判斷原因
    if deepl_reason == 'unsupported_language':
        print(f"[Translation] DeepL also does not support {target_lang}")
    
    # 4. Google 和 DeepL 都失敗
    print(f"[Translation] Both Google ({google_reason}) and DeepL ({deepl_reason}) failed for {target_lang}")
    return "翻譯暫時失敗，請稍後再試"


def _format_translation_results(text, langs, prefer_deepl_first=False, group_id=None):
    """將多語言翻譯結果組成一段文字。"""
    results = []
    for lang in langs:
        translated = translate_text(text, lang, prefer_deepl_first=prefer_deepl_first, group_id=group_id)
        results.append(f"[{lang}] {translated}")
    return '\n'.join(results)
