"""
Google translator module - Google Translate 翻譯引擎
"""
import requests
import time
import config

google_session = requests.Session()


def translate(text, target_lang):
    """
    使用 Google Translate 非官方 API 翻譯。
    
    Args:
        text: 要翻譯的文本
        target_lang: 目標語言代碼 (e.g. 'zh-TW', 'en', 'ja')
    
    Returns:
        (translated_text, reason) 其中 reason 是 'success' 或 error_code
    """
    url = config.GOOGLE_TRANSLATE_URL
    params = {
        'client': 'gtx',
        'sl': 'auto',
        'tl': target_lang,
        'dt': 't',
        'q': text,
    }
    
    max_retries = config.MAX_TRANSLATION_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            res = google_session.get(
                url,
                params=params,
                timeout=config.GOOGLE_TIMEOUT
            )
        except requests.Timeout as e:
            print(f"⚠️ [Google] Timeout (第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                return None, 'timeout'
            time.sleep(0.3)
            continue
        except requests.RequestException as e:
            print(f"⚠️ [Google] 網路錯誤 (第 {attempt}/{max_retries} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'network_error'
            time.sleep(0.3)
            continue

        # 處理 429 Too Many Requests
        if res.status_code == 429:
            print(f"⚠️ [Google] HTTP 429 Too Many Requests (第 {attempt}/{max_retries} 次)")
            if attempt < max_retries:
                time.sleep(2)  # 429 需要較長等待
                continue
            return None, 'rate_limited'
        
        # 處理其他 HTTP 錯誤
        if res.status_code != 200:
            preview = res.text[:150] if hasattr(res, 'text') else ''
            print(f"⚠️ [Google] HTTP {res.status_code} (第 {attempt}/{max_retries} 次): {preview}")
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
                print(f"⚠️ [Google] 回應中無翻譯文字")
                return None, 'empty_response'
        except (IndexError, KeyError, TypeError) as e:
            print(f"⚠️ [Google] JSON 結構異常 (第 {attempt}/{max_retries} 次): {type(e).__name__}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.3)
            continue
        except Exception as e:
            print(f"⚠️ [Google] JSON 解析失敗 (第 {attempt}/{max_retries} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None, 'parse_error'
            time.sleep(0.3)
            continue

    return None, 'unknown_error'
