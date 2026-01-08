# 群組功能配置範例

## 配置檔案格式

以下是 `data.json` 中 `feature_switches` 的範例配置：

```json
{
  "user_whitelist": [],
  "user_prefs": {},
  "voice_translation": {},
  "group_admin": {},
  "translate_engine_pref": {},
  "feature_switches": {
    "C1234567890abcdef": {
      "features": [
        "translate",
        "auto_translate"
      ],
      "token": "abc123def456ghi789",
      "created_at": "2026-01-08T10:30:00.000000"
    },
    "C9876543210fedcba": {
      "features": [
        "translate",
        "voice",
        "auto_translate",
        "statistics"
      ],
      "token": "xyz789uvw456rst123",
      "created_at": "2026-01-08T11:00:00.000000"
    },
    "Cabcdef1234567890": {
      "features": [
        "translate",
        "voice",
        "admin",
        "auto_translate",
        "statistics"
      ],
      "token": "pqr456mno123jkl789",
      "created_at": "2026-01-08T11:30:00.000000"
    }
  }
}
```

## 預設配置說明

### 群組 ID: C1234567890abcdef (免費版)
**功能清單**:
- `translate` - 基本翻譯功能
- `auto_translate` - 自動翻譯

**TOKEN**: `abc123def456ghi789`

**使用場景**: 
- 試用用戶
- 個人使用
- 基本需求

### 群組 ID: C9876543210fedcba (標準版)
**功能清單**:
- `translate` - 基本翻譯功能
- `voice` - 語音翻譯
- `auto_translate` - 自動翻譯
- `statistics` - 統計功能

**TOKEN**: `xyz789uvw456rst123`

**使用場景**:
- 付費用戶
- 小型團隊
- 商務應用

### 群組 ID: Cabcdef1234567890 (專業版)
**功能清單**:
- `translate` - 基本翻譯功能
- `voice` - 語音翻譯
- `admin` - 管理功能
- `auto_translate` - 自動翻譯
- `statistics` - 統計功能

**TOKEN**: `pqr456mno123jkl789`

**使用場景**:
- 高級付費用戶
- 企業客戶
- 完整功能需求

## 手動配置步驟

### 方法 1: 使用指令（推薦）
```bash
# 在 LINE 群組中執行
/功能設定                    # 查看當前狀態
/設定功能 translate          # 開啟/關閉翻譯
/設定功能 voice             # 開啟/關閉語音
/設定功能 auto_translate    # 開啟/關閉自動翻譯
/設定功能 statistics        # 開啟/關閉統計
/設定功能 admin             # 開啟/關閉管理
/生成token                  # 生成新 TOKEN
```

### 方法 2: 直接編輯 data.json
1. 停止服務
2. 編輯 `data.json`
3. 在 `feature_switches` 下新增群組配置
4. 重啟服務

**注意**: 手動編輯時請確保 JSON 格式正確！

## 批量配置範例

### Python 腳本配置
```python
import json
from datetime import datetime

# 讀取現有配置
with open('data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 新增配置
data.setdefault('feature_switches', {})

# 配置多個群組
groups_config = {
    'GROUP_ID_1': ['translate', 'auto_translate'],  # 免費版
    'GROUP_ID_2': ['translate', 'voice', 'auto_translate', 'statistics'],  # 標準版
    'GROUP_ID_3': ['translate', 'voice', 'admin', 'auto_translate', 'statistics'],  # 專業版
}

import secrets
for group_id, features in groups_config.items():
    data['feature_switches'][group_id] = {
        'features': features,
        'token': secrets.token_urlsafe(16),
        'created_at': datetime.utcnow().isoformat()
    }

# 儲存配置
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("配置完成！")
```

## 功能組合建議

### 最小配置（僅翻譯）
```json
"features": ["translate"]
```

### 推薦基礎配置
```json
"features": ["translate", "auto_translate"]
```

### 推薦標準配置
```json
"features": ["translate", "voice", "auto_translate", "statistics"]
```

### 完整配置
```json
"features": ["translate", "voice", "admin", "auto_translate", "statistics"]
```

## 功能依賴關係

- `auto_translate` 需要 `translate`
- `voice` 可獨立運作，但建議搭配 `translate`
- `statistics` 獨立運作
- `admin` 獨立運作

## TOKEN 管理

### TOKEN 格式
- 使用 `secrets.token_urlsafe(16)` 生成
- 長度約 22 個字元
- URL 安全字元組成

### TOKEN 安全性
- 每個群組唯一
- 不可猜測
- 建議定期更換

### 重新生成 TOKEN
```bash
# 在 LINE 中執行
/生成token
```
舊 TOKEN 會被新 TOKEN 取代，但功能配置保持不變。

## 配置驗證

### 檢查配置是否生效
1. 在群組中輸入 `/功能設定`
2. 查看顯示的功能狀態
3. 確認 TOKEN 是否正確

### 測試功能限制
1. 嘗試使用關閉的功能
2. 應看到提示: "❌ 本群組未開啟[功能名稱]功能"

## 故障排除

### 配置未生效
1. 檢查 JSON 格式是否正確
2. 確認 group_id 是否正確
3. 重啟服務

### TOKEN 無法顯示
1. 確認有執行 `/生成token`
2. 檢查 `data.json` 是否有該群組的設定
3. 確認權限（只有主人可查看）

### 功能狀態錯誤
1. 使用 `/功能設定` 查看實際狀態
2. 重新執行 `/設定功能` 調整
3. 檢查 `data.json` 中的實際配置

## 備份建議

### 定期備份
```bash
# 備份配置
cp data.json data.json.backup.$(date +%Y%m%d)

# 或使用 git
git add data.json
git commit -m "Update feature switches config"
```

### 還原配置
```bash
# 從備份還原
cp data.json.backup.20260108 data.json

# 重啟服務
python main.py
```

---

**提示**: 建議先在測試群組中驗證配置，確認無誤後再應用到正式群組。
