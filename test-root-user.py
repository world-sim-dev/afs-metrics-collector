#!/usr/bin/env python3
"""
测试 root 用户配置脚本
验证容器是否以 root 用户运行
"""

import os
import sys
import pwd
import grp


def test_user_permissions():
    """测试用户权限"""
    print("🔍 用户权限测试")
    print("=" * 40)
    
    # 获取当前用户信息
    uid = os.getuid()
    gid = os.getgid()
    
    try:
        user_info = pwd.getpwuid(uid)
        group_info = grp.getgrgid(gid)
        
        print(f"当前用户ID: {uid}")
        print(f"当前用户名: {user_info.pw_name}")
        print(f"当前组ID: {gid}")
        print(f"当前组名: {group_info.gr_name}")
        print(f"用户主目录: {user_info.pw_dir}")
        print(f"用户Shell: {user_info.pw_shell}")
        
        # 检查是否为 root 用户
        if uid == 0:
            print("✅ 当前以 root 用户运行")
            return True
        else:
            print("❌ 当前不是 root 用户")
            return False
            
    except Exception as e:
        print(f"❌ 获取用户信息失败: {e}")
        return False


def test_file_permissions():
    """测试文件权限"""
    print("\n📁 文件权限测试")
    print("=" * 40)
    
    test_paths = [
        "/app",
        "/app/logs",
        "/app/config",
        "/tmp"
    ]
    
    success = True
    
    for path in test_paths:
        try:
            if os.path.exists(path):
                # 检查读写权限
                readable = os.access(path, os.R_OK)
                writable = os.access(path, os.W_OK)
                executable = os.access(path, os.X_OK)
                
                print(f"{path}:")
                print(f"  读权限: {'✅' if readable else '❌'}")
                print(f"  写权限: {'✅' if writable else '❌'}")
                print(f"  执行权限: {'✅' if executable else '❌'}")
                
                if not (readable and writable):
                    success = False
            else:
                print(f"{path}: 路径不存在")
                
        except Exception as e:
            print(f"{path}: 权限检查失败 - {e}")
            success = False
    
    return success


def test_write_operations():
    """测试写操作"""
    print("\n✏️  写操作测试")
    print("=" * 40)
    
    test_files = [
        "/app/logs/test.log",
        "/tmp/test.tmp"
    ]
    
    success = True
    
    for test_file in test_files:
        try:
            # 尝试创建和写入文件
            with open(test_file, 'w') as f:
                f.write("test content")
            
            # 尝试读取文件
            with open(test_file, 'r') as f:
                content = f.read()
            
            # 删除测试文件
            os.remove(test_file)
            
            print(f"✅ {test_file} 写入测试成功")
            
        except Exception as e:
            print(f"❌ {test_file} 写入测试失败: {e}")
            success = False
    
    return success


def test_environment():
    """测试环境变量"""
    print("\n🌍 环境变量测试")
    print("=" * 40)
    
    important_vars = [
        "PYTHONPATH",
        "PYTHONUNBUFFERED", 
        "PYTHONDONTWRITEBYTECODE",
        "PATH",
        "HOME"
    ]
    
    for var in important_vars:
        value = os.environ.get(var, "未设置")
        print(f"{var}: {value}")
    
    return True


def main():
    """主函数"""
    print("🔍 Root 用户配置测试")
    print("=" * 60)
    
    tests = [
        ("用户权限", test_user_permissions),
        ("文件权限", test_file_permissions),
        ("写操作", test_write_operations),
        ("环境变量", test_environment)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
    
    print(f"\n📊 测试结果: {passed}/{total} 测试通过")
    
    if passed == total:
        print("✅ 所有测试通过 - Root 用户配置正确")
        return True
    else:
        print("❌ 部分测试失败")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)