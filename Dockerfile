# 使用 Python 3.11 slim 镜像
FROM sandai-registry-vpc.cn-beijing.cr.aliyuncs.com/mirrors/python:3.11-slim

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 配置 apt 使用阿里云镜像源并安装系统依赖
RUN rm -rf /etc/apt/sources.list.d/* && \
    rm -f /etc/apt/sources.list && \
    echo "# 阿里云 Debian 镜像源" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 配置 pip 使用阿里云镜像源并安装 Python 依赖
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.aliyun.com && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY server.py ./
COPY config.yaml.example ./config.yaml.example
COPY .env.example ./.env.example

# 创建必要的目录
RUN mkdir -p /app/logs /app/config

# 暴露端口
EXPOSE 8080

# 健康检查 - 使用 TCP 端口检测
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD timeout 3 bash -c '</dev/tcp/localhost/8080' || exit 1

# 启动命令
CMD ["python", "server.py"]