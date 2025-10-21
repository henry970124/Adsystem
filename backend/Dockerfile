FROM python:3.11-slim

WORKDIR /app

# 安裝 Docker CLI（僅客戶端）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
RUN pip install --no-cache-dir flask==3.0.0 flask-socketio==5.3.5 flask-cors==4.0.0 pyyaml==6.0.1 requests==2.31.0

# 複製應用文件
COPY . .

# 創建數據目錄
RUN mkdir -p /app/data

# 複製啟動腳本並確保使用 Unix 換行符
COPY start.sh /app/start.sh
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# 暴露端口
EXPOSE 5000

# 啟動應用
CMD ["/app/start.sh"]
