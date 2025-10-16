# 多阶段构建，优化镜像大小
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖到临时目录
RUN pip install --no-cache-dir --user -r requirements.txt

# 生产阶段
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 创建非 root 用户
RUN groupadd -r afs && useradd -r -g afs -d /app -s /bin/bash afs

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 设置工作目录
WORKDIR /app

# 从构建阶段复制 Python 包
COPY --from=builder /root/.local /home/afs/.local

# 复制应用代码
COPY --chown=afs:afs src/ ./src/
COPY --chown=afs:afs server.py ./
COPY --chown=afs:afs config.yaml.example ./config.yaml.example
COPY --chown=afs:afs .env.example ./.env.example

# 创建必要的目录
RUN mkdir -p /app/logs /app/config && \
    chown -R afs:afs /app

# 切换到非 root 用户
USER afs

# 将用户本地包路径添加到 PATH
ENV PATH=/home/afs/.local/bin:$PATH

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

# 启动命令
CMD ["python", "server.py"]