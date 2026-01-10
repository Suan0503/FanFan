# FanFan LINE Bot - 模組化架構說明

## 📁 專案結構

```
FanFan/
├── main.py (✅ 原始檔案 - 保留備份)
├── main_new.py (🆕 模組化版本入口 - 可直接替換 main.py)
├── config.py (⚙️ 配置和常數)
├── models.py (🗄️ 資料庫模型)
│
├── translations/ (🌐 翻譯引擎)
│   ├── __init__.py
│   ├── deepl_translator.py (DeepL API 介面)
│   └── google_translator.py (Google Translate 介面)
│
├── services/ (🎯 業務邏輯層)
│   ├── __init__.py
│   ├── translation_service.py (翻譯協調，Google 優先 + DeepL 備援)
│   ├── tenant_service.py (租戶訂閱管理)
│   └── group_service.py (群組設定、語言管理、活躍監控)
│
├── handlers/ (📨 事件處理器 - 預留擴展位置)
│   └── __init__.py
│
├── utils/ (🔧 工具函數)
│   ├── __init__.py
│   ├── file_utils.py (JSON 檔案操作)
│   ├── system_utils.py (系統監控、Keep-Alive、自動檢查)
│   └── line_utils.py (LINE API 包裝、訊息回覆)
│
├── requirements.txt (依賴)
├── config_example.py (配置範例)
└── README.md (本文件)
```

## 🎯 模組功能說明

### 1. **config.py** - 集中配置
所有常數、環境變數、API 設定集中管理
- Flask、資料庫、LINE Bot 設定
- 翻譯服務參數（timeout、retry 次數）
- 系統參數（執行緒限制、檢查間隔）
- 語言映射表

**使用方式：**
```python
import config
print(config.DEEPL_API_KEY)
print(config.MAX_CONCURRENT_TRANSLATIONS)
```

### 2. **models.py** - 資料庫模型
SQLAlchemy ORM 模型定義
- `GroupTranslateSetting` - 群組翻譯語言設定
- `GroupActivity` - 群組最後活躍時間
- `GroupEnginePreference` - 群組翻譯引擎偏好

**使用方式：**
```python
from models import db, GroupTranslateSetting
setting = GroupTranslateSetting.query.filter_by(group_id=gid).first()
```

### 3. **translations/** - 翻譯引擎分離

#### deepl_translator.py
```python
from translations import deepl_translator
text, reason = deepl_translator.translate("Hello", "zh-TW")
```

#### google_translator.py
```python
from translations import google_translator
text, reason = google_translator.translate("Hello", "zh-TW")
```

都回傳 `(translated_text, reason_code)` 便於錯誤處理

### 4. **services/** - 核心業務邏輯

#### translation_service.py
統一翻譯入口，自動協調 Google 和 DeepL
```python
from services import translation_service
result = translation_service.translate_text(text, "zh-TW", group_id)
```
策略：Google 優先 → Google 失敗則 DeepL → 兩者都失敗才報錯

#### tenant_service.py
租戶訂閱管理
```python
from services import tenant_service
tenant_service.create_tenant(user_id, months=3)
tenant_service.update_tenant_stats(user_id, translate_count=1)
```

#### group_service.py
群組設定管理
```python
from services import group_service
langs = group_service.get_group_langs(group_id)
group_service.set_group_langs(group_id, {'zh-TW', 'en'})
group_service.touch_group_activity(group_id)
```

### 5. **utils/** - 工具函數

#### file_utils.py
JSON 檔案操作
```python
from utils import file_utils
data = file_utils.load_json("data.json")
file_utils.save_json("data.json", data)
```

#### system_utils.py
系統監控、自動檢查
```python
from utils import system_utils
memory = system_utils.monitor_memory()
system_utils.start_inactive_checker(app)
```

#### line_utils.py
LINE API 包裝
```python
from utils import line_utils
line_utils.create_reply_message(line_bot_api, token, message)
is_admin = line_utils.is_group_admin(user_id, group_id, data)
```

