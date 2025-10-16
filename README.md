# AFS Prometheus Metrics Collector

An HTTP server that exposes AFS storage usage statistics as Prometheus metrics.

## Quick Start

### 1. 使用 Docker (推荐)

```bash
# 构建镜像
docker build -t afs-metrics-collector .

# 运行容器
docker run -d --name afs-metrics -p 8080:8080 \
  -e AFS_ACCESS_KEY=your_access_key \
  -e AFS_SECRET_KEY=your_secret_key \
  -e AFS_BASE_URL=https://afs.cn-sh-01.sensecoreapi.cn \
  afs-metrics-collector

# 查看日志
docker logs -f afs-metrics
```

### 2. 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置应用
# 方式1：使用 YAML 配置文件
cp config.yaml.example config.yaml
# 编辑 config.yaml，设置你的 AFS 凭据和卷信息

# 方式2：使用环境变量
cp .env.example .env
# 编辑 .env 文件

# 验证配置（可选）
python validate-config.py

# 运行服务器
python server.py
```

## 服务端点

- `/metrics` - Prometheus 指标端点
- `/health/ready` - 就绪检查
- `/health/live` - 存活检查

## 配置说明

应用支持两种配置方式：

### 1. YAML 配置文件 (推荐)
```bash
# 复制并编辑配置文件
cp config.yaml.example config.yaml
# 编辑 config.yaml，设置你的 AFS 凭据
```

主要配置项：
- `afs.access_key` - AFS API 访问密钥 (必填)
- `afs.secret_key` - AFS API 密钥 (必填)
- `afs.base_url` - AFS API 基础 URL
- `afs.volumes` - 要监控的 AFS 卷列表 (必填)
  - `volume_id` - AFS 卷 ID
  - `zone` - AFS 可用区
- `server.host` - 服务器监听地址 (默认: 0.0.0.0)
- `server.port` - HTTP 服务端口 (默认: 8080)
- `collection.timeout_seconds` - API 请求超时时间 (默认: 25s)
- `collection.max_retries` - 最大重试次数 (默认: 3)
- `collection.cache_duration` - 缓存持续时间 (默认: 30s)
- `logging.level` - 日志级别 (默认: INFO)

### 2. 环境变量
```bash
# 复制并编辑环境变量文件
cp .env.example .env
```

环境变量优先级高于配置文件设置。

## 监控集成

可以将此服务集成到现有的 Prometheus 监控系统中：

```yaml
# prometheus.yml 配置示例
scrape_configs:
  - job_name: 'afs-metrics'
    static_configs:
      - targets: ['localhost:8080']
    scrape_interval: 30s
    metrics_path: /metrics
```