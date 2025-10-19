# A&D CTF System (Attack & Defense CTF)

🚩 一個完整的攻防 CTF (Capture The Flag) 競賽平台，支援多隊伍同時進行攻防演練。

## �� 功能特色

### 核心功能
- ✅ **即時攻防競賽** - 支援 12 支隊伍同時競技
- 🔧 **Patch 管理系統** - 隊伍可上傳修補漏洞的 patch
- 📦 **Patch 分享** - 查看並下載其他隊伍的防禦策略
- 🚩 **Flag 提交** - 攻擊其他隊伍並提交 Flag
- 📊 **即時計分板** - 實時更新隊伍排名和分數
- 🖥️ **服務健康檢查** - 自動檢測各隊服務狀態
- 📱 **響應式 Dashboard** - 美觀的網頁介面

### 計分系統
- **SLA 分數** - 服務可用性獎勵
- **防禦分數** - 成功防禦攻擊獲得分數
- **攻擊分數** - 成功攻擊其他隊伍獲得分數

## 🏗️ 系統架構

```
adsystem/
├── backend/              # 後端程式
│   ├── app.py           # 主應用程式
│   ├── auth.py          # 認證系統
│   ├── checker.py       # 服務檢查器
│   ├── models.py        # 資料模型
│   ├── scoring.py       # 計分系統
│   └── flag_manager.py  # Flag 管理
├── vulnerable_app_unified/  # 漏洞應用
│   └── app.py           # Flask 漏洞應用
├── dashboard.html       # Dashboard 頁面
├── docker-compose.yml   # Docker 編排
└── config-docker.yml    # 遊戲配置
```

## 🚀 快速開始

### 環境需求
- Docker
- Docker Compose
- Linux (推薦 Ubuntu 22.04)

### 部署步驟

1. **克隆專案**
```bash
git clone https://github.com/henry970124/Adsystem.git
cd Adsystem
```

2. **啟動服務**
```bash
docker-compose up -d
```

3. **訪問 Dashboard**
```
http://your-server-ip:8001
```

### 遊戲配置

編輯 `config-docker.yml` 設定遊戲參數：
```yaml
round_duration: 1800      # 回合時長（秒）
patch_duration: 60        # 補丁時長（秒）
service_check_interval: 5 # 服務檢查間隔（秒）
num_teams: 12            # 隊伍數量
```

## 🎮 使用指南

### 管理員操作
1. 使用 Admin Token 登入
2. 點擊「開始遊戲」啟動競賽
3. 監控所有隊伍狀態和日誌
4. 隨時停止遊戲

### 隊伍操作
1. 使用 Team Token 登入
2. **上傳 Patch**: 修補自己服務的漏洞
3. **瀏覽 Patches**: 查看並下載其他隊伍的 patch
4. **提交 Flag**: 攻擊其他隊伍並提交 Flag
5. **查看排行榜**: 即時查看自己的排名

## 🔐 安全性

- Token 認證系統
- 容器隔離
- 網路隔離
- 定期服務健康檢查

## 📦 新功能：Patch 瀏覽

隊伍可以：
- ✅ 查看所有隊伍已上傳的 patches
- ✅ 下載其他隊伍的 patch 學習防禦策略
- ✅ 查看上傳時間和檔案大小
- ✅ 自動更新列表（每 10 秒）

## 🛠️ 技術棧

- **後端**: Python 3.8, Flask, Flask-SocketIO
- **前端**: HTML5, CSS3, JavaScript
- **容器化**: Docker, Docker Compose
- **網頁伺服器**: Apache 2.4 + mod_wsgi
- **資料庫**: SQLite

## 📝 API 端點

### 認證
- `POST /api/auth/verify` - 驗證 Token

### 遊戲控制
- `POST /api/game/start` - 開始遊戲
- `POST /api/game/stop` - 停止遊戲
- `GET /api/status` - 獲取遊戲狀態

### Flag 操作
- `POST /api/flag/submit` - 提交 Flag
- `GET /api/flag/history` - Flag 提交記錄

### Patch 操作
- `POST /api/patch/upload` - 上傳 Patch
- `GET /api/patch/download` - 下載自己的 Patch
- `GET /api/patch/list` - 列出所有 Patches
- `GET /api/patch/download/<team_id>` - 下載其他隊伍的 Patch

### 排行榜
- `GET /api/scoreboard` - 獲取排行榜
- `GET /api/service-status` - 服務狀態

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

## 📄 授權

MIT License

## 👨‍�� 作者

henry970124

---

⭐ 如果這個專案對您有幫助，請給個 Star！
