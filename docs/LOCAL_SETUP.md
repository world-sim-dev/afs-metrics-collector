# 本地运行 AFS Prometheus 指标收集器

本文档介绍如何在本地环境中运行 AFS Prometheus 指标收集器服务器。

## 前置要求

1. **Python 环境**
   - Python 3.8 或更高版本
   - pip 包管理器

2. **AFS API 访问权限**
   - AFS Access Key（访问密钥）
   - AFS Secret Key（秘密密钥）
   - AFS API 基础 URL
   - 至少一个 AFS 卷的 volume_id 和 zone

## 安装步骤

### 1. 克隆项目并安装依赖

```bash
# 克隆项目（如果还没有）
git clone <repository-url>
cd afs-prometheus-metrics

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或者在 Windows 上：venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

有两种配置方式：**环境变量** 或 **配置文件**。

#### 方式一：使用环境变量（推荐用于开发）

创建 `.env` 文件或直接设置环境变量：

```bash
# 必需的 AFS API 配置
export AFS_ACCESS_KEY="your_actual_access_key"
export AFS_SECRET_KEY="your_actual_secret_key"
export AFS_BASE_URL="https://afs.cn-sh-01.sensecoreapi.cn"

# 必需的卷配置
export AFS_VOLUME_ID="your_volume_id"
export AFS_ZONE="your_zone"

# 可选的服务器配置
export SERVER_HOST="127.0.0.1"  # 本地开发使用 127.0.0.1
export SERVER_PORT="8080"
export REQUEST_TIMEOUT="30"

# 可选的收集配置
export MAX_RETRIES="3"
export RETRY_DELAY="2"
export COLLECTION_TIMEOUT="25"
export CACHE_DURATION="30"

# 可选的日志配置
export LOG_LEVEL="INFO"  # 或 DEBUG 用于详细日志
```

#### 方式二：使用配置文件

复制示例配置文件并修改：

```bash
# 复制配置文件模板
cp config.yaml.example config.yaml

# 编辑配置文件
nano config.yaml  # 或使用你喜欢的编辑器
```

修改 `config.yaml` 中的以下内容：

```yaml
afs:
  access_key: "你的实际访问密钥"
  secret_key: "你的实际秘密密钥"
  base_url: "https://afs.cn-sh-01.sensecoreapi.cn"
  volumes:
    - volume_id: "你的卷ID"
      zone: "你的区域"
    # 可以添加多个卷
    # - volume_id: "另一个卷ID"
    #   zone: "另一个区域"

server:
  host: "127.0.0.1"  # 本地开发
  port: 8080
  request_timeout: 30

collection:
  max_retries: 3
  retry_delay: 2
  timeout_seconds: 25
  cache_duration: 30

logging:
  level: "INFO"  # 或 "DEBUG" 用于详细日志
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## 运行服务器

### 1. 验证配置

在启动服务器之前，先验证配置是否正确：

```bash
# 使用专用配置验证工具（推荐）
python validate_config.py

# 或使用服务器内置验证
python server.py --validate-config

# 测试 AFS API 连接
python server.py --test-connection
```

如果发现配置问题，可以使用自动修复工具：

```bash
# 自动检测并提供修复建议
python fix_config.py
```

### 2. 启动服务器

```bash
# 使用默认配置启动
python server.py

# 使用特定配置文件启动
python server.py --config config.yaml

# 启用调试模式
python server.py --debug

# 查看帮助信息
python server.py --help
```

### 3. 验证服务运行

服务启动后，你应该看到类似以下的日志输出：

```
2025-10-15 18:45:00,123 - __main__ - INFO - Starting AFS Prometheus Metrics Collector
2025-10-15 18:45:00,124 - __main__ - INFO - Python version: 3.13.5
2025-10-15 18:45:00,125 - __main__ - INFO - Configuration validation successful
2025-10-15 18:45:00,126 - __main__ - INFO - Configured 1 AFS volumes:
2025-10-15 18:45:00,127 - __main__ - INFO -   1. Volume your_volume_id in zone your_zone
2025-10-15 18:45:00,128 - __main__ - INFO - Server will listen on 127.0.0.1:8080
2025-10-15 18:45:00,129 - __main__ - INFO - All components initialized successfully
2025-10-15 18:45:00,130 - __main__ - INFO - Starting HTTP server...
 * Running on http://127.0.0.1:8080
```

## 测试服务

### 1. 健康检查

```bash
# 存活检查
curl http://localhost:8080/health/live

# 就绪检查
curl http://localhost:8080/health/ready
```

### 2. 获取指标

```bash
# 获取 Prometheus 指标
curl http://localhost:8080/metrics

# 保存指标到文件
curl http://localhost:8080/metrics > metrics.txt
```

### 3. 使用浏览器

打开浏览器访问：
- http://localhost:8080/health/live - 存活检查
- http://localhost:8080/health/ready - 就绪检查  
- http://localhost:8080/metrics - Prometheus 指标

## 必需的环境变量

