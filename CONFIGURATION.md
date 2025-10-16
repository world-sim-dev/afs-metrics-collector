# AFS Metrics Collector 配置指南

## 概述

AFS Metrics Collector 支持多种配置方式，环境变量优先级高于配置文件。

## 配置方式

### 1. 环境变量配置 (推荐用于容器化部署)

#### 必需配置
```bash
# AFS API 凭据
AFS_ACCESS_KEY=your_access_key
AFS_SECRET_KEY=your_secret_key

# AFS 卷配置 (JSON 格式)
AFS_VOLUMES='[{"volume_id": "vol-123", "zone": "cn-sh-01e"}]'
```

#### 可选配置
```bash
# AFS API 配置
AFS_BASE_URL=https://afs.cn-sh-01.sensecoreapi.cn

# 服务器配置
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
REQUEST_TIMEOUT=30

# 数据收集配置
COLLECTION_TIMEOUT=25
COLLECTION_MAX_RETRIES=3
COLLECTION_RETRY_DELAY=2
COLLECTION_CACHE_DURATION=30

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 2. YAML 配置文件

```yaml
afs:
  access_key: "your_access_key"
  secret_key: "your_secret_key"
  base_url: "https://afs.cn-sh-01.sensecoreapi.cn"
  volumes:
    - volume_id: "vol-123"
      zone: "cn-sh-01e"
    - volume_id: "vol-456"
      zone: "cn-sh-01f"

server:
  host: "0.0.0.0"
  port: 8080
  request_timeout: 30

collection:
  max_retries: 3
  retry_delay: 2
  timeout_seconds: 25
  cache_duration: 30

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## AFS_VOLUMES 格式

### 单个卷
```bash
AFS_VOLUMES='[{"volume_id": "vol-123", "zone": "cn-sh-01e"}]'
```

### 多个卷
```bash
AFS_VOLUMES='[
  {"volume_id": "vol-123", "zone": "cn-sh-01e"},
  {"volume_id": "vol-456", "zone": "cn-sh-01f"},
  {"volume_id": "vol-789", "zone": "cn-sh-01g"}
]'
```

### 向后兼容 (单卷)
```bash
# 仍然支持，但推荐使用 AFS_VOLUMES
AFS_VOLUME_ID=vol-123
AFS_ZONE=cn-sh-01e
```

## 日志格式

### JSON 格式 (推荐用于生产环境)
```bash
LOG_FORMAT=json
```
输出示例：
```json
{"timestamp": "2025-10-16 17:45:09", "logger": "afs.client", "level": "INFO", "message": "API request successful"}
```

### 简单格式
```bash
LOG_FORMAT=simple
```
输出示例：
```
INFO - API request successful
```

### 自定义格式
```bash
LOG_FORMAT="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

## 配置验证

### 使用验证脚本
```bash
python validate-config.py
```

### 使用服务器验证
```bash
python server.py --validate-config
```

### 测试连接
```bash
python server.py --test-connection
```

## Docker 部署示例

### 基本部署
```bash
docker run -d --name afs-metrics -p 8080:8080 \
  -e AFS_ACCESS_KEY=your_access_key \
  -e AFS_SECRET_KEY=your_secret_key \
  -e AFS_VOLUMES='[{"volume_id": "vol-123", "zone": "cn-sh-01e"}]' \
  -e LOG_FORMAT=json \
  afs-metrics-collector
```

### 使用配置文件
```bash
docker run -d --name afs-metrics -p 8080:8080 \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -e LOG_FORMAT=json \
  afs-metrics-collector
```

## Kubernetes 部署示例

### 使用 Secret 和 ConfigMap
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: afs-credentials
stringData:
  AFS_ACCESS_KEY: "your_access_key"
  AFS_SECRET_KEY: "your_secret_key"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: afs-config
data:
  AFS_VOLUMES: '[{"volume_id": "vol-123", "zone": "cn-sh-01e"}]'
  LOG_FORMAT: "json"
  LOG_LEVEL: "INFO"
```

### 部署脚本
```bash
./deploy-k8s.sh -k YOUR_ACCESS_KEY -s YOUR_SECRET_KEY -v YOUR_VOLUME_ID
```

## 故障排除

### 常见错误

1. **"At least one AFS volume must be configured"**
   - 确保设置了 `AFS_VOLUMES` 或 `AFS_VOLUME_ID`/`AFS_ZONE`

2. **"Invalid AFS_VOLUMES format"**
   - 检查 JSON 格式是否正确
   - 确保包含 `volume_id` 和 `zone` 字段

3. **"Unable to configure formatter"**
   - 检查 `LOG_FORMAT` 设置
   - 使用 `json`, `simple` 或有效的 Python 日志格式字符串

### 调试技巧

1. **启用调试日志**
   ```bash
   LOG_LEVEL=DEBUG python server.py
   ```

2. **验证配置**
   ```bash
   python validate-config.py
   ```

3. **测试 JSON 格式**
   ```bash
   echo $AFS_VOLUMES | python -m json.tool
   ```

## 安全说明

### 用户权限
- **Docker**: 容器以 root 用户运行，便于文件系统访问和调试
- **Kubernetes**: Pod 以 root 用户运行 (runAsUser: 0)
- **本地运行**: 使用当前用户权限

### 网络安全
- 容器只暴露必要的端口 (8080)
- 使用 TCP 端口检测进行健康检查
- 支持 Kubernetes NetworkPolicy 限制网络访问

## 最佳实践

1. **生产环境**
   - 使用 `LOG_FORMAT=json` 便于日志分析
   - 设置适当的资源限制
   - 使用 Secret 管理敏感信息
   - 配置网络策略限制访问

2. **开发环境**
   - 使用 `LOG_LEVEL=DEBUG` 获取详细信息
   - 使用配置文件便于调试
   - 可以使用非特权用户运行

3. **监控**
   - 定期检查 `/metrics` 端点
   - 监控容器健康状态
   - 设置适当的告警规则
   - 监控资源使用情况