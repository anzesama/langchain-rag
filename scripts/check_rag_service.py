#!/usr/bin/env python3
"""
RAG 服务健康检查和启动脚本
在搜索知识库前自动检查服务状态，如果未运行则启动
用法: python check_rag_service.py
"""

import sys
import os
import socket
import subprocess
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_rag_service():
    """启动 RAG 服务"""
    server_script = PROJECT_ROOT / "rag_server.py"
    
    if not server_script.exists():
        print(f"[FAIL] 找不到服务器脚本: {server_script}")
        return False
    
    # 设置环境变量
    env = os.environ.copy()
    env['OMP_NUM_THREADS'] = '1'
    env['TOKENIZERS_PARALLELISM'] = 'false'
    
    print("[INFO] 正在启动 RAG 服务...")
    try:
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"[OK] 服务已启动 (PID: {process.pid})")
        return True
    except Exception as e:
        print(f"[FAIL] 启动失败: {e}")
        return False

def check_service(port: int = 8765, timeout: int = 10) -> bool:
    """检查 RAG 服务是否正常运行"""
    # 检查端口
    if not is_port_in_use(port):
        print(f"[WARN] 端口 {port} 未监听，服务未运行")
        return False
    
    # 尝试连接
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(('localhost', port))
        print(f"[OK] RAG 服务正常运行 (端口 {port})")
        return True
    except Exception as e:
        print(f"[WARN] 端口 {port} 监听但无法连接: {e}")
        return False

def main():
    print("=" * 60)
    print("RAG 服务健康检查")
    print("=" * 60)
    
    if check_service():
        print("\n[OK] 服务正常，可以继续搜索知识库")
        return 0
    else:
        print("\n[INFO] 服务未运行，尝试启动...")
        if start_rag_service():
            # 等待服务启动
            import time
            print("[INFO] 等待服务启动...")
            for i in range(timeout):
                time.sleep(1)
                if check_service():
                    print(f"\n[OK] 服务已启动 ({i+1}秒)")
                    return 0
            
            print(f"\n[FAIL] 服务启动超时 ({timeout}秒)")
            return 1
        else:
            print("\n[FAIL] 服务启动失败")
            return 1

if __name__ == '__main__':
    sys.exit(main())
