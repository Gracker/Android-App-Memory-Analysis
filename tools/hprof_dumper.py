#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android App HPROF Memory Dump and Analysis Tool
# @Author: Android Memory Analysis Tool

import argparse
import os
import re
import sys
import time
from datetime import datetime

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.android_shell_utils import (
    list_processes_with_adb,
    resolve_pid_with_adb,
    run_adb_command,
    run_adb_shell,
)

class HprofDumper:
    def __init__(self, adb_path='adb'):
        self.adb = adb_path
        self.adb_available = self._check_adb()

    def _is_valid_package_name(self, package_name):
        """校验包名，避免命令注入和非法输入"""
        return bool(re.fullmatch(r"[A-Za-z0-9._:]+", package_name))

    def _list_processes(self):
        """获取进程列表，返回 (pid, process_name) 元组列表"""
        return [(pid, process_name) for pid, _, process_name in list_processes_with_adb(self.adb)]
        
    def _check_adb(self):
        """检查ADB是否可用"""
        _, return_code, error = run_adb_command(self.adb, ['version'], timeout=10)
        if return_code == 0:
            return True
        if "No such file" in error or "not found" in error:
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
            pid = resolve_pid_with_adb(self.adb, package_name)
            if pid is None:
                print(f"错误: 应用 {package_name} 未运行")
                return None

            process_name = None
            for process_pid, name in self._list_processes():
                if process_pid == pid:
                    process_name = name
                    break

            if process_name and process_name.startswith(f"{package_name}:"):
                print(f"找到应用子进程 {process_name} PID: {pid}")
            else:
                print(f"找到应用 {package_name} PID: {pid}")
            return pid
            
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
            if package_name:
                dump_target = package_name
            else:
                dump_target = str(pid)

            print(f"执行命令: {self.adb} shell am dumpheap {dump_target} {device_path}")
            _, dump_code, dump_error = run_adb_shell(
                self.adb,
                f'am dumpheap {dump_target} {device_path}',
                timeout=180,
            )

            if dump_code != 0:
                print(f"dump命令执行失败: {dump_error or '无详细错误信息'}")
                return None
            
            print("等待hprof文件生成...")
            time.sleep(3)
            
            _, check_code, _ = run_adb_shell(self.adb, f'ls -la {device_path}', timeout=30)
            if check_code != 0:
                print("hprof文件生成失败")
                return None
                
            print(f"hprof文件已生成: {device_path}")
            
            print(f"拉取文件到本地: {self.adb} pull {device_path} {local_path}")
            _, pull_code, pull_error = run_adb_command(
                self.adb,
                ['pull', device_path, local_path],
                timeout=180,
            )

            if pull_code != 0:
                print(f"拉取文件失败: {pull_error or '无详细错误信息'}")
                return None
            
            run_adb_shell(self.adb, f'rm {device_path}', timeout=30)
            
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
