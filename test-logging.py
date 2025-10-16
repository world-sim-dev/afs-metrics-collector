#!/usr/bin/env python3
"""
测试日志配置脚本
验证不同日志格式是否正常工作
"""

import os
import sys
import tempfile

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.logging_config import setup_logging, get_logger


def test_log_format(format_name, format_value):
    """测试特定的日志格式"""
    print(f"\n🧪 测试日志格式: {format_name}")
    print("=" * 50)
    
    # 设置环境变量
    os.environ['LOG_FORMAT'] = format_value
    os.environ['LOG_LEVEL'] = 'INFO'
    
    try:
        # 创建配置
        config = Config()
        
        # 设置日志
        logging_config = config.get_logging_config()
        setup_logging(logging_config)
        
        # 获取日志器
        logger = get_logger(__name__)
        
        # 测试不同级别的日志
        logger.info("这是一条信息日志")
        logger.warning("这是一条警告日志")
        logger.error("这是一条错误日志")
        
        # 测试带上下文的日志
        logger.set_context(volume_id="test-volume", zone="test-zone")
        logger.info("这是一条带上下文的日志")
        logger.clear_context()
        
        print(f"✅ {format_name} 格式测试成功")
        
    except Exception as e:
        print(f"❌ {format_name} 格式测试失败: {e}")
        return False
    
    return True


def main():
    """主函数"""
    print("🔍 AFS Metrics Collector 日志格式测试")
    print("=" * 60)
    
    # 保存原始环境变量
    original_format = os.environ.get('LOG_FORMAT')
    original_level = os.environ.get('LOG_LEVEL')
    
    try:
        # 测试不同的日志格式
        formats = [
            ("标准格式", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            ("JSON 格式", "json"),
            ("简单格式", "simple"),
            ("详细格式", "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
        ]
        
        success_count = 0
        for format_name, format_value in formats:
            if test_log_format(format_name, format_value):
                success_count += 1
        
        print(f"\n📊 测试结果: {success_count}/{len(formats)} 格式测试成功")
        
        if success_count == len(formats):
            print("✅ 所有日志格式测试通过")
            return True
        else:
            print("❌ 部分日志格式测试失败")
            return False
            
    finally:
        # 恢复原始环境变量
        if original_format is not None:
            os.environ['LOG_FORMAT'] = original_format
        elif 'LOG_FORMAT' in os.environ:
            del os.environ['LOG_FORMAT']
            
        if original_level is not None:
            os.environ['LOG_LEVEL'] = original_level
        elif 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)