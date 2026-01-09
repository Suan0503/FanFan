# 資料庫遷移說明

## 📋 更新內容

### 1. 資料結構改變
- ✅ 從 `data.json` 遷移到 **資料庫**（PostgreSQL/SQLite）
- ✅ 新增租戶訂閱系統（Tenant-based subscription）
- ✅ 自動到期降級機制
- ✅ 到期提醒機制（7天、1天）

### 2. 新增資料表

#### Tenant（租戶）
- `user_id`: LINE User ID
- `token`: 個人 TOKEN
- `expires_at`: 到期日
- `plan`: 方案（premium/free）
- `translate_count`: 翻譯次數統計
- `char_count`: 字元數統計
- `reminded_7days/reminded_1day`: 提醒標記

#### Group（群組）
- `group_id`: LINE Group ID
- `tenant_id`: 所屬租戶
- `auto_translate`: 自動翻譯開關
- `voice_translation`: 語音翻譯開關
- `engine_pref`: 翻譯引擎偏好（google/deepl）

#### UserPreference（用戶語言偏好）
- `group_id`: 群組 ID
- `user_id`: 用戶 ID
- `languages`: 語言列表 JSON

#### GroupAdmin（群組管理員）
- `group_id`: 群組 ID
- `user_id`: 管理員 User ID

#### Whitelist（白名單）
- `user_id`: 白名單用戶 ID

### 3. 新增指令

#### `/管理員選單`
- 權限：MASTER/白名單
- 功能：
  - 查看所有租戶列表
  - 查看活躍租戶數
  - 查看系統統計
  - 管理指令清單

#### `/付費選單`
- 權限：付費用戶（有效訂閱）
- 功能：
  - 查看訂閱資訊（到期日、剩餘天數）
  - 查看使用統計（翻譯次數、字元數）
  - 查看可用功能
  - 管理指令清單
- 特點：**必須有剩餘天數才能使用**

### 4. 自動機制

#### 自動降級
- 到期時自動從 `premium` 降級為 `free`
- **不會停用服務**，只是功能受限
- 發送通知給用戶

#### 到期提醒
- **剩7天**：發送一次提醒
- **剩1天**：發送一次緊急提醒
- 使用資料庫記錄已提醒狀態，避免重複發送

### 5. 定時任務
- 每24小時自動檢查一次所有租戶
- 執行降級和提醒動作
- 背景執行緒，不影響主服務

## 🚀 部署步驟

### 1. 安裝依賴
```bash
# 安裝 Python 套件
pip install -r requirements.txt
```

### 2. 設定環境變數
```bash
# .env 檔案
DATABASE_URL=postgresql://user:password@host:port/database
# 或使用 SQLite（本地開發）
# DATABASE_URL=sqlite:///fanfan.db

CHANNEL_ACCESS_TOKEN=your_line_token
CHANNEL_SECRET=your_line_secret
```

### 3. 首次啟動
程式會自動：
1. 建立所有資料表
2. 從 `data.json` 遷移資料到資料庫
3. 啟動定時檢查任務

```bash
python main.py
```

### 4. 驗證遷移
```bash
# 在 LINE 中測試指令
/管理員選單    # 查看租戶列表
/付費選單      # 查看個人訂閱資訊
/租戶資訊      # 查看當前群組租戶
/統計          # 查看系統統計
```

## 📝 使用說明

### 管理員操作

#### 1. 設定租戶管理員
```
/設定管理員 @用戶 6
```
- 為指定用戶創建6個月訂閱
- 自動將當前群組加入該租戶管理
- 設定為群組臨時管理員

#### 2. 查看租戶資訊
```
/租戶資訊
```
- 查看當前群組的租戶資訊
- 包含到期日、統計資料、管理群組數

#### 3. 查看系統統計
```
/統計
```
- 總群組數、活躍租戶數
- 總翻譯次數、總字元數
- 語言使用統計

### 付費用戶操作

#### 1. 查看付費選單
```
/付費選單
```
- 訂閱資訊（到期日、剩餘天數）
- 使用統計（翻譯次數、字元數）
- 可用功能列表
- 管理指令

#### 2. 管理翻譯設定
```
/選單          # 設定翻譯語言
/語音翻譯      # 切換語音翻譯
/引擎          # 切換翻譯引擎
/自動翻譯      # 切換自動翻譯
```

## ⚠️ 注意事項

### 1. 資料遷移
- 首次啟動時會自動從 `data.json` 遷移
- 遷移後建議備份 `data.json`
- 可以刪除 `data.json`，系統已完全使用資料庫

### 2. 到期處理
- 到期後自動降級為免費版
- 不會刪除群組或資料
- 用戶可隨時續費恢復

### 3. 提醒機制
- 每個提醒只發送一次
- 使用資料庫記錄已提醒狀態
- 續費後會重置提醒標記

### 4. 效能考量
- 使用資料庫索引加速查詢
- 統計資料即時更新
- 定時任務不影響主服務

## 🔧 故障排除

### 資料庫連接失敗
```bash
# 檢查 DATABASE_URL
echo $DATABASE_URL

# 測試連接
psql $DATABASE_URL
```

### 遷移失敗
```bash
# 手動刪除資料表重新遷移
# 注意：這會清除所有資料
python
>>> from main import app, db
>>> with app.app_context():
...     db.drop_all()
...     db.create_all()
```

### 提醒未發送
```bash
# 檢查定時任務是否運行
# 查看日誌輸出
# 確認 LINE TOKEN 有效
```

## 📊 資料庫 Schema

```sql
-- Tenant
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL,
    token VARCHAR(500) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    plan VARCHAR(20) DEFAULT 'premium',
    translate_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    reminded_7days BOOLEAN DEFAULT FALSE,
    reminded_1day BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Group
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    group_id VARCHAR(100) UNIQUE NOT NULL,
    tenant_id INTEGER REFERENCES tenants(id),
    auto_translate BOOLEAN DEFAULT TRUE,
    voice_translation BOOLEAN DEFAULT TRUE,
    engine_pref VARCHAR(20) DEFAULT 'google',
    created_at TIMESTAMP DEFAULT NOW()
);

-- UserPreference
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    user_id VARCHAR(100) NOT NULL,
    languages JSON DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

-- GroupAdmin
CREATE TABLE group_admins (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    user_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

-- Whitelist
CREATE TABLE whitelists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🎯 後續優化

- [ ] 加入續費指令（自動化）
- [ ] 多方案支援（不同功能組合）
- [ ] 使用量限制（付費版無限，免費版限制）
- [ ] Dashboard 管理介面
- [ ] 報表匯出功能
- [ ] 批次操作指令

---

**最後更新：2026-01-09**
