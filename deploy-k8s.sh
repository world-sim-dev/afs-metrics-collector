#!/bin/bash

# AFS Metrics Collector Kubernetes 部署脚本
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
NAMESPACE="afs-metrics"
DEPLOYMENT_FILE="k8s-deployment.yaml"
IMAGE_NAME="afs-metrics-collector:latest"
ACCESS_KEY=""
SECRET_KEY=""
VOLUME_ID=""
ZONE="cn-sh-01e"
BASE_URL="https://afs.cn-sh-01.sensecoreapi.cn"

# 显示帮助信息
show_help() {
    echo "AFS Metrics Collector Kubernetes 部署脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -n, --namespace NS     Kubernetes 命名空间 (默认: $NAMESPACE)"
    echo "  -f, --file FILE        部署文件 (默认: $DEPLOYMENT_FILE)"
    echo "  -i, --image IMAGE      Docker 镜像 (默认: $IMAGE_NAME)"
    echo "  -k, --access-key KEY   AFS Access Key (必需)"
    echo "  -s, --secret-key KEY   AFS Secret Key (必需)"
    echo "  -v, --volume-id ID     AFS Volume ID (必需)"
    echo "  -z, --zone ZONE        AFS Zone (默认: $ZONE)"
    echo "  -u, --base-url URL     AFS Base URL (默认: $BASE_URL)"
    echo "  --simple               使用简化部署文件"
    echo "  --delete               删除部署"
    echo "  --status               查看部署状态"
    echo "  --verify               验证 root 用户配置"
    echo "  -h, --help             显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 -k ACCESS_KEY -s SECRET_KEY -v VOLUME_ID"
    echo "  $0 --simple -k ACCESS_KEY -s SECRET_KEY -v VOLUME_ID"
    echo "  $0 --status"
    echo "  $0 --verify"
    echo "  $0 --delete"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -f|--file)
            DEPLOYMENT_FILE="$2"
            shift 2
            ;;
        -i|--image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -k|--access-key)
            ACCESS_KEY="$2"
            shift 2
            ;;
        -s|--secret-key)
            SECRET_KEY="$2"
            shift 2
            ;;
        -v|--volume-id)
            VOLUME_ID="$2"
            shift 2
            ;;
        -z|--zone)
            ZONE="$2"
            shift 2
            ;;
        -u|--base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --simple)
            DEPLOYMENT_FILE="k8s-simple.yaml"
            shift
            ;;
        --delete)
            echo -e "${YELLOW}删除 AFS Metrics Collector 部署...${NC}"
            kubectl delete -f "$DEPLOYMENT_FILE" --ignore-not-found=true
            echo -e "${GREEN}✅ 删除完成${NC}"
            exit 0
            ;;
        --status)
            echo -e "${BLUE}=== AFS Metrics Collector 部署状态 ===${NC}"
            echo ""
            echo -e "${YELLOW}命名空间:${NC}"
            kubectl get namespace "$NAMESPACE" 2>/dev/null || echo "命名空间不存在"
            echo ""
            echo -e "${YELLOW}部署状态:${NC}"
            kubectl get deployment -n "$NAMESPACE" 2>/dev/null || echo "无部署"
            echo ""
            echo -e "${YELLOW}Pod 状态:${NC}"
            kubectl get pods -n "$NAMESPACE" 2>/dev/null || echo "无 Pod"
            echo ""
            echo -e "${YELLOW}服务状态:${NC}"
            kubectl get service -n "$NAMESPACE" 2>/dev/null || echo "无服务"
            exit 0
            ;;
        --verify)
            echo -e "${BLUE}验证 root 用户配置...${NC}"
            ./verify-k8s-root.sh
            exit $?
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}错误: 未知选项 $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

echo -e "${BLUE}=== AFS Metrics Collector Kubernetes 部署 ===${NC}"
echo -e "${YELLOW}命名空间:${NC} $NAMESPACE"
echo -e "${YELLOW}部署文件:${NC} $DEPLOYMENT_FILE"
echo -e "${YELLOW}镜像名称:${NC} $IMAGE_NAME"
echo ""

# 检查 kubectl 是否可用
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}错误: kubectl 未安装或不可用${NC}"
    exit 1
fi

# 检查部署文件是否存在
if [[ ! -f "$DEPLOYMENT_FILE" ]]; then
    echo -e "${RED}错误: 部署文件 $DEPLOYMENT_FILE 不存在${NC}"
    exit 1
fi

# 检查必需参数
if [[ -z "$ACCESS_KEY" || -z "$SECRET_KEY" || -z "$VOLUME_ID" ]]; then
    echo -e "${RED}错误: 缺少必需参数${NC}"
    echo "请提供 AFS Access Key (-k), Secret Key (-s) 和 Volume ID (-v)"
    echo ""
    show_help
    exit 1
fi

# 创建临时部署文件
TEMP_FILE=$(mktemp)
cp "$DEPLOYMENT_FILE" "$TEMP_FILE"

# 替换配置值
sed -i.bak "s/YOUR_ACCESS_KEY_HERE/$ACCESS_KEY/g" "$TEMP_FILE"
sed -i.bak "s/YOUR_SECRET_KEY_HERE/$SECRET_KEY/g" "$TEMP_FILE"
sed -i.bak "s/YOUR_VOLUME_ID_HERE/$VOLUME_ID/g" "$TEMP_FILE"
sed -i.bak "s|afs-metrics-collector:latest|$IMAGE_NAME|g" "$TEMP_FILE"

# 如果使用简化部署，还需要替换 JSON 中的值
if [[ "$DEPLOYMENT_FILE" == "k8s-simple.yaml" ]]; then
    sed -i.bak "s/cn-sh-01e/$ZONE/g" "$TEMP_FILE"
fi

echo -e "${BLUE}开始部署...${NC}"

# 应用部署
if kubectl apply -f "$TEMP_FILE"; then
    echo -e "${GREEN}✅ 部署成功${NC}"
    
    # 等待部署就绪
    echo ""
    echo -e "${BLUE}等待 Pod 启动...${NC}"
    kubectl wait --for=condition=ready pod -l app=afs-metrics-collector -n "$NAMESPACE" --timeout=300s
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Pod 启动成功${NC}"
        
        # 显示部署信息
        echo ""
        echo -e "${BLUE}部署信息:${NC}"
        echo "-------------------"
        kubectl get deployment,service,pod -n "$NAMESPACE"
        
        echo ""
        echo -e "${YELLOW}访问服务:${NC}"
        echo "  kubectl port-forward -n $NAMESPACE service/afs-metrics-service 8080:8080"
        echo "  然后访问: http://localhost:8080/metrics"
        
        echo ""
        echo -e "${YELLOW}查看日志:${NC}"
        echo "  kubectl logs -n $NAMESPACE -l app=afs-metrics-collector -f"
        
    else
        echo -e "${RED}❌ Pod 启动超时${NC}"
        echo "请检查 Pod 状态: kubectl get pods -n $NAMESPACE"
    fi
    
else
    echo -e "${RED}❌ 部署失败${NC}"
    exit 1
fi

# 清理临时文件
rm -f "$TEMP_FILE" "$TEMP_FILE.bak"

echo ""
echo -e "${GREEN}=== 部署完成 ===${NC}"