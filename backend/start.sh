#!/bin/sh

# 刪除舊資料庫
echo "清理舊資料庫..."
rm -f /app/data/game.db
rm -f /app/data/ad_system.db

# 清空 patch 資料夾
echo "清理 patch 資料夾..."
rm -rf /app/patches/*

echo "啟動應用程式..."
python app.py
