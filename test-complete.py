#!/usr/bin/env python3
"""
完整功能测试脚本
验证配置、日志和基本功能是否正常工作
"""

import os
import sys
import json
import tempfile

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config, ConfigurationError
from src.logging_config import setup_logging, get_logger


def test_json_volumes_config():
    """测试 JSON 格式的 AFS_VOLUMES 配置"""
    print("\n🧪 测试 JSON 格式 AFS_VOLUMES 配置")
    print("=" * 50)
    
    # 设置测试环境变量
    test_volumes = [
        {"volume_id": "vol-123", "zone": "cn-sh-01e"},
        {"volume_id": "vol-456", "zone": "cn-sh-01f"}
    ]
    
    os.environ.update({
        'AFS_ACCESS_KEY': 'test_access_key',
        'AFS_SECRET_KEY': 'test_secret_key',
        'AFS_VOLUMES': json.dumps(test_volumes),
        'LOG_FORMAT': 'json'
    })
    
    try:
        config = Config()
        afs_config = config.get_afs_config()
        
        print(f"✅ 成功解析 {len(afs_config.volumes)} 个卷:")
        for i, volume in enumerate(afs_config.volumes, 1):
            print(f"   {i}. {volume.volume_id} (Zone: {volume.zone})")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_single_volume_config():
    """测试单卷格式配置（向后兼容）"""
    print("\n🧪 测试单卷格式配置")
    print("=" * 50)
    
    # 清除 AFS_VOLUMES，使用单卷格式
    if 'AFS_VOLUMES' in os.environ:
        del os.environ['AFS_VOLUMES']
    
    os.environ.update({
        'AFS_ACCESS_KEY': 'test_access_key',
        'AFS_SECRET_KEY': 'test_secret_key',
        'AFS_VOLUME_ID': 'single-vol-123',
        'AFS_ZONE': 'cn-sh-01e'
    })
    
    try:
        config = Config()
        afs_config = config.get_afs_config()
        
        print(f"✅ 成功解析单卷配置:")
        print(f"   Volume: {afs_config.volumes[0].volume_id} (Zone: {afs_config.volumes[0].zone})")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_json_logging():
    """测试 JSON 日志格式"""
    print("\n🧪 测试 JSON 日志格式")
    print("=" * 50)
    
    os.environ['LOG_FORMAT'] = 'json'
    
    try:
        config = Config()
        setup_logging(config.get_logging_config())
        logger = get_logger('test')
        
        print("JSON 日志输出示例:")
        logger.info("这是一条信息日志")
        logger.set_context(volume_id="test-vol", operation="test")
        logger.warning("这是带上下文的警告日志")
        logger.clear_context()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_invalid_volumes_config():
    """测试无效的 AFS_VOLUMES 配置"""
    print("\n🧪 测试无效 AFS_VOLUMES 配置处理")
    print("=" * 50)
    
    # 设置必需的环境变量
    os.environ.update({
        'AFS_ACCESS_KEY': 'test_access_key',
        'AFS_SECRET_KEY': 'test_secret_key',
        'AFS_VOLUMES': '{"invalid": "json"'  # 缺少闭合括号
    })
    
    try:
        config = Config()
        print("❌ 应该抛出配置错误")
        return False
        
    except ConfigurationError as e:
        print(f"✅ 正确捕获配置错误: {e}")
        return True
        
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        return False


def test_missing_volumes_config():
    """测试缺少卷配置的情况"""
    print("\n🧪 测试缺少卷配置")
    print("=" * 50)
    
    # 清除所有卷相关配置
    for key in ['AFS_VOLUMES', 'AFS_VOLUME_ID', 'AFS_ZONE']:
        if key in os.environ:
            del os.environ[key]
    
    os.environ.update({
        'AFS_ACCESS_KEY': 'test_access_key',
        'AFS_SECRET_KEY': 'test_secret_key'
    })
    
    try:
        config = Config()
        config.validate()
        print("❌ 应该抛出验证错误")
        return False
        
    except ConfigurationError as e:
        print(f"✅ 正确捕获验证错误: {e}")
        return True
        
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        return False


def cleanup_env():
    """清理测试环境变量"""
    test_vars = [
        'AFS_ACCESS_KEY', 'AFS_SECRET_KEY', 'AFS_VOLUMES',
        'AFS_VOLUME_ID', 'AFS_ZONE', 'LOG_FORMAT'
    ]
    
    for var in test_vars:
        if var in os.environ:
            del os.environ[var]


def main():
    """主函数"""
    print("🔍 AFS Metrics Collector 完整功能测试")
    print("=" * 60)
    
    # 保存原始环境变量
    original_env = {}
    test_vars = [
        'AFS_ACCESS_KEY', 'AFS_SECRET_KEY', 'AFS_VOLUMES',
        'AFS_VOLUME_ID', 'AFS_ZONE', 'LOG_FORMAT'
    ]
    
    for var in test_vars:
        if var in os.environ:
            original_env[var] = os.environ[var]
    
    try:
        # 运行测试
        tests = [
            test_json_volumes_config,
            test_single_volume_config,
            test_json_logging,
            test_invalid_volumes_config,
            test_missing_volumes_config
        ]
        
        passed = 0
        for test in tests:
            cleanup_env()  # 清理环境变量
            if test():
                passed += 1
        
        print(f"\n📊 测试结果: {passed}/{len(tests)} 测试通过")
        
        if passed == len(tests):
            print("✅ 所有测试通过")
            return True
        else:
            print("❌ 部分测试失败")
            return False
            
    finally:
        # 恢复原始环境变量
        cleanup_env()
        for var, value in original_env.items():
            os.environ[var] = value


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)