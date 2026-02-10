#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android App HPROF Memory Dump and Analysis Tool
# @Author: Android Memory Analysis Tool

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

class HprofDumper:
    def __init__(self):
        self.adb_available = self._check_adb()

    def _is_valid_package_name(self, package_name):
        """校验包名，避免命令注入和非法输入"""
        return bool(re.fullmatch(r"[A-Za-z0-9._:]+", package_name))

    def _list_processes(self):
        """获取进程列表，返回 (pid, process_name) 元组列表"""
        result = subprocess.run(['adb', 'shell', 'ps'], capture_output=True, text=True)
        if result.returncode != 0:
            return []

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return []

        header = lines[0].split()
        has_header = "PID" in header
        start_index = 1 if has_header else 0
        pid_index = header.index("PID") if has_header else 1
        name_index = header.index("NAME") if has_header and "NAME" in header else -1

        processes = []
        for line in lines[start_index:]:
            parts = line.split()
            if len(parts) <= pid_index:
                continue
            pid_token = parts[pid_index]
            if not pid_token.isdigit():
                continue

            process_name = parts[name_index] if name_index >= 0 and len(parts) > name_index else parts[-1]
            processes.append((int(pid_token), process_name))
        return processes
        
    def _check_adb(self):
        """检查ADB是否可用"""
        try:
            result = subprocess.run(['adb', 'version'], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            print("错误: ADB未找到，请确保Android SDK已安装并添加到PATH")
            return False
    
    def _get_package_pid(self, package_name):
        """根据包名获取进程PID"""
        if not self.adb_available:
            return None
        if not self._is_valid_package_name(package_name):
            print(f"错误: 非法包名: {package_name}")
            return None
            
        try:
            processes = self._list_processes()
            if not processes:
                print(f"错误: 应用 {package_name} 未运行")
                return None

            # 优先精确匹配主进程，再匹配子进程
            exact_match = [(pid, name) for pid, name in processes if name == package_name]
            if exact_match:
                pid = exact_match[0][0]
                print(f"找到应用 {package_name} PID: {pid}")
                return pid

            child_match = [(pid, name) for pid, name in processes if name.startswith(f"{package_name}:")]
            if child_match:
                pid = child_match[0][0]
                print(f"找到应用子进程 {child_match[0][1]} PID: {pid}")
                return pid
            
            print(f"错误: 无法解析 {package_name} 的PID")
            return None
            
        except Exception as e:
            print(f"获取PID时出错: {e}")
            return None
    
    def dump_hprof_by_package(self, package_name, output_dir="./"):
        """根据包名dump hprof文件"""
        pid = self._get_package_pid(package_name)
        if not pid:
            return None
        return self.dump_hprof_by_pid(pid, output_dir, package_name)
    
    def dump_hprof_by_pid(self, pid, output_dir="./", package_name=None):
        """根据PID dump hprof文件"""
        if not self.adb_available:
            print("错误: ADB不可用")
            return None
        os.makedirs(output_dir, exist_ok=True)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if package_name:
            hprof_filename = f"{package_name}_{pid}_{timestamp}.hprof"
        else:
            hprof_filename = f"pid_{pid}_{timestamp}.hprof"
        
        device_path = f"/data/local/tmp/{hprof_filename}"
        local_path = os.path.join(output_dir, hprof_filename)
        
        print(f"开始dump进程 {pid} 的内存文件...")
        
        try:
            # 使用am dumpheap命令dump hprof
            if package_name:
                dump_cmd = ['adb', 'shell', 'am', 'dumpheap', package_name, device_path]
            else:
                dump_cmd = ['adb', 'shell', 'am', 'dumpheap', str(pid), device_path]
                
            print(f"执行命令: {' '.join(dump_cmd)}")
            result = subprocess.run(dump_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"dump命令执行失败: {result.stderr}")
                return None
            
            # 等待文件生成
            print("等待hprof文件生成...")
            time.sleep(3)
            
            # 检查文件是否存在
            check_cmd = ['adb', 'shell', 'ls', '-la', device_path]
            check_result = subprocess.run(check_cmd, capture_output=True, text=True)
            
            if check_result.returncode != 0:
                print("hprof文件生成失败")
                return None
                
            print(f"hprof文件已生成: {device_path}")
            
            # 拉取文件到本地
            pull_cmd = ['adb', 'pull', device_path, local_path]
            print(f"拉取文件到本地: {' '.join(pull_cmd)}")
            pull_result = subprocess.run(pull_cmd, capture_output=True, text=True)
            
            if pull_result.returncode != 0:
                print(f"拉取文件失败: {pull_result.stderr}")
                return None
            
            # 清理设备上的临时文件
            cleanup_cmd = ['adb', 'shell', 'rm', device_path]
            subprocess.run(cleanup_cmd, capture_output=True, text=True)
            
            print(f"hprof文件已保存到: {local_path}")
            return local_path
            
        except Exception as e:
            print(f"dump过程中出错: {e}")
            return None
    
    def list_running_apps(self):
        """列出正在运行的应用进程"""
        if not self.adb_available:
            print("错误: ADB不可用")
            return
            
        try:
            processes = self._list_processes()
            if not processes:
                print("获取进程列表失败")
                return
                
            print("正在运行的应用进程:")
            print("PID\t\t进程名")
            print("-" * 50)
            
            for pid, process_name in processes:
                # 过滤系统进程，只显示应用进程
                if '.' in process_name and not process_name.startswith('/'):
                    print(f"{pid}\t\t{process_name}")
                        
        except Exception as e:
            print(f"列出进程时出错: {e}")

def main():
    parser = argparse.ArgumentParser(description="Android App HPROF内存dump工具")
    parser.add_argument('-p', '--pid', help="目标进程PID")
    parser.add_argument('-pkg', '--package', help="目标应用包名")
    parser.add_argument('-o', '--output', help="输出目录", default="./")
    parser.add_argument('-l', '--list', action='store_true', help="列出正在运行的应用")
    
    args = parser.parse_args()
    
    dumper = HprofDumper()
    
    if args.list:
        dumper.list_running_apps()
        return
    
    if not args.pid and not args.package:
        print("请提供PID (-p) 或包名 (-pkg)")
        print("使用 -l 选项查看正在运行的应用")
        return
    
    if args.package:
        hprof_file = dumper.dump_hprof_by_package(args.package, args.output)
    else:
        pid = int(args.pid)
        hprof_file = dumper.dump_hprof_by_pid(pid, args.output)
    
    if hprof_file:
        print(f"\nhprof文件dump完成: {hprof_file}")
        print("现在可以使用hprof_parser.py分析该文件")
    else:
        print("hprof文件dump失败")

if __name__ == "__main__":
    main()
