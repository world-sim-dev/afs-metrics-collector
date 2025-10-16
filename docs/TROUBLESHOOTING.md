# 问题排查指南

本文档提供了 AFS Prometheus 指标收集器常见问题的排查和解决方案。

## 快速诊断工具

### 1. 配置验证

```bash
# 验证当前配置
python validate_config.py

# 自动修复常见配置问题
python fix_config.py
```

### 2. 连接测试

```bash
# 测试配置和连接
python server.py --validate-config
python server.py --test-connection
```

## 常见问题

### 1. Volume ID 配置错误

**症状**: 
```
GET https://afs.cn-sh-01.sensecoreapi.cn/storage/afs/data/v1/volume/80433778-429e-11ef-bc97-4eca24dcdba9&zone=cn-sh-01e/dir_quotas - 404
```

**原因**: `AFS_VOLUME_ID` 环境变量包含了额外的参数（如 `&zone=xxx`）

**解决方案**:
```bash
# 错误的设置
export AFS_VOLUME_ID="80433778-429e-11ef-bc97-4eca24dcdba9&zone=cn-sh-01e"

# 正确的设置
export AFS_VOLUME_ID="80433778-429e-11ef-bc97-4eca24dcdba9"
export AFS_ZONE="cn-sh-01e"
```

**自动修复**:
```bash
python fix_config.py
```

### 2. 认证失败 (401/403)

**症状**:
```
2025-10-15 19:08:30 - src.afs_client - ERROR - Authentication failed - invalid credentials or signature
```

**可能原因**:
- Access Key 或 Secret Key 错误
- 时间同步问题
- 签名算法问题

**排查步骤**:
1. 验证凭据格式:
   ```bash
   echo "Access Key: ${AFS_ACCESS_KEY:0:8}..."
   echo "Secret Key: ${AFS_SECRET_KEY:0:8}..."
   ```

2. 检查时间同步:
   ```bash
   date
   # 确保系统时间正确
   ```

3. 测试连接:
   ```bash
   python server.py --test-connection
   ```

### 3. 网络连接问题

**症状**:
```
Connection error: HTTPSConnectionPool(host='afs.cn-sh-01.sensecoreapi.cn', port=443)
```

**排查步骤**:
1. 测试网络连通性:
   ```bash
   curl -I https://afs.cn-sh-01.sensecoreapi.cn
   ping afs.cn-sh-01.sensecoreapi.cn
   ```

2. 检查防火墙和代理设置

3. 验证 DNS 解析:
   ```bash
   nslookup afs.cn-sh-01.sensecoreapi.cn
   ```

### 4. 端口被占用

**症状**:
```
Address already in use
```

**解决方案**:
1. 查看端口占用:
   ```bash
   lsof -i :8080
   netstat -tulpn | grep 8080
   ```

2. 使用不同端口:
   ```bash
   export SERVER_PORT=8081
   python server.py
   ```

3. 停止占用端口的进程:
   ```bash
   sudo kill -9 <PID>
   ```

### 5. 配置文件问题

**症状**:
```
Configuration error: Invalid YAML in configuration file
```

**排查步骤**:
1. 验证 YAML 语法:
   ```bash
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   ```

2. 检查文件权限:
   ```bash
   ls -la config.yaml
   ```

3. 使用示例配置:
   ```bash
   cp config.yaml.example config.yaml
   # 编辑 config.yaml
   ```

### 6. 权限问题

**症状**:
```
Permission denied
```

**解决方案**:
1. 使用非特权端口 (>1024):
   ```bash
   export SERVER_PORT=8080
   ```

2. 检查文件权限:
   ```bash
   chmod +r config.yaml
   chmod +x server.py
   ```

### 7. 内存不足

**症状**:
- 服务器响应缓慢
- 进程被系统终止

**排查步骤**:
1. 检查内存使用:
   ```bash
   free -h
   ps aux | grep python
   ```

2. 监控内存使用:
   ```bash
   python tests/run_performance_tests.py --benchmark
   ```

3. 调整配置:
   ```bash
   export CACHE_DURATION=60  # 增加缓存时间
   export COLLECTION_TIMEOUT=20  # 减少超时时间
   ```

## 日志分析

### 启用调试日志

