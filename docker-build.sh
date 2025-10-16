#!/bin/bash

# AFS Metrics Collector Docker 构建脚本
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
IMAGE_NAME="afs-metrics-collector"
TAG="latest"
REGISTRY=""
PUSH=false
NO_CACHE=false

# 显示帮助信息
show_help() {
    echo "AFS Metrics Collector Docker 构建脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -n, --name NAME       镜像名称 (默认: $IMAGE_NAME)"
    echo "  -t, --tag TAG         镜像标签 (默认: $TAG)"
    echo "  -r, --registry REG    镜像仓库地址"
    echo "  -p, --push            构建后推送到仓库"
    echo "  --no-cache            不使用缓存构建"
    echo "  -h, --help            显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                    # 基本构建"
    echo "  $0 -t v1.0.0                        # 指定标签"
    echo "  $0 -r registry.example.com -p       # 构建并推送"
    echo "  $0 --no-cache                       # 无缓存构建"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
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

# 构建完整镜像名称
if [[ -n "$REGISTRY" ]]; then
    FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME:$TAG"
else
    FULL_IMAGE_NAME="$IMAGE_NAME:$TAG"
fi

echo -e "${BLUE}=== AFS Metrics Collector Docker 构建 ===${NC}"
echo -e "${YELLOW}镜像名称:${NC} $FULL_IMAGE_NAME"
echo -e "${YELLOW}构建时间:${NC} $(date)"
echo ""

# 检查 Docker 是否可用
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装或不可用${NC}"
    exit 1
fi

# 检查 Dockerfile 是否存在
if [[ ! -f "Dockerfile" ]]; then
    echo -e "${RED}错误: 当前目录下未找到 Dockerfile${NC}"
    exit 1
fi

# 构建 Docker 镜像
echo -e "${BLUE}开始构建 Docker 镜像...${NC}"

BUILD_ARGS=""
if [[ "$NO_CACHE" == true ]]; then
    BUILD_ARGS="--no-cache"
fi

if docker build $BUILD_ARGS -t "$FULL_IMAGE_NAME" .; then
    echo -e "${GREEN}✅ Docker 镜像构建成功${NC}"
else
    echo -e "${RED}❌ Docker 镜像构建失败${NC}"
    exit 1
fi

# 显示镜像信息
echo ""
echo -e "${BLUE}镜像信息:${NC}"
docker images "$FULL_IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# 推送镜像（如果需要）
if [[ "$PUSH" == true ]]; then
    if [[ -z "$REGISTRY" ]]; then
        echo -e "${YELLOW}警告: 未指定仓库地址，跳过推送${NC}"
    else
        echo ""
        echo -e "${BLUE}推送镜像到仓库...${NC}"
        if docker push "$FULL_IMAGE_NAME"; then
            echo -e "${GREEN}✅ 镜像推送成功${NC}"
        else
            echo -e "${RED}❌ 镜像推送失败${NC}"
            exit 1
        fi
    fi
fi

echo ""
echo -e "${GREEN}=== 构建完成 ===${NC}"
echo -e "${YELLOW}运行命令:${NC}"
echo ""
echo -e "${BLUE}方式1: 使用环境变量${NC}"
echo "  docker run -d --name afs-metrics -p 8080:8080 \\"
echo "    -e AFS_ACCESS_KEY=your_access_key \\"
echo "    -e AFS_SECRET_KEY=your_secret_key \\"
echo "    -e AFS_BASE_URL=https://afs.cn-sh-01.sensecoreapi.cn \\"
echo "    $FULL_IMAGE_NAME"
echo ""
echo -e "${BLUE}方式2: 挂载配置文件${NC}"
echo "  docker run -d --name afs-metrics -p 8080:8080 \\"
echo "    -v \$(pwd)/config.yaml:/app/config.yaml:ro \\"
echo "    $FULL_IMAGE_NAME"
echo ""
echo -e "${YELLOW}查看日志:${NC}"
echo "  docker logs -f afs-metrics"
echo ""
echo -e "${YELLOW}访问服务:${NC}"
echo "  curl http://localhost:8080/metrics"