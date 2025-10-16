#!/usr/bin/env python3
"""
配置验证脚本
用于验证 AFS Metrics Collector 的配置是否正确
"""

import sys
import os
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config, ConfigurationError
from src.logging_config import setup_logging, get_logger


def main():
    """主函数"""
    print("🔍 AFS Metrics Collector 配置验证")
    print("=" * 50)
    
    # 检查配置文件是否存在
    config_file = Path("config.yaml")
    env_file = Path(".env")
    
    if not config_file.exists() and not env_file.exists():
        print("❌ 错误: 未找到配置文件")
        print("请创建 config.yaml 或 .env 文件")
        print("\n💡 建议:")
        print("  cp config.yaml.example config.yaml")
        print("  # 然后编辑 config.yaml 设置你的凭据")
        return False
    
    try:
        # 加载配置
        print("📋 加载配置...")
        config = Config()
        
        # 设置基础日志
        logging_config = config.get_logging_config()
        setup_logging(logging_config)
        logger = get_logger(__name__)
        
        # 验证配置
        print("✅ 配置加载成功")
        config.validate()
        print("✅ 配置验证通过")
        
        # 显示配置摘要
        print("\n📊 配置摘要:")
        print("-" * 30)
        
        # AFS 配置
        afs_config = config.get_afs_config()
        print(f"🔑 AFS API URL: {afs_config.base_url}")
        print(f"🔑 Access Key: {afs_config.access_key[:8]}...")
        print(f"📁 监控卷数量: {len(afs_config.volumes)}")
        
        for i, volume in enumerate(afs_config.volumes, 1):
            print(f"   {i}. Volume: {volume.volume_id} (Zone: {volume.zone})")
        
        # 服务器配置
        server_config = config.get_server_config()
        print(f"🌐 服务器: {server_config.host}:{server_config.port}")
        
        # 收集配置
        collection_config = config.get_collection_config()
        print(f"⏱️  超时时间: {collection_config.timeout_seconds}s")
        print(f"🔄 最大重试: {collection_config.max_retries}")
        print(f"💾 缓存时间: {collection_config.cache_duration}s")
        
        # 日志配置
        logging_config = config.get_logging_config()
        print(f"📝 日志级别: {logging_config.level}")
        
        print("\n✅ 配置验证完成！")
        print("\n🚀 启动命令:")
        print("  python server.py")
        
        return True
        
    except ConfigurationError as e:
        print(f"❌ 配置错误: {e}")
        print("\n💡 请检查你的配置文件并修正错误")
        return False
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)