```bash
export LOG_LEVEL=DEBUG
python server.py --debug
```

### 常见日志模式

1. **成功的 API 请求**:
   ```
   API request: GET https://afs.cn-sh-01.sensecoreapi.cn/storage/afs/data/v1/volume/xxx/dir_quotas - 200 (0.150s)
   ```

2. **认证错误**:
   ```
   API request: GET https://afs.cn-sh-01.sensecoreapi.cn/storage/afs/data/v1/volume/xxx/dir_quotas - 401 (0.100s)
   Authentication failed - invalid credentials or signature
   ```

3. **网络错误**:
   ```
   Connection error: HTTPSConnectionPool(host='afs.cn-sh-01.sensecoreapi.cn', port=443)
   ```

4. **配置错误**:
   ```
   Configuration error: AFS configuration is required
   ```

## 性能问题

### 响应时间过长

1. 检查网络延迟:
   ```bash
   ping afs.cn-sh-01.sensecoreapi.cn
   ```

2. 调整超时设置:
   ```bash
   export COLLECTION_TIMEOUT=30
   export REQUEST_TIMEOUT=45
   ```

3. 启用缓存:
   ```bash
   export CACHE_DURATION=60
   ```

### 高内存使用

1. 运行性能测试:
   ```bash
   python tests/run_performance_tests.py
   ```

2. 监控内存使用:
   ```bash
   python -c "
   import psutil
   import time
   while True:
       mem = psutil.virtual_memory()
       print(f'Memory: {mem.percent}% used, {mem.available/1024/1024/1024:.1f}GB available')
       time.sleep(5)
   "
   ```

## 环境特定问题

### Docker 环境

1. 检查容器日志:
   ```bash
   docker logs afs-metrics-collector
   ```

2. 进入容器调试:
   ```bash
   docker exec -it afs-metrics-collector /bin/bash
   ```

### Docker 容器

1. 检查容器状态:
   ```bash
   docker ps -a | grep afs-metrics
   ```

2. 查看容器日志:
   ```bash
   docker logs -f afs-metrics
   ```

## 获取帮助

### 收集诊断信息

运行以下命令收集诊断信息:

```bash
echo "=== 系统信息 ===" > diagnostic.txt
uname -a >> diagnostic.txt
python --version >> diagnostic.txt

echo -e "\n=== 配置验证 ===" >> diagnostic.txt
python validate_config.py >> diagnostic.txt 2>&1

echo -e "\n=== 网络测试 ===" >> diagnostic.txt
curl -I https://afs.cn-sh-01.sensecoreapi.cn >> diagnostic.txt 2>&1

echo -e "\n=== 端口检查 ===" >> diagnostic.txt
netstat -tulpn | grep 8080 >> diagnostic.txt 2>&1

echo -e "\n=== 内存信息 ===" >> diagnostic.txt
free -h >> diagnostic.txt

echo -e "\n=== 磁盘空间 ===" >> diagnostic.txt
df -h >> diagnostic.txt

echo "诊断信息已保存到 diagnostic.txt"
```

### 联系支持

提供以下信息:
1. 错误日志 (启用 DEBUG 级别)
2. 配置验证结果 (`python validate_config.py`)
3. 系统信息 (操作系统、Python 版本)
4. 网络环境信息
5. 重现步骤

## 预防措施

### 定期检查

1. **配置验证** (每周):
   ```bash
   python validate_config.py
   ```

2. **性能测试** (每月):
   ```bash
   python tests/run_performance_tests.py --benchmark
   ```

3. **连接测试** (每日):
   ```bash
   python server.py --test-connection
   ```

### 监控设置

1. **健康检查**:
   ```bash
   curl http://localhost:8080/health/ready
   ```

2. **指标监控**:
   ```bash
   curl http://localhost:8080/metrics | grep afs_collection_success
   ```

3. **日志监控**:
   ```bash
   tail -f /var/log/afs-collector/afs-metrics.log | grep ERROR
   ```

### 备份和恢复

1. **备份配置**:
   ```bash
   cp config.yaml config.yaml.backup
   ```

2. **环境变量备份**:
   ```bash
   env | grep AFS_ > afs_env.backup
   ```

3. **恢复配置**:
   ```bash
   source afs_env.backup
   ```