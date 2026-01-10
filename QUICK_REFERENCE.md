# 快速模組參考指南

## 📖 常用匯入

### 讀取配置
```python
import config
print(config.DEEPL_API_KEY)
print(config.MAX_CONCURRENT_TRANSLATIONS)
```

### 文件操作
```python
from utils.file_utils import load_json, save_json
data = load_json("data.json")
save_json("data.json", data)
```

### 翻譯服務
```python
from services.translation_service import translate_text
result = translate_text("Hello", "zh-TW", group_id="G123")
```

### 租戶管理
```python
from services.tenant_service import (
    create_tenant, 
    get_tenant_by_group, 
    update_tenant_stats
)

token, expires_at = create_tenant("U123", months=3)
user_id, tenant = get_tenant_by_group("G123")
update_tenant_stats(user_id, translate_count=5)
```

### 群組管理
```python
from services.group_service import (
    get_group_langs,
    set_group_langs,
    get_engine_pref,
    touch_group_activity
)

langs = get_group_langs("G123")
set_group_langs("G123", {"zh-TW", "en"})
engine = get_engine_pref("G123")  # "google" or "deepl"
touch_group_activity("G123")
```

### 系統監控
```python
from utils.system_utils import monitor_memory, start_inactive_checker
memory_mb = monitor_memory()
start_inactive_checker(app)
```

### LINE 工具
```python
from utils.line_utils import create_reply_message, is_group_admin
create_reply_message(line_bot_api, token, {"type": "text", "text": "Hello"})
is_admin = is_group_admin(user_id, group_id, data)
```

### 翻譯引擎（低級）
```python
from translations.google_translator import translate as google_translate
from translations.deepl_translator import translate as deepl_translate

text, reason = google_translate("Hello", "zh-TW")
text, reason = deepl_translate("Hello", "zh-TW")
```

### 資料庫模型
```python
from models import db, GroupTranslateSetting, GroupActivity, GroupEnginePreference

# 查詢
setting = GroupTranslateSetting.query.filter_by(group_id="G123").first()

# 新增
new_setting = GroupTranslateSetting(group_id="G123", languages="zh-TW,en")
db.session.add(new_setting)
db.session.commit()

# 更新
setting.languages = "zh-TW,en,ja"
db.session.commit()

# 刪除
db.session.delete(setting)
db.session.commit()
```

## 🔧 常見任務

### 任務：添加新翻譯引擎

1. 創建新檔案 `translations/xxx_translator.py`：
```python
def translate(text, target_lang):
    """實現翻譯邏輯"""
    try:
        # ... 翻譯代碼 ...
        return translated_text, 'success'
    except Exception as e:
        return None, 'error_code'
```

2. 在 `translation_service.py` 中修改邏輯：
```python
from translations import xxx_translator

def translate_text(text, target_lang, group_id=None):
    # 嘗試新引擎
    translated, reason = xxx_translator.translate(text, target_lang)
    if translated:
        return translated
    # ... fallback 邏輯 ...
```

### 任務：添加新指令

1. 在 `main.py` 的 `handle_message()` 中添加：
```python
if lower == '/my_command':
    # 實現指令邏輯
    result = my_service.do_something(user_id, group_id)
    line_utils.create_reply_message(line_bot_api, event['replyToken'], 
                                    {"type": "text", "text": result})
    return
```

2. 複雜邏輯可提取到 `services/` 中

### 任務：添加新服務

1. 在 `services/` 創建新模組 `my_service.py`
2. 定義函數，使用需要的資料庫模型和工具
3. 在 `main.py` 或其他模組中匯入使用

### 任務：添加資料庫模型

1. 在 `models.py` 中定義新模型：
```python
class MyModel(db.Model):
    __tablename__ = "my_table"
    
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

2. 應用將在啟動時自動建表（`init_db()` 函數）

## 📊 性能監控

### 查看翻譯引擎性能
在日誌中查找：
- `[Google]` - Google Translate 日誌
- `[DeepL]` - DeepL API 日誌

### 檢查系統狀態
```bash
curl http://localhost:5000/status
```

回應：
```json
{
  "status": "ok",
  "uptime_seconds": 3600,
  "memory_mb": 150.5,
  "translation_queue": 4
}
```

## 🐛 調試技巧

### 調試翻譯
```python
# 直接測試翻譯引擎
from translations import google_translator, deepl_translator

text, reason = google_translator.translate("你好", "en")
print(f"Google: {text} (reason: {reason})")

text, reason = deepl_translator.translate("你好", "en")
print(f"DeepL: {text} (reason: {reason})")
```

### 調試租戶
```python
from services.tenant_service import *

# 查看所有租戶
data = load_json(config.DATA_FILE)
for user_id, tenant in data.get('tenants', {}).items():
    print(f"{user_id}: {tenant}")
```

### 調試群組設定
```python
from services.group_service import *

# 查看群組語言
langs = get_group_langs("G123")
print(f"Languages: {langs}")

# 查看引擎偏好
engine = get_engine_pref("G123")
print(f"Engine: {engine}")
```

## 🚀 部署檢查清單

- [ ] 所有模組都能正常匯入
- [ ] 環境變數已設定（.env）
- [ ] 資料庫已初始化
- [ ] DeepL 語言列表已載入
- [ ] 翻譯引擎可正常工作
- [ ] LINE Webhook 簽名驗證通過
- [ ] 日誌輸出正常
- [ ] **性能優化已啟用**（快取層工作）

## 📊 性能監控（新增）

### 檢查系統狀態
```bash
curl http://localhost:5000/status | jq
```

**回應示例**：
```json
{
  "status": "ok",
  "uptime": "2h 30m",
  "memory_mb": 156.3,
  "cache": {
    "translation_cache_size": 245,
    "group_langs_cache_size": 38
  }
}
```

### 快取統計解讀
- `translation_cache_size` - 翻譯結果快取（3600 秒過期）
- `group_langs_cache_size` - 群組語言設定快取（300 秒過期）

### 性能優化效果
- 🟢 選單打開：**350ms → 50ms** (7 倍提升)
- 🟢 首次翻譯：**3-5s → 1-2s** (2-3 倍提升)
- 🟢 快取命中：**3-5s → 1ms** (3000+ 倍提升)

## 📞 獲取幫助

### 匯入錯誤
- 確保在專案根目錄執行
- 檢查 Python 路徑
- 驗證所有 `__init__.py` 存在

### 翻譯失敗
- 檢查 API Key 是否正確
- 查看日誌中的 `[Google]` / `[DeepL]` 錯誤
- 確認網路連接

### 資料庫錯誤
- 檢查 `DATABASE_URL` 配置
- 驗證資料庫服務運行
- 檢查遷移狀態

---

**快速參考版本：** 1.0
**更新日期：** 2026-01-10
