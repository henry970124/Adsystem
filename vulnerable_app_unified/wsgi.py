#!/usr/bin/env python3
"""
WSGI entry point for Apache mod_wsgi
"""
import sys
import os
from pathlib import Path

# 添加應用目錄到 Python 路徑
sys.path.insert(0, '/app')

# 從 app.py 導入 Flask 應用並初始化
from app import app as application, init_app

# 初始化應用（創建資料庫、啟動 flag 更新線程等）
init_app()

# Apache mod_wsgi 會使用 'application' 這個變數
if __name__ == "__main__":
    # 這個分支不會在 Apache 下執行，僅供測試
    application.run()
