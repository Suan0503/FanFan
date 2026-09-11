# FanFan 翻譯系統問題分析與修復

## 檢測到的問題

### 1. ❌ **DeepL API 認證失敗 (HTTP 403)**

**症狀**:
```
⚠️ [DeepL] HTTP 403 (第 1/2 次): {"message":"Missing Authorization header, expected 'Authorization: DeepL-Auth-Key <API key>'"}
```

**根本原因**:
- API 金鑰被發送為表單數據（form data）的 `auth_key` 參數
- DeepL API 要求金鑰通過 HTTP Authorization 標頭傳送

**修復位置**: `FanFan/translations/deepl_translator.py` (第 75-78 行)

**修改內容**:
```python
# ❌ 舊代碼
data={
    'auth_key': config.DEEPL_API_KEY,
    'text': text,
    'target_lang': deepl_target,
}

# ✅ 新代碼
headers={'Authorization': f'DeepL-Auth-Key {config.DEEPL_API_KEY}'},
data={
    'text': text,
    'target_lang': deepl_target,
}
```

---

### 2. ⚠️ **Google Translate 速率限制 (HTTP 429)**

**症狀**:
```
⚠️ [Google] HTTP 429 Too Many Requests (第 1/2 次)
⚠️ [Google] HTTP 429 Too Many Requests (第 2/2 次)
```

**根本原因**:
1. 使用非官方 Google Translate API（`gtx` 客戶端），易被限流
2. 重試邏輯過於簡單（固定等待時間）
3. 重試次數太少 (MAX_TRANSLATION_RETRIES = 1)

**修復方案**:

**a) 增加重試次數** - `FanFan/config.py` (第 34 行)
```python
# ❌ 舊：MAX_TRANSLATION_RETRIES = 1
# ✅ 新：MAX_TRANSLATION_RETRIES = 2
```

**b) 實施指數退避** - `FanFan/translations/google_translator.py` 與 `deepl_translator.py`
```python
# ✅ 新的退避邏輯
if attempt < max_retries:
    wait_time = min(2 ** attempt, 10)  # 1秒, 2秒, 4秒...最多10秒
    print(f"   等待 {wait_time} 秒後重試...")
    time.sleep(wait_time)
    continue
```

---

### 3. ❌ **不支援的語言映射到 DeepL**

**症狀**:
```
ℹ️ [翻譯] DeepL 也不支援 id
ℹ️ [翻譯] DeepL 也不支援 vi
ℹ️ [翻譯] DeepL 也不支援 th
```

**根本原因**:
- DeepL 的語言對應表中包含 DeepL 不支援的語言：
  - `th` (泰文) - 不支援
  - `vi` (越南文) - 不支援
  - `id` (印尼文) - 不支援
  - `my` (緬甸文) - 不支援

**修復位置**: `FanFan/translations/deepl_translator.py` (第 57-63 行)

**修改內容**:
```python
# ❌ 舊代碼
lang_map = {
    'en': 'EN', 'ja': 'JA', 'ru': 'RU',
    'zh-TW': 'ZH-HANT', 'zh-CN': 'ZH-HANS',
    'de': 'DE', 'fr': 'FR', 'es': 'ES', 'it': 'IT', 'pt': 'PT',
    'nl': 'NL', 'pl': 'PL', 'ko': 'KO', 'th': 'TH', 'vi': 'VI', 'id': 'ID', 'my': 'MY',
}

# ✅ 新代碼 (僅保留 DeepL 實際支援的語言)
lang_map = {
    'en': 'EN', 'ja': 'JA', 'ru': 'RU',
    'zh-TW': 'ZH-HANT', 'zh-CN': 'ZH-HANS',
    'de': 'DE', 'fr': 'FR', 'es': 'ES', 'it': 'IT', 'pt': 'PT',
    'nl': 'NL', 'pl': 'PL', 'ko': 'KO',
}
```

**影響**:
- 泰文、越南文、印尼文、緬甸文現在會跳過 DeepL fallback
- 如果 Google Translate 失敗，這些語言會返回翻譯失敗
- 這些語言仍然可以透過配置支援，但需要依賴 Google Translate

---

## 修復摘要

| 問題 | 狀態 | 影響 | 優先級 |
|------|------|------|--------|
| DeepL HTTP 403 認證 | ✅ 已修復 | 所有 DeepL 翻譯請求 | 🔴 極高 |
| Google Translate 速率限制 | ✅ 已改進 | 高流量翻譯場景 | 🟠 高 |
| DeepL 不支援語言 | ✅ 已修復 | 泰文、越南文等 | 🟡 中 |

---

## 測試建議

1. **測試 DeepL 認證**:
   ```python
   from translations import deepl_translator
   result, reason = deepl_translator.translate("Hello", "zh-TW")
   # 應該返回成功翻譯，而非 http_403
   ```

2. **測試高流量場景**:
   - 並發多個翻譯請求
   - 觀察是否還有 429 錯誤
   - 檢查指數退避是否生效

3. **測試不支援語言的 fallback**:
   ```python
   from services import translation_service
   result = translation_service.translate_text("Hello", "id")
   # 如果 Google 失敗，應該返回適當的錯誤訊息，而非嘗試 DeepL
   ```

---

## 後續優化建議

1. **實施請求隊列** - 防止同時發送過多請求
2. **更長的快取 TTL** - 減少重複翻譯相同文本
3. **考慮官方 Google Cloud Translation API** - 如果預算允許
4. **監控速率限制指標** - 追蹤 429 錯誤頻率

---

## 變更詳情

- **修改檔案**:
  - `FanFan/config.py` - 增加 MAX_TRANSLATION_RETRIES
  - `FanFan/translations/deepl_translator.py` - 修復認證、移除不支援語言、改進重試邏輯
  - `FanFan/translations/google_translator.py` - 改進重試邏輯
