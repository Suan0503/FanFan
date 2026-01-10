"""
DeepL translator module - DeepL 翻譯引擎
"""
import requests
import time
import config

deepl_session = requests.Session()
DEEPL_SUPPORTED_TARGETS = set()


def load_deepl_supported_languages():
    """啟動時載入 DeepL 支援的目標語言列表"""
    global DEEPL_SUPPORTED_TARGETS
    
    if not config.DEEPL_API_KEY:
        print("⚠️ 未設定 DEEPL_API_KEY，將只使用 Google 翻譯。")
        return
    
    try:
        url = f"{config.DEEPL_API_BASE_URL.rstrip('/')}/v2/languages"
        resp = deepl_session.get(
            url,
            params={'auth_key': config.DEEPL_API_KEY, 'type': 'target'},
            timeout=config.DEEPL_TIMEOUT
        )
        
        if resp.status_code == 200:
            languages = resp.json()
            # 提取語言代碼
            DEEPL_SUPPORTED_TARGETS = {lang['language'].upper() for lang in languages}
            print(f"✅ DeepL 已載入 {len(DEEPL_SUPPORTED_TARGETS)} 種支援語言: {sorted(DEEPL_SUPPORTED_TARGETS)}")
        else:
            print(f"⚠️ 無法載入 DeepL 支援語言列表 (HTTP {resp.status_code})，將依語言代碼猜測")
            # Fallback: 使用常見語言
            DEEPL_SUPPORTED_TARGETS = {'EN', 'JA', 'RU', 'ZH', 'ZH-HANT', 'ZH-HANS', 'DE', 'FR', 'ES', 'IT', 'PT', 'NL', 'PL', 'KO'}
    except Exception as e:
        print(f"⚠️ 載入 DeepL 支援語言時發生錯誤: {type(e).__name__}: {e}")
        # Fallback: 使用常見語言
        DEEPL_SUPPORTED_TARGETS = {'EN', 'JA', 'RU', 'ZH', 'ZH-HANT', 'ZH-HANS', 'DE', 'FR', 'ES', 'IT', 'PT', 'NL', 'PL', 'KO'}


def translate(text, target_lang):
    """
    使用 DeepL API 翻譯。
    
    Args:
        text: 要翻譯的文本
        target_lang: 目標語言代碼 (e.g. 'zh-TW', 'en', 'ja')
    
    Returns:
        (translated_text, reason) 其中 reason 是 'success' 或 error_code
    """
    if not config.DEEPL_API_KEY:
        return None, 'no_api_key'

    # 語言代碼轉換
    lang_map = {
        'en': 'EN', 'ja': 'JA', 'ru': 'RU',
        'zh-TW': 'ZH-HANT', 'zh-CN': 'ZH-HANS',
        'de': 'DE', 'fr': 'FR', 'es': 'ES', 'it': 'IT', 'pt': 'PT',
        'nl': 'NL', 'pl': 'PL', 'ko': 'KO', 'th': 'TH', 'vi': 'VI', 'id': 'ID', 'my': 'MY',
    }
    deepl_target = lang_map.get(target_lang, target_lang.upper())
    
    # 檢查是否在支援列表中
    if DEEPL_SUPPORTED_TARGETS and deepl_target not in DEEPL_SUPPORTED_TARGETS:
        return None, 'unsupported_language'

    url = f"{config.DEEPL_API_BASE_URL.rstrip('/')}/v2/translate"
    
    max_retries = config.MAX_TRANSLATION_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            resp = deepl_session.post(
                url,
                data={
                    'auth_key': config.DEEPL_API_KEY,
                    'text': text,
                    'target_lang': deepl_target,
                },
                timeout=config.DEEPL_TIMEOUT,
            )
        except requests.Timeout as e:
            print(f"⚠️ [DeepL] Timeout (第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                return None, 'timeout'
            time.sleep(0.1)  # 優化：減少重試等待時間
            continue
        except requests.RequestException as e:
            print(f"⚠️ [DeepL] 網路錯誤 (第 {attempt}/{max_retries} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'network_error'
            time.sleep(0.1)  # 優化：減少重試等待時間
            continue

        # 處理 429 Too Many Requests
        if resp.status_code == 429:
            print(f"⚠️ [DeepL] HTTP 429 Too Many Requests (第 {attempt}/{max_retries} 次)")
            if attempt < max_retries:
                time.sleep(1)  # 優化：減少 429 等待時間
                continue
            return None, 'rate_limited'
        
        # 處理其他 HTTP 錯誤
        if resp.status_code != 200:
            preview = resp.text[:150] if hasattr(resp, 'text') else ''
            print(f"⚠️ [DeepL] HTTP {resp.status_code} (第 {attempt}/{max_retries} 次): {preview}")
            if attempt == max_retries:
                return None, f'http_{resp.status_code}'
            time.sleep(0.1)  # 優化：減少重試等待時間
            continue

        # 解析回應
        try:
            data_json = resp.json()
            translations = data_json.get('translations') or []
            if not translations:
                print(f"⚠️ [DeepL] 回應中無 translations 欄位 (第 {attempt}/{max_retries} 次)")
                if attempt == max_retries:
                    return None, 'empty_response'
                time.sleep(0.1)  # 優化：減少重試等待時間
                continue
            
            translated_text = translations[0].get('text')
            if translated_text:
                return translated_text, 'success'
            else:
                print(f"⚠️ [DeepL] translations[0] 中無 text 欄位")
                return None, 'invalid_response'
                
        except Exception as e:
            print(f"⚠️ [DeepL] JSON 解析失敗 (第 {attempt}/{max_retries} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.1)  # 優化：減少重試等待時間
            continue
    
    return None, 'unknown_error'
