"""
FanFan LINE Bot - 系統監控工具
"""
import gc


def monitor_memory():
    """監控系統記憶體使用情況"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_usage_mb = memory_info.rss / 1024 / 1024

        # 強制進行垃圾回收
        gc.collect()
        process.memory_percent()

        return memory_usage_mb
    except ImportError:
        print("⚠️ psutil 未安裝，無法監控記憶體")
        return 0