| 变量名 | 描述 | 示例值 | 必需 |
|--------|------|--------|------|
| `AFS_ACCESS_KEY` | AFS API 访问密钥 | `AKIAIOSFODNN7EXAMPLE` | ✅ |
| `AFS_SECRET_KEY` | AFS API 秘密密钥 | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` | ✅ |
| `AFS_BASE_URL` | AFS API 基础 URL | `https://afs.cn-sh-01.sensecoreapi.cn` | ✅ |
| `AFS_VOLUME_ID` | AFS 卷 ID（仅 UUID 部分） | `01987d8c-2d13-78cc-ba7b-1ad9beb7e552` | ✅ |
| `AFS_ZONE` | AFS 区域 | `cn-sh-01e` | ✅ |

⚠️ **重要提示**: `AFS_VOLUME_ID` 应该只包含 UUID，不要包含其他参数如 `&zone=xxx`。

## 可选的环境变量

| 变量名 | 描述 | 默认值 | 示例值 |
|--------|------|--------|--------|
| `SERVER_HOST` | 服务器监听地址 | `0.0.0.0` | `127.0.0.1` |
| `SERVER_PORT` | 服务器端口 | `8080` | `9090` |
| `REQUEST_TIMEOUT` | 请求超时时间（秒） | `30` | `60` |
| `MAX_RETRIES` | 最大重试次数 | `3` | `5` |
| `RETRY_DELAY` | 重试延迟（秒） | `2` | `1` |
| `COLLECTION_TIMEOUT` | 收集超时时间（秒） | `25` | `20` |
| `CACHE_DURATION` | 缓存持续时间（秒） | `30` | `60` |
| `LOG_LEVEL` | 日志级别 | `INFO` | `DEBUG` |

## 常见问题排查

### 1. 配置错误

**错误**: `Configuration error: AFS configuration is required`

**解决**: 确保设置了必需的 AFS 环境变量或配置文件。

```bash
# 检查环境变量
echo $AFS_ACCESS_KEY
echo $AFS_SECRET_KEY
echo $AFS_VOLUME_ID
echo $AFS_ZONE
```

### 2. 认证失败

**错误**: `AFS API connection test failed`

**解决**: 
1. 验证 Access Key 和 Secret Key 是否正确
2. 检查 AFS API URL 是否可访问
3. 确认网络连接正常

```bash
# 测试网络连接
curl -I https://afs.cn-sh-01.sensecoreapi.cn

# 验证配置
python server.py --test-connection
```

### 3. 端口被占用

**错误**: `Address already in use`

**解决**: 更改端口或停止占用端口的进程。

```bash
# 查看端口占用
lsof -i :8080

# 使用不同端口
export SERVER_PORT=8081
python server.py
```

### 4. 权限问题

**错误**: `Permission denied`

**解决**: 
1. 使用非特权端口（>1024）
2. 或使用 sudo 运行（不推荐用于开发）

```bash
# 使用非特权端口
export SERVER_PORT=8080
python server.py
```

## 开发模式

### 启用调试日志

```bash
export LOG_LEVEL=DEBUG
python server.py --debug
```

### 使用本地地址

```bash
export SERVER_HOST=127.0.0.1
export SERVER_PORT=8080
python server.py
```

### 快速重启

```bash
# 使用 Ctrl+C 停止服务器，然后重新启动
python server.py
```

## 性能测试

运行性能测试以验证服务器性能：

```bash
# 运行基准测试
python tests/run_performance_tests.py --benchmark

# 运行完整性能测试
python tests/run_performance_tests.py
```

## 生产部署

对于生产环境，请参考：
- [DEPLOYMENT.md](DEPLOYMENT.md) - 生产部署指南
- [Dockerfile](../Dockerfile) - Docker 部署

## 获取帮助

如果遇到问题：

1. **使用诊断工具**:
   ```bash
   python validate_config.py  # 配置验证
   python fix_config.py       # 配置修复建议
   ```

2. **查看详细日志**:
   ```bash
   export LOG_LEVEL=DEBUG
   python server.py --debug
   ```

3. **测试连接**:
   ```bash
   python server.py --test-connection
   ```

4. **查看文档**:
   - [问题排查指南](TROUBLESHOOTING.md)
   - [性能测试文档](PERFORMANCE_TESTING.md)

## 示例：完整的本地启动流程

```bash
# 1. 设置环境变量
export AFS_ACCESS_KEY="your_access_key"
export AFS_SECRET_KEY="your_secret_key"
export AFS_BASE_URL="https://afs.cn-sh-01.sensecoreapi.cn"
export AFS_VOLUME_ID="your_volume_id"
export AFS_ZONE="your_zone"
export SERVER_HOST="127.0.0.1"
export SERVER_PORT="8080"
export LOG_LEVEL="INFO"

# 2. 验证配置
python server.py --validate-config

# 3. 测试连接
python server.py --test-connection

# 4. 启动服务器
python server.py

# 5. 在另一个终端测试
curl http://localhost:8080/health/live
curl http://localhost:8080/metrics
```