## 🔄 模組間調用關係

```
main.py (入口)
  ├── config (讀取配置)
  ├── models (初始化資料庫)
  ├── services (核心邏輯)
  │   ├── translation_service → translations (呼叫翻譯引擎)
  │   ├── tenant_service → utils/file_utils
  │   └── group_service → models + utils/file_utils
  ├── translations (翻譯引擎)
  │   ├── deepl_translator
  │   └── google_translator
  ├── utils (工具函數)
  │   ├── file_utils
  │   ├── system_utils
  │   └── line_utils
  └── handlers (事件處理 - 預留擴展)
```

## 🚀 使用步驟

### 步驟 1：備份原檔案
```bash
cp main.py main_backup.py
```

### 步驟 2：替換主文件
```bash
cp main_new.py main.py
```

### 步驟 3：測試運行
```bash
python main.py
```

## ✅ 功能對應表

| 功能 | 原 main.py 位置 | 模組化後位置 |
|------|----------------|-----------|
| 翻譯邏輯 | ~850 行 | `services/translation_service.py` |
| DeepL 引擎 | ~800 行 | `translations/deepl_translator.py` |
| Google 引擎 | ~900 行 | `translations/google_translator.py` |
| 租戶管理 | ~500 行 | `services/tenant_service.py` |
| 群組設定 | ~250 行 | `services/group_service.py` |
| 資料庫 | ~150 行 | `models.py` |
| 配置 | 分散 | `config.py` |
| 檔案操作 | ~50 行 | `utils/file_utils.py` |
| 系統監控 | ~100 行 | `utils/system_utils.py` |
| LINE API | ~100 行 | `utils/line_utils.py` |

## 📝 開發指南

### 添加新翻譯引擎
1. 在 `translations/` 新增 `xxx_translator.py`
2. 實現 `translate(text, target_lang)` 函數，回傳 `(text, reason)`
3. 在 `translation_service.py` 中添加邏輯

### 添加新指令
1. 在 `main.py` 的 `handle_message()` 中添加條件判斷
2. 必要的邏輯提取到 `services/` 或 `handlers/`

### 添加新服務
1. 在 `services/` 創建新模組
2. 從 `main.py` 導入並使用

## 🧪 測試

### 測試翻譯引擎
```bash
python -c "
from translations import google_translator, deepl_translator
text, reason = google_translator.translate('Hello', 'zh-TW')
print(f'Google: {text} ({reason})')

text, reason = deepl_translator.translate('Hello', 'zh-TW')
print(f'DeepL: {text} ({reason})')
"
```

### 測試服務
```bash
python -c "
from services import translation_service
text = translation_service.translate_text('Hello', 'zh-TW')
print(f'Result: {text}')
"
```

### 測試檔案操作
```bash
python -c "
from utils import file_utils
data = file_utils.load_json('data.json')
print(f'Loaded: {len(data)} keys')
"
```

## 🔍 故障排除

### 模組匯入錯誤
確保在專案根目錄運行，且所有 `__init__.py` 都存在

### 資料庫錯誤
檢查 `DATABASE_URL` 配置，確認資料庫連接

### 翻譯失敗
查看日誌中的 `[Google]` 和 `[DeepL]` 標籤，判斷是哪個引擎失敗

## 📚 相關檔案

- `config.py` - 所有設定的單一來源
- `requirements.txt` - 必要依賴
- `.env` - 環境變數（不上傳 Git）

## 🎯 下一步優化方向

1. **handlers 模組化** - 將指令邏輯分離到 `handlers/` 中
2. **快取層** - 添加 Redis 快取翻譯結果
3. **日誌系統** - 統一日誌管理（logger）
4. **單元測試** - 為各模組添加 pytest 測試
5. **API 文檔** - 添加 Swagger API 文檔

---

**版本：** 1.0 模組化版本
**最後更新：** 2026-01-10
