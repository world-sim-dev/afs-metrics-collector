# AFS Prometheus Metrics Collector

An HTTP server that exposes AFS storage usage statistics as Prometheus metrics.

## Quick Start

### 1. 使用 Docker (推荐)

```bash
# 构建镜像（使用阿里云镜像源优化）
docker build -t afs-metrics-collector .

# 或使用构建脚本
./docker-build.sh

# 运行容器
docker run -d --name afs-metrics -p 8080:8080 \
  -e AFS_ACCESS_KEY=your_access_key \
  -e AFS_SECRET_KEY=your_secret_key \
  -e AFS_BASE_URL=https://afs.cn-sh-01.sensecoreapi.cn \
  afs-metrics-collector

# 查看日志
docker logs -f afs-metrics
```

> **优化说明**: Dockerfile 已配置使用阿里云的 APT 和 PyPI 镜像源，在中国大陆环境下可显著提高构建速度。

### 2. 使用 Kubernetes

```bash
# 快速部署（使用部署脚本）
./deploy-k8s.sh -k YOUR_ACCESS_KEY -s YOUR_SECRET_KEY -v YOUR_VOLUME_ID

# 或使用简化版本
./deploy-k8s.sh --simple -k YOUR_ACCESS_KEY -s YOUR_SECRET_KEY -v YOUR_VOLUME_ID

# 手动部署
kubectl apply -f k8s-deployment.yaml

# 查看状态
./deploy-k8s.sh --status

# 访问服务
kubectl port-forward -n afs-metrics service/afs-metrics-service 8080:8080

# 删除部署
./deploy-k8s.sh --delete
```

### 3. 本地开发

```bash
# 安装运行时依赖
pip install -r requirements.txt

# 或安装开发依赖（包含测试工具）
pip install -r requirements-dev.txt

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