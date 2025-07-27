#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android App HPROF Memory Dump and Analysis Tool
# @Author: Android Memory Analysis Tool

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

class HprofDumper:
    def __init__(self):
        self.adb_available = self._check_adb()
        
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
            
        try:
            # 首先检查应用是否正在运行
            cmd = f'adb shell "ps | grep {package_name}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0 or not result.stdout.strip():
                print(f"错误: 应用 {package_name} 未运行")
                return None
                
            # 解析PID
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if package_name in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            print(f"找到应用 {package_name} PID: {pid}")
                            return pid
                        except ValueError:
                            continue
            
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
                dump_cmd = f'adb shell "am dumpheap {package_name} {device_path}"'
            else:
                dump_cmd = f'adb shell "am dumpheap {pid} {device_path}"'
                
            print(f"执行命令: {dump_cmd}")
            result = subprocess.run(dump_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"dump命令执行失败: {result.stderr}")
                return None
            
            # 等待文件生成
            print("等待hprof文件生成...")
            time.sleep(3)
            
            # 检查文件是否存在
            check_cmd = f'adb shell "ls -la {device_path}"'
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if check_result.returncode != 0:
                print("hprof文件生成失败")
                return None
                
            print(f"hprof文件已生成: {device_path}")
            
            # 拉取文件到本地
            pull_cmd = f'adb pull {device_path} {local_path}'
            print(f"拉取文件到本地: {pull_cmd}")
            pull_result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            if pull_result.returncode != 0:
                print(f"拉取文件失败: {pull_result.stderr}")
                return None
            
            # 清理设备上的临时文件
            cleanup_cmd = f'adb shell "rm {device_path}"'
            subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
            
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
            # 获取正在运行的应用进程
            cmd = 'adb shell "ps | grep -v \'\\[.*\\]\'"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print("获取进程列表失败")
                return
                
            print("正在运行的应用进程:")
            print("PID\t\t进程名")
            print("-" * 50)
            
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # 跳过标题行
                parts = line.split()
                if len(parts) >= 9:
                    pid = parts[1]
                    process_name = parts[8]
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