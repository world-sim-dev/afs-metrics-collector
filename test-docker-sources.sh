#!/bin/bash

# 测试 Docker 镜像中的 APT 源配置
echo "🔍 测试 Docker 镜像中的 APT 源配置"
echo "=================================="

# 构建测试镜像
echo "📦 构建测试镜像..."
docker build -t afs-test-sources -f - . << 'EOF'
FROM sandai-registry-vpc.cn-beijing.cr.aliyuncs.com/mirrors/python:3.11-slim

# 配置 apt 使用阿里云镜像源
RUN rm -rf /etc/apt/sources.list.d/* && \
    rm -f /etc/apt/sources.list && \
    echo "# 阿里云 Debian 镜像源" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

# 测试命令
CMD ["cat", "/etc/apt/sources.list"]
EOF

if [ $? -eq 0 ]; then
    echo "✅ 测试镜像构建成功"
    
    echo ""
    echo "📋 APT 源配置内容:"
    echo "-------------------"
    docker run --rm afs-test-sources
    
    echo ""
    echo "🧹 清理测试镜像..."
    docker rmi afs-test-sources >/dev/null 2>&1
    
    echo "✅ 测试完成"
else
    echo "❌ 测试镜像构建失败"
    exit 1
fi