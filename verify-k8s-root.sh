#!/bin/bash

# Kubernetes Root 用户配置验证脚本
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

NAMESPACE="afs-metrics"
POD_SELECTOR="app=afs-metrics-collector"

echo -e "${BLUE}=== Kubernetes Root 用户配置验证 ===${NC}"
echo ""

# 检查 kubectl 是否可用
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}错误: kubectl 未安装或不可用${NC}"
    exit 1
fi

# 检查命名空间是否存在
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo -e "${RED}错误: 命名空间 $NAMESPACE 不存在${NC}"
    echo "请先部署应用: ./deploy-k8s.sh"
    exit 1
fi

# 获取 Pod 名称
POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l "$POD_SELECTOR" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo -e "${RED}错误: 未找到运行中的 Pod${NC}"
    echo "请检查部署状态: kubectl get pods -n $NAMESPACE"
    exit 1
fi

echo -e "${YELLOW}找到 Pod:${NC} $POD_NAME"
echo ""

# 检查 Pod 状态
POD_STATUS=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo -e "${RED}错误: Pod 状态不是 Running (当前: $POD_STATUS)${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Pod 状态正常${NC}"

# 验证用户 ID
echo ""
echo -e "${BLUE}验证用户配置...${NC}"

USER_ID=$(kubectl exec -n "$NAMESPACE" "$POD_NAME" -- id -u 2>/dev/null)
GROUP_ID=$(kubectl exec -n "$NAMESPACE" "$POD_NAME" -- id -g 2>/dev/null)
USER_NAME=$(kubectl exec -n "$NAMESPACE" "$POD_NAME" -- whoami 2>/dev/null)

echo "用户ID: $USER_ID"
echo "组ID: $GROUP_ID"
echo "用户名: $USER_NAME"

if [ "$USER_ID" = "0" ] && [ "$GROUP_ID" = "0" ] && [ "$USER_NAME" = "root" ]; then
    echo -e "${GREEN}✅ 用户配置正确 - 以 root 用户运行${NC}"
else
    echo -e "${RED}❌ 用户配置错误 - 未以 root 用户运行${NC}"
    exit 1
fi

# 验证文件权限
echo ""
echo -e "${BLUE}验证文件权限...${NC}"

# 检查关键目录的权限
DIRS="/app /app/logs /app/config"
for dir in $DIRS; do
    if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- test -d "$dir" 2>/dev/null; then
        if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- test -w "$dir" 2>/dev/null; then
            echo -e "✅ $dir - 可写"
        else
            echo -e "❌ $dir - 不可写"
        fi
    else
        echo -e "❌ $dir - 不存在"
    fi
done

# 测试写操作
echo ""
echo -e "${BLUE}测试写操作...${NC}"

TEST_FILE="/app/logs/test-$(date +%s).log"
if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- sh -c "echo 'test' > $TEST_FILE && rm $TEST_FILE" 2>/dev/null; then
    echo -e "${GREEN}✅ 写操作测试成功${NC}"
else
    echo -e "${RED}❌ 写操作测试失败${NC}"
fi

# 检查安全上下文配置
echo ""
echo -e "${BLUE}检查安全上下文配置...${NC}"

SECURITY_CONTEXT=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.securityContext}')
CONTAINER_SECURITY_CONTEXT=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].securityContext}')

echo "Pod 安全上下文: $SECURITY_CONTEXT"
echo "容器安全上下文: $CONTAINER_SECURITY_CONTEXT"

# 检查应用是否正常运行
echo ""
echo -e "${BLUE}检查应用状态...${NC}"

if kubectl exec -n "$NAMESPACE" "$POD_NAME" -- curl -f http://localhost:8080/metrics -o /dev/null -s 2>/dev/null; then
    echo -e "${GREEN}✅ 应用运行正常 - /metrics 端点可访问${NC}"
else
    echo -e "${RED}❌ 应用可能有问题 - /metrics 端点不可访问${NC}"
fi

# 显示资源使用情况
echo ""
echo -e "${BLUE}资源使用情况:${NC}"
kubectl top pod "$POD_NAME" -n "$NAMESPACE" 2>/dev/null || echo "无法获取资源使用情况 (需要 metrics-server)"

echo ""
echo -e "${GREEN}=== 验证完成 ===${NC}"
echo ""
echo -e "${YELLOW}有用的命令:${NC}"
echo "  查看日志: kubectl logs -n $NAMESPACE $POD_NAME -f"
echo "  进入容器: kubectl exec -n $NAMESPACE $POD_NAME -it -- bash"
echo "  端口转发: kubectl port-forward -n $NAMESPACE $POD_NAME 8080:8080"