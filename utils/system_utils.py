"""
System utilities - 系統監控工具
"""
import time
import os
import threading
import config


def monitor_memory():
    """監控系統記憶體使用情況"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_usage_mb = memory_info.rss / 1024 / 1024
        return memory_usage_mb
    except ImportError:
        return 0
    except Exception as e:
        print(f"❌ 監控記憶體失敗: {e}")
        return 0


def start_inactive_checker(app):
    """啟動背景執行緒，定期檢查未使用群組。"""
    from services.group_service import check_inactive_groups
    
    def _loop():
        while True:
            try:
                with app.app_context():
                    check_inactive_groups()
            except Exception as e:
                print(f"❌ 檢查未使用群組時發生錯誤: {e}")
            time.sleep(86400)  # 每天檢查一次

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def keep_alive(app):
    """每 KEEP_ALIVE_INTERVAL 秒檢查一次服務狀態"""
    import requests
    
    # 在 Railway 環境下不啟用 keep_alive，避免自我請求造成資源浪費
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print("🚆 偵測到 Railway 環境，停用 keep_alive")
        return
    
    retry_count = 0
    max_retries = 3
    last_restart = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            if current_time - last_restart >= config.AUTO_RESTART_INTERVAL:
                print("⏰ 執行定時重啟...")
                from utils.file_utils import load_json, save_json
                os._exit(0)

            response = requests.get('http://0.0.0.0:5000/', timeout=10)
            if response.status_code == 200:
                print("🔄 Keep-Alive 請求成功")
                retry_count = 0
            else:
                raise Exception(f"請求返回狀態碼: {response.status_code}")
        except Exception as e:
            retry_count += 1
            print(f"❌ Keep-Alive 請求失敗 (重試 {retry_count}/{max_retries})")
            
            if retry_count >= max_retries:
                print("🔄 重啟伺服器...")
                os._exit(1)
                
            time.sleep(30)
            continue

        time.sleep(config.KEEP_ALIVE_INTERVAL)
