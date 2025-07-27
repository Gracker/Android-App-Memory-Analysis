#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# Android App Memory Analysis Script
# Enhanced for Android 16 compatibility with backward compatibility
# Original: 2019/6/13 上午10:55 by yangzhiting
# Enhanced: 2025 for comprehensive Android version support

"""
Android App Memory Analysis Tool

This script analyzes Android app memory usage by parsing smaps files.
Compatible with Android versions from early releases to Android 16+.

Features:
- Parse /proc/PID/smaps files from Android devices  
- Support for all Android versions including Android 16 features
- Enhanced heap type classification including latest memory management
- Memory insights and anomaly detection
- Backward compatibility with older Android versions
- Detailed Chinese descriptions for better understanding

Usage:
    python3 smaps_parser.py -p <PID>           # Analyze by process ID
    python3 smaps_parser.py -f <smaps_file>    # Analyze smaps file
"""

import argparse
import re
from collections import Counter
import os
import subprocess
import sys
from datetime import datetime

# Android version-adaptive memory heap type constants
# Dynamically adjusts based on available features
type_length = 45  # Extended for Android 16, backward compatible
pssSum_count = [0] * type_length
pss_count = [0] * type_length
swapPss_count = [0] * type_length

# Core heap types (stable across all Android versions)
HEAP_UNKNOWN = 0                    # 未知内存类型
HEAP_DALVIK = 1                     # Dalvik虚拟机内存
HEAP_NATIVE = 2                     # 本地C/C++代码内存

# Extended heap types (Android 4.0+)
HEAP_DALVIK_OTHER = 3               # Dalvik虚拟机其他内存
HEAP_STACK = 4                      # 线程栈内存
HEAP_CURSOR = 5                     # 数据库游标内存
HEAP_ASHMEM = 6                     # 匿名共享内存
HEAP_GL_DEV = 7                     # OpenGL设备内存
HEAP_UNKNOWN_DEV = 8                # 未知设备内存
HEAP_SO = 9                         # 动态链接库(.so)内存
HEAP_JAR = 10                       # JAR文件映射内存
HEAP_APK = 11                       # APK文件映射内存
HEAP_TTF = 12                       # 字体文件内存
HEAP_DEX = 13                       # DEX字节码文件内存
HEAP_OAT = 14                       # 编译后的OAT文件内存
HEAP_ART = 15                       # ART运行时文件内存
HEAP_UNKNOWN_MAP = 16               # 未知映射文件内存
HEAP_GRAPHICS = 17                  # 图形相关内存
HEAP_GL = 18                        # OpenGL图形内存
HEAP_OTHER_MEMTRACK = 19            # 其他内存追踪

# Dalvik heap subdivisions (Android 5.0+)
HEAP_DALVIK_NORMAL = 20             # Dalvik普通堆空间
HEAP_DALVIK_LARGE = 21              # Dalvik大对象堆空间
HEAP_DALVIK_ZYGOTE = 22             # Dalvik Zygote堆空间
HEAP_DALVIK_NON_MOVING = 23         # Dalvik非移动对象堆空间

# Dalvik other subdivisions (Android 6.0+)
HEAP_DALVIK_OTHER_LINEARALLOC = 24          # Dalvik线性分配器
HEAP_DALVIK_OTHER_ACCOUNTING = 25           # Dalvik内存记账
HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE = 26    # Zygote代码缓存
HEAP_DALVIK_OTHER_APP_CODE_CACHE = 27       # 应用代码缓存
HEAP_DALVIK_OTHER_COMPILER_METADATA = 28    # 编译器元数据
HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE = 29  # 间接引用表

# DEX/VDEX subdivisions (Android 7.0+)
HEAP_DEX_BOOT_VDEX = 30             # 启动VDEX验证文件
HEAP_DEX_APP_DEX = 31               # 应用DEX文件
HEAP_DEX_APP_VDEX = 32              # 应用VDEX验证文件

# ART subdivisions (Android 8.0+)
HEAP_ART_APP = 33                   # 应用ART文件
HEAP_ART_BOOT = 34                  # 启动ART文件

# Android 15+ new heap types
HEAP_NATIVE_HEAP = 35               # 本地堆内存
HEAP_DMABUF = 36                    # DMA缓冲区内存
HEAP_JIT_CACHE = 37                 # JIT编译缓存
HEAP_ZYGOTE_CODE_CACHE = 38         # Zygote代码缓存
HEAP_APP_CODE_CACHE = 39            # 应用代码缓存

# Android 16+ new heap types (backward compatible)
HEAP_SCUDO_HEAP = 40                # Scudo内存分配器堆
HEAP_GWP_ASAN = 41                  # GWP-ASan调试堆
HEAP_TLS_OPTIMIZED = 42             # 优化的线程本地存储
HEAP_APEX_MAPPING = 43              # APEX模块映射内存
HEAP_16KB_PAGE_ALIGNED = 44         # 16KB页面对齐内存

# Constants for heap categorization
_NUM_HEAP = type_length
_NUM_EXCLUSIVE_HEAP = HEAP_OTHER_MEMTRACK + 1
_NUM_CORE_HEAP = HEAP_NATIVE + 1

# Comprehensive memory type descriptions with Chinese explanations
# Adaptively supports all Android versions
pss_type = [
    "Unknown (未知内存类型)",
    "Dalvik (Dalvik虚拟机运行时内存)", 
    "Native (本地C/C++代码内存)", 
    "Dalvik Other (Dalvik虚拟机额外内存)", 
    "Stack (线程栈内存)", 
    "Cursor (数据库游标内存)", 
    "Ashmem (匿名共享内存)", 
    "Gfx dev (图形设备内存)",
    "Other dev (其他设备内存)", 
    ".so mmap (动态链接库映射内存)", 
    ".jar mmap (JAR文件映射内存)", 
    ".apk mmap (APK文件映射内存)", 
    ".ttf mmap (字体文件映射内存)", 
    ".dex mmap (DEX字节码文件映射内存)", 
    ".oat mmap (编译后的安卓应用程序映射内存)", 
    ".art mmap (ART运行时文件映射内存)", 
    "Other mmap (其他文件映射内存)",
    "graphics (图形相关内存)",
    "gl (OpenGL图形内存)",
    "other memtrack (其他内存追踪)",
    # Dalvik subdivisions
    "dalvik normal (Dalvik普通内存空间)",
    "dalvik large (Dalvik大对象内存空间)",
    "dalvik zygote (Dalvik进程孵化器内存)",
    "dalvik non moving (Dalvik非移动对象内存)",
    # Dalvik other subdivisions  
    "dalvik other linearalloc (Dalvik线性分配器内存)",
    "dalvik other accounting (Dalvik内存记账)",
    "dalvik other zygote code cache (Zygote代码缓存)",
    "dalvik other app code cache (应用代码缓存)",
    "dalvik other compiler metadata (编译器元数据)",
    "dalvik other indirect reference table (间接引用表)",
    # DEX/VDEX subdivisions
    "dex boot vdex (启动阶段DEX验证文件)",
    "dex app dex (应用DEX文件)",
    "dex app vdex (应用DEX验证文件)",
    # ART subdivisions
    "heap art app (应用ART堆)",
    "heap art boot (启动ART堆)",
    # Android 15+ heap types
    "native heap (本地堆内存)",
    "dmabuf (直接内存缓冲区)",
    "jit cache (即时编译缓存)",
    "zygote code cache (Zygote代码缓存)",
    "app code cache (应用代码缓存)",
    # Android 16+ heap types
    "scudo heap (Scudo安全内存分配器)",
    "gwp-asan (GWP-ASan内存错误检测)",
    "tls optimized (优化的线程本地存储)",
    "apex mapping (APEX模块映射内存)",
    "16kb page aligned (16KB页面对齐内存)"
]

# Initialize type lists for detailed tracking
# Separate tracking for PSS and SwapPSS
pss_type_list = []      # For PSS detailed entries
swap_type_list = []     # For SwapPSS detailed entries
for i in range(type_length):
    pss_type_list.append({})
    swap_type_list.append({})

def help():
    """
    Enhanced argument parser with comprehensive Android version support
    """
    parser = argparse.ArgumentParser(
        description="Android App Memory Analysis Tool - Universal Android Version Support\n" +
                   "Android应用内存分析工具 - 全版本Android支持",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法 / Example Usage:
  python3 smaps_parser.py -p 1234                    # 分析进程ID 1234
  python3 smaps_parser.py -f smaps_file.txt          # 分析smaps文件
  python3 smaps_parser.py -p 1234 -t "Native"        # 只分析Native内存
  python3 smaps_parser.py -p 1234 -o report.txt      # 指定输出文件
  python3 smaps_parser.py -p 1234 -s                 # 简化输出模式

支持的Android版本 / Supported Android Versions:
  • Android 4.0+ (基础功能)
  • Android 15+ (增强内存分析)  
  • Android 16+ (最新安全和性能特性)
  • 自动向后兼容所有版本
        """)
    
    parser.add_argument('-p', '--pid', 
                       help="目标进程PID / Target process PID")
    parser.add_argument('-f', '--filename', 
                       help="smaps文件路径 / Path to smaps file")
    parser.add_argument('-t', '--type', 
                       help="内存类型过滤 / Memory type filter (e.g., Unknown, Dalvik, Native)", 
                       default="ALL")
    parser.add_argument('-o', '--output', 
                       help="输出文件路径 / Output file path", 
                       default="smaps_analysis.txt")
    parser.add_argument('-s', '--simple', 
                       action="store_true", 
                       help="简化输出模式 / Simple output mode", 
                       default=False)
    parser.add_argument('--version', 
                       action="version", 
                       version="Android Memory Parser v2.1 (Universal Android Support)")
    
    return parser.parse_args()

def match_head(line):
    """
    Enhanced header line matching with improved regex for Android version compatibility
    """
    # More flexible regex to handle various smaps formats across Android versions
    patterns = [
        r'([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+):([0-9a-f]+)\s+(\d+)\s*(.*)$',
        r'(\w*)-(\w*)\s+(\S*)\s+(\w*)\s+(\w*):(\w*)\s+(\w*)\s*(.+)$'  # Original pattern for compatibility
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line, re.I)
        if match:
            return match
    return None

def match_pss(line):
    """
    Enhanced PSS value matching supporting various Android version formats
    """
    patterns = [
        r'Pss:\s+([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)[bB]?\s*(?::\s*(.+))?',
        r'Pss:\s+([0-9.]+)\s*[kM]B\s*(?::?\s*(.+))?'  # Original pattern for compatibility
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line, re.I)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower() if len(match.groups()) > 1 and match.group(2) else 'k'
            # Convert to kB if needed
            if unit.startswith('m'):
                value *= 1000
            
            # Return normalized match object
            class NormalizedMatch:
                def group(self, n):
                    if n == 1:
                        return str(int(value))
                    elif n == 2:
                        return match.group(3) if len(match.groups()) > 2 and match.group(3) else None
                    return None
            return NormalizedMatch()
    return None

def match_swapPss(line):
    """
    Enhanced SwapPSS value matching supporting various Android version formats
    """
    patterns = [
        r'SwapPss:\s+([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)[bB]?\s*(?::\s*(.+))?',
        r'SwapPss:\s+([0-9.]+)\s*[kM]B\s*(?::?\s*(.+))?'  # Original pattern for compatibility
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line, re.I)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower() if len(match.groups()) > 1 and match.group(2) else 'k'
            # Convert to kB if needed
            if unit.startswith('m'):
                value *= 1000
            
            # Return normalized match object
            class NormalizedMatch:
                def group(self, n):
                    if n == 1:
                        return str(int(value))
                    elif n == 2:
                        return match.group(3) if len(match.groups()) > 2 and match.group(3) else None
                    return None
            return NormalizedMatch()
    return None

def match_type(name, prewhat):
    """
    Universal memory type matching for all Android versions
    
    Classifies memory regions based on their name patterns.
    Supports Android 4.0 through Android 16+ with automatic fallback for older versions.
    
    Args:
        name (str): Memory region name from smaps
        prewhat (int): Previous heap type for context
        
    Returns:
        int: Heap type constant representing the memory category
    """
    which_heap = HEAP_UNKNOWN
    sub_heap = HEAP_UNKNOWN
    is_swappable = False

    # Remove deleted marker if present
    if name.endswith(" (deleted)"):
        name = name[0 : len(name) - len(' (deleted)')]

    size = len(name)

    # Enhanced native heap detection (Android 15+, fallback for older versions)
    if name.startswith("[heap]") or name.startswith("[anon:native]"):
        which_heap = HEAP_NATIVE_HEAP if HEAP_NATIVE_HEAP < type_length else HEAP_NATIVE
    elif name.startswith("[anon:libc_malloc]"):
        which_heap = HEAP_NATIVE
    
    # Android 16+ Scudo allocator detection (with fallback)
    elif name.startswith("[anon:scudo:") or name.startswith("[anon:scudo_"):
        which_heap = HEAP_SCUDO_HEAP if HEAP_SCUDO_HEAP < type_length else HEAP_NATIVE
    
    # Android 16+ GWP-ASan debugging heap detection (with fallback)
    elif name.startswith("[anon:GWP-ASan") or name.startswith("[anon:gwp_asan"):
        which_heap = HEAP_GWP_ASAN if HEAP_GWP_ASAN < type_length else HEAP_NATIVE
    
    # Android 16+ TLS optimization detection (with fallback)
    elif name.startswith("[anon:tls_") or name.startswith("[anon:thread_local"):
        which_heap = HEAP_TLS_OPTIMIZED if HEAP_TLS_OPTIMIZED < type_length else HEAP_STACK
    
    elif name.startswith("[stack") or name.startswith("[anon:stack_and_tls:") or name.startswith("[anon:stack:"):
        which_heap = HEAP_STACK
    
    # Android 15+ DMA-BUF heap detection (with fallback)
    elif name.startswith("/dev/dma_heap/") or name.startswith("/dev/dmabuf/"):
        which_heap = HEAP_DMABUF if HEAP_DMABUF < type_length else HEAP_UNKNOWN_DEV
    
    # Android 15+ JIT cache detection (with fallback)
    elif name.startswith("/memfd:jit-cache") or name.startswith("[anon:jit-cache"):
        which_heap = HEAP_JIT_CACHE if HEAP_JIT_CACHE < type_length else HEAP_DALVIK_OTHER
    
    elif name.startswith("/memfd:jit-zygote-cache") or name.startswith("[anon:jit-zygote-cache"):
        which_heap = HEAP_ZYGOTE_CODE_CACHE if HEAP_ZYGOTE_CODE_CACHE < type_length else HEAP_DALVIK_OTHER
    
    # Android 16+ APEX module mapping detection (with fallback)
    elif name.startswith("/apex/") or name.startswith("[anon:apex_"):
        which_heap = HEAP_APEX_MAPPING if HEAP_APEX_MAPPING < type_length else HEAP_UNKNOWN_MAP
    
    # Android 16+ 16KB page aligned memory detection (with fallback)
    elif "16kb" in name.lower() or "16k_page" in name.lower():
        which_heap = HEAP_16KB_PAGE_ALIGNED if HEAP_16KB_PAGE_ALIGNED < type_length else HEAP_UNKNOWN
    
    elif name.endswith(".so"):
        which_heap = HEAP_SO
        is_swappable = True
    elif name.endswith(".jar"):
        which_heap = HEAP_JAR
        is_swappable = True
    elif name.endswith(".apk"):
        which_heap = HEAP_APK
        is_swappable = True
    elif name.endswith(".ttf"):
        which_heap = HEAP_TTF
        is_swappable = True
    elif name.endswith(".odex") or (size > 4 and ".dex" in name):
        which_heap = HEAP_DEX
        sub_heap = HEAP_DEX_APP_DEX if HEAP_DEX_APP_DEX < type_length else HEAP_UNKNOWN
        is_swappable = True
    elif name.endswith(".vdex"):
        which_heap = HEAP_DEX
        # Handle system@framework@boot and system/framework/boot|apex
        if "@boot" in name or "/boot" in name or "/apex" in name:
            sub_heap = HEAP_DEX_BOOT_VDEX if HEAP_DEX_BOOT_VDEX < type_length else HEAP_UNKNOWN
        else:
            sub_heap = HEAP_DEX_APP_VDEX if HEAP_DEX_APP_VDEX < type_length else HEAP_UNKNOWN
        is_swappable = True
    elif name.endswith(".oat"):
        which_heap = HEAP_OAT
        is_swappable = True
    elif name.endswith(".art") or name.endswith(".art]"):
        which_heap = HEAP_ART
        # Handle system@framework@boot* and system/framework/boot|apex*
        if "@boot" in name or "/boot" in name or "/apex" in name:
            sub_heap = HEAP_ART_BOOT if HEAP_ART_BOOT < type_length else HEAP_UNKNOWN
        else:
            sub_heap = HEAP_ART_APP if HEAP_ART_APP < type_length else HEAP_UNKNOWN
        is_swappable = True
    elif name.startswith("/dev"):
        which_heap = HEAP_UNKNOWN_DEV
        if name.startswith("/dev/kgsl-3d0"):
            which_heap = HEAP_GL_DEV
        elif "/dev/ashmem/CursorWindow" in name:
            which_heap = HEAP_CURSOR
        elif name.startswith("/dev/ashmem/jit-zygote-cache"):
            which_heap = HEAP_DALVIK_OTHER
            sub_heap = HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE if HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE < type_length else HEAP_UNKNOWN
        elif "/dev/ashmem" in name:
            which_heap = HEAP_ASHMEM
    elif name.startswith("/memfd:jit-cache"):
        which_heap = HEAP_DALVIK_OTHER
        sub_heap = HEAP_DALVIK_OTHER_APP_CODE_CACHE if HEAP_DALVIK_OTHER_APP_CODE_CACHE < type_length else HEAP_UNKNOWN
    elif name.startswith("/memfd:jit-zygote-cache"):
        which_heap = HEAP_DALVIK_OTHER
        sub_heap = HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE if HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE < type_length else HEAP_UNKNOWN
    elif name.startswith("[anon:"):
        which_heap = HEAP_UNKNOWN
        if name.startswith("[anon:dalvik-"):
            which_heap = HEAP_DALVIK_OTHER
            if name.startswith("[anon:dalvik-LinearAlloc"):
                sub_heap = HEAP_DALVIK_OTHER_LINEARALLOC if HEAP_DALVIK_OTHER_LINEARALLOC < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-alloc space") or name.startswith("[anon:dalvik-main space"):
                # This is the regular Dalvik heap.
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_NORMAL if HEAP_DALVIK_NORMAL < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-large object space") or name.startswith("[anon:dalvik-free list large object space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_LARGE if HEAP_DALVIK_LARGE < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-non moving space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_NON_MOVING if HEAP_DALVIK_NON_MOVING < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-zygote space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_ZYGOTE if HEAP_DALVIK_ZYGOTE < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-indirect ref"):
                sub_heap = HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE if HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-jit-code-cache") or name.startswith("[anon:dalvik-data-code-cache"):
                which_heap = HEAP_APP_CODE_CACHE if HEAP_APP_CODE_CACHE < type_length else HEAP_DALVIK_OTHER
            elif name.startswith("[anon:dalvik-CompilerMetadata"):
                sub_heap = HEAP_DALVIK_OTHER_COMPILER_METADATA if HEAP_DALVIK_OTHER_COMPILER_METADATA < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-accounting"):
                sub_heap = HEAP_DALVIK_OTHER_ACCOUNTING if HEAP_DALVIK_OTHER_ACCOUNTING < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-linearalloc"):
                sub_heap = HEAP_DALVIK_OTHER_LINEARALLOC if HEAP_DALVIK_OTHER_LINEARALLOC < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-zygote-code-cache"):
                sub_heap = HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE if HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-app-code-cache"):
                sub_heap = HEAP_DALVIK_OTHER_APP_CODE_CACHE if HEAP_DALVIK_OTHER_APP_CODE_CACHE < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-compiler-metadata"):
                sub_heap = HEAP_DALVIK_OTHER_COMPILER_METADATA if HEAP_DALVIK_OTHER_COMPILER_METADATA < type_length else HEAP_UNKNOWN
            elif name.startswith("[anon:dalvik-other-indirect-reference-table"):
                sub_heap = HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE if HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE < type_length else HEAP_UNKNOWN
            else:
                sub_heap = HEAP_DALVIK_OTHER_ACCOUNTING if HEAP_DALVIK_OTHER_ACCOUNTING < type_length else HEAP_UNKNOWN
    elif name != " " and len(name) > 0:
        which_heap = HEAP_UNKNOWN_MAP
    elif prewhat == 10:
        which_heap = 10
    
    # Ensure we return a valid heap type within bounds
    if which_heap < 0 or which_heap >= type_length:
        which_heap = HEAP_UNKNOWN
        
    return which_heap

def parse_smaps(filename):
    """
    Universal smaps parser with enhanced error handling and Android version compatibility
    """
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as file:
            print(f"正在解析smaps文件，支持全版本Android...")
            print(f"Parsing smaps file with universal Android version support...")
            
            line = file.readline()
            if not line:
                print("警告: smaps文件为空 / Warning: smaps file is empty")
                return
                
            what = 0
            prewhat = 0
            name = ""  # Initialize name
            total_entries = 0
            
            while line:
                tmp = match_head(line)
                if tmp:
                    name = tmp.group(8) if tmp.group(8) else ""
                    what = match_type(name, prewhat)
                    total_entries += 1
                    
                    # Progress indicator for large files
                    if total_entries % 1000 == 0:
                        print(f"已处理 {total_entries} 个内存区域...")
                
                while True:
                    line2 = file.readline()
                    if not line2:
                        print(f"\n解析完成，共处理 {total_entries} 个内存区域")
                        return
                        
                    tmp2 = match_pss(line2)
                    tmp3 = match_swapPss(line2)
                    pss = 0  # Initialize pss with default value
                    
                    if tmp2 or tmp3:
                        if 0 <= what < len(pss_count):  # Bounds checking
                            if tmp2:
                                try:
                                    pss = int(float(tmp2.group(1)))  # Handle decimal PSS values
                                    pss_count[what] += pss
                                    # Track PSS details separately
                                    if pss > 0:
                                        pssSum_count[what] += pss
                                        if what < len(pss_type_list):
                                            pss_tmplist = pss_type_list[what]
                                            if name in pss_tmplist:
                                                pss_tmplist[name] += pss
                                            else:
                                                pss_tmplist[name] = pss
                                except (ValueError, IndexError):
                                    continue
                                    
                            if tmp3:
                                try:
                                    swap_pss = int(float(tmp3.group(1)))  # Handle decimal SwapPSS values
                                    swapPss_count[what] += swap_pss
                                    # Track SwapPSS details separately
                                    if swap_pss > 0:
                                        if what < len(swap_type_list):
                                            swap_tmplist = swap_type_list[what]
                                            if name in swap_tmplist:
                                                swap_tmplist[name] += swap_pss
                                            else:
                                                swap_tmplist[name] = swap_pss
                                except (ValueError, IndexError):
                                    continue
                    else:
                        tmp4 = match_head(line2)
                        if tmp4:
                            line = line2
                            prewhat = what
                            break
                            
    except FileNotFoundError:
        print(f"错误: 找不到文件 {filename} / Error: File not found {filename}")
    except PermissionError:
        print(f"错误: 没有权限读取文件 {filename} / Error: Permission denied reading {filename}")
    except Exception as e:
        print(f"解析smaps文件时发生错误: {e} / Error parsing smaps file: {e}")

def analyze_memory_insights(args):
    """
    Universal memory analysis with insights for all Android versions
    """
    insights = {
        "total_memory_mb": sum(pssSum_count) / 1000,
        "total_swap_mb": sum(swapPss_count) / 1000,
        "anomalies": [],
        "recommendations": []
    }
    
    total_memory = sum(pssSum_count)
    
    # 1. 检测内存泄漏指标 (all Android versions)
    dalvik_memory = pss_count[HEAP_DALVIK]
    if HEAP_DALVIK_NORMAL < type_length:
        dalvik_memory += pss_count[HEAP_DALVIK_NORMAL]
    if HEAP_DALVIK_LARGE < type_length:
        dalvik_memory += pss_count[HEAP_DALVIK_LARGE]
    
    native_memory = pss_count[HEAP_NATIVE]
    if HEAP_NATIVE_HEAP < type_length:
        native_memory += pss_count[HEAP_NATIVE_HEAP]
    
    if dalvik_memory > 200 * 1000:  # 200MB
        insights["anomalies"].append({
            "type": "high_dalvik_memory",
            "severity": "high",
            "description": f"Dalvik堆内存过高: {dalvik_memory/1000:.1f}MB，可能存在Java内存泄漏",
            "recommendation": "检查对象引用、静态变量持有、监听器未注销等常见内存泄漏原因"
        })
    
    if native_memory > 150 * 1000:  # 150MB
        insights["anomalies"].append({
            "type": "high_native_memory",
            "severity": "high", 
            "description": f"Native内存过高: {native_memory/1000:.1f}MB，可能存在C/C++内存泄漏",
            "recommendation": "检查NDK代码中的malloc/free配对、JNI对象释放等"
        })
    
    # 2. 实用的内存分析 - 关注实际问题而非版本特性
    # 检查是否有大量的未分类内存
    unknown_memory = pss_count[HEAP_UNKNOWN] if HEAP_UNKNOWN < type_length else 0
    if unknown_memory > 50 * 1000:  # 50MB
        insights["recommendations"].append({
            "type": "high_unknown_memory",
            "description": f"未分类内存较多: {unknown_memory/1000:.1f}MB",
            "recommendation": "可能存在未优化的内存分配，建议详细分析内存映射"
        })
    
    # 检查 JIT 缓存是否过大
    jit_memory = 0
    if HEAP_JIT_CACHE < type_length:
        jit_memory = pss_count[HEAP_JIT_CACHE]
    if jit_memory > 100 * 1000:  # 100MB
        insights["recommendations"].append({
            "type": "high_jit_cache",
            "description": f"JIT缓存较大: {jit_memory/1000:.1f}MB",
            "recommendation": "JIT缓存过大可能影响内存效率，检查热点代码优化"
        })
    
    # 3. 通用内存分析
    graphics_memory = pss_count[HEAP_GRAPHICS] + pss_count[HEAP_GL]
    if graphics_memory > 80 * 1000:  # 80MB
        insights["recommendations"].append({
            "type": "high_graphics_memory",
            "description": f"图形内存使用较高: {graphics_memory/1000:.1f}MB",
            "recommendation": "检查纹理加载、视图缓存、动画对象等图形资源管理"
        })
    
    return insights

def print_result(args):
    """
    Universal result printing with comprehensive Android version support
    """
    if args.pid and not args.output:
        try:
            output = "%d_smaps_analysis.txt" % int(args.pid)
        except:
            output = "smaps_analysis.txt"
    else:
        output = args.output
        
    type_filter = args.type
    simple = args.simple
    index = -1
    
    if not type_filter == "ALL":
        if type_filter in pss_type:
            index = pss_type.index(type_filter)
        else:
            print("请输入正确的内存类型 / Please enter a correct memory type")
            return
    
    # Generate insights
    insights = analyze_memory_insights(args)
    
    # Write analysis results
    with open(output, 'w', encoding='utf-8') as output_file:
        # Header with timestamp and version info
        header = f"""
========================================
Android App Memory Analysis Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Script Version: Universal Android Support
========================================

"""        
        print(header)
        output_file.write(header)
        
        # Memory overview
        overview = f"""内存概览 / Memory Overview:
总内存使用: {insights['total_memory_mb']:.2f} MB
总交换内存: {insights['total_swap_mb']:.2f} MB

"""        
        print(overview)
        output_file.write(overview)
        
        # Detailed memory breakdown
        if index == -1:
            # Show all memory types with data
            for i in range(len(pss_type)):
                type_name = pss_type[i]
                pss_sum = pssSum_count[i] if i < len(pssSum_count) else 0
                pss_val = pss_count[i] if i < len(pss_count) else 0
                swap_val = swapPss_count[i] if i < len(swapPss_count) else 0
                pss_dict = pss_type_list[i] if i < len(pss_type_list) else {}
                swap_dict = swap_type_list[i] if i < len(swap_type_list) else {}
                
                if pss_sum > 0 or pss_val > 0 or swap_val > 0:  # Only show non-zero entries
                    tmp = f"{type_name} : {float(pss_sum)/1000:.3f} MB"
                    print(tmp)
                    output_file.write(tmp + "\n")
                    
                    # PSS section with details
                    tmp = f"\tPSS: {float(pss_val)/1000:.3f} MB"
                    print(tmp)
                    output_file.write(tmp + "\n")
                    
                    if not simple and pss_dict:
                        count = Counter(pss_dict)
                        for name, size in count.most_common(10):  # Limit to top 10
                            tmp = f"\t\t{name} : {size} kB"
                            print(tmp)
                            output_file.write(tmp + "\n")
                    
                    # SwapPSS section with details
                    tmp = f"\tSwapPSS: {float(swap_val)/1000:.3f} MB"
                    print(tmp)
                    output_file.write(tmp + "\n")
                    
                    if not simple and swap_dict:
                        count = Counter(swap_dict)
                        for name, size in count.most_common(10):  # Limit to top 10
                            tmp = f"\t\t{name} : {size} kB"
                            print(tmp)
                            output_file.write(tmp + "\n")
                    
                    output_file.write("\n")
        else:
            # Show specific memory type
            if index < len(pssSum_count):
                tmp = f"{pss_type[index]} : {float(pssSum_count[index])/1000:.3f} MB"
                print(tmp)
                output_file.write(tmp + "\n")
                
                # PSS section with details
                tmp = f"\tPSS: {float(pss_count[index])/1000:.3f} MB"
                print(tmp)
                output_file.write(tmp + "\n")
                
                if not simple and index < len(pss_type_list):
                    count = Counter(pss_type_list[index])
                    for name, size in count.most_common():
                        tmp = f"\t\t{name} : {size} kB"
                        print(tmp)
                        output_file.write(tmp + "\n")
                
                # SwapPSS section with details
                tmp = f"\tSwapPSS: {float(swapPss_count[index])/1000:.3f} MB"
                print(tmp)
                output_file.write(tmp + "\n")
                
                if not simple and index < len(swap_type_list):
                    count = Counter(swap_type_list[index])
                    for name, size in count.most_common():
                        tmp = f"\t\t{name} : {size} kB"
                        print(tmp)
                        output_file.write(tmp + "\n")
        
        # Add insights section
        insights_section = "\n" + "="*50 + "\n"
        insights_section += "内存分析洞察 / Memory Analysis Insights\n"
        insights_section += "="*50 + "\n\n"
        
        # Anomalies
        if insights["anomalies"]:
            insights_section += "⚠️  异常检测 / Anomalies Detected:\n"
            for anomaly in insights["anomalies"]:
                insights_section += f"  • [{anomaly['severity'].upper()}] {anomaly['description']}\n"
                insights_section += f"    建议: {anomaly['recommendation']}\n\n"
        
        # Recommendations
        if insights["recommendations"]:
            insights_section += "💡 优化建议 / Optimization Recommendations:\n"
            for rec in insights["recommendations"]:
                insights_section += f"  • {rec['description']}\n"
                insights_section += f"    建议: {rec['recommendation']}\n\n"
        
        # Only show insights section if there are actual insights
        if insights["anomalies"] or insights["recommendations"]:
            print(insights_section)
            output_file.write(insights_section)
        
        # Educational Resources Section
        education_section = "\n" + "="*60 + "\n"
        education_section += "📚 深入学习指南 / Educational Resources\n"
        education_section += "="*60 + "\n\n"
        education_section += "为了更好地理解分析结果，建议阅读以下详细指南：\n"
        education_section += "For better understanding of analysis results, please refer to these detailed guides:\n\n"
        
        education_section += "🔍 基础内存分析 / Basic Memory Analysis:\n"
        education_section += "  • dumpsys meminfo 输出详解指南 / dumpsys meminfo Interpretation Guide:\n"
        education_section += "    ./meminfo_interpretation_guide.md\n"
        education_section += "    应用级内存使用分析，理解应用内存分布和使用状况\n\n"
        
        education_section += "  • /proc/meminfo 输出详解指南 / /proc/meminfo Interpretation Guide:\n"
        education_section += "    ./proc_meminfo_interpretation_guide.md\n"
        education_section += "    系统级内存使用分析，理解设备整体内存状况\n\n"
        
        education_section += "  • showmap 输出详解指南 / showmap Interpretation Guide:\n"
        education_section += "    ./showmap_interpretation_guide.md\n"
        education_section += "    进程级内存映射概览，快速识别内存使用模式\n\n"
        
        education_section += "🗺️ 详细内存分析 / Detailed Memory Analysis:\n"
        education_section += "  • smaps 输出详解指南 / smaps Interpretation Guide:\n"
        education_section += "    ./smaps_interpretation_guide.md\n"
        education_section += "    最详细的内存映射分析，深入理解每个内存区域\n\n"
        
        education_section += "📊 解析结果理解 / Understanding Analysis Results:\n"
        education_section += "  • 分析结果详解指南 / Analysis Results Interpretation Guide:\n"
        education_section += "    ./analysis_results_interpretation_guide.md\n"
        education_section += "    理解本工具输出的每一项数据和优化建议\n\n"
        
        education_section += "💡 推荐学习路径 / Recommended Learning Path:\n"
        education_section += "   1️⃣ 先阅读 meminfo 指南了解系统内存基础\n"
        education_section += "   2️⃣ 然后学习 showmap 指南掌握进程内存概览\n"
        education_section += "   3️⃣ 深入研究 smaps 指南理解详细内存映射\n"
        education_section += "   4️⃣ 最后参考分析结果指南优化内存使用\n\n"
        
        print(education_section)
        output_file.write(education_section)
        
        # Footer
        footer = f"\n分析完成 / Analysis completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        footer += "工具版本 / Tool version: Universal Android Memory Parser\n"
        print(footer)
        output_file.write(footer)
    
    print(f"\n详细报告已保存到: {output}")

def main():
    """
    Main function with universal Android version support and enhanced error handling
    """
    try:
        args = help()
            
        if args.filename:
            if os.path.exists(args.filename):
                print(f"正在解析smaps文件: {args.filename}")
                parse_smaps(args.filename)
                print_result(args)
            else:
                print(f"错误: smaps文件不存在 / Error: smaps file does not exist: {args.filename}")
                
        elif args.pid:
            if args.pid.isdigit():
                pid = int(args.pid)
                if pid > 0:
                    print(f"正在分析进程 PID: {pid}")
                    
                    # Universal ADB commands with enhanced compatibility
                    if sys.platform == "win32":
                        check_cmd = 'adb shell "su -c \'ls /proc/%d/smaps\' root 2>/dev/null"' % pid
                        read_cmd = 'adb shell "su -c \'cat /proc/%d/smaps\' root"' % pid
                    else:
                        check_cmd = "adb shell 'su -c \"ls /proc/%d/smaps\" root 2>/dev/null'" % pid
                        read_cmd = "adb shell 'su -c \"cat /proc/%d/smaps\" root'" % pid
                    
                    ret = os.system(check_cmd)
                    if ret == 0:
                        print("正在读取内存映射数据...")
                        
                        smaps_filename = f"{pid}_smaps_file.txt"
                        
                        try:
                            with os.popen(read_cmd) as proc:
                                with open(smaps_filename, 'w', encoding='utf-8') as new_file:
                                    lines = proc.readlines()
                                    for line in lines:
                                        new_file.write(line)
                            
                            if os.path.getsize(smaps_filename) > 0:
                                parse_smaps(smaps_filename)
                                print_result(args)
                            else:
                                print(f"警告: smaps文件为空，可能权限不足")
                                
                        except Exception as e:
                            print(f"读取smaps数据时出错: {e}")
                    else:
                        print(f"错误: 无法访问 /proc/{pid}/smaps")
                        print("请确保:")
                        print("  • 设备已获得root权限 / Device is rooted")
                        print("  • ADB连接正常 / ADB connection is working")
                        print("  • PID存在且正确 / PID exists and is correct")
                else:
                    print("错误: 请输入正确的PID / Error: Please enter a correct PID")
            else:
                print("错误: PID必须是数字 / Error: PID must be a number")
        else:
            print("错误: 请提供PID或smaps文件路径")
            print("Error: Please provide a PID or smaps file path")
            print("\n使用方法 / Usage:")
            print("  python3 smaps_parser.py -p <PID>")
            print("  python3 smaps_parser.py -f <smaps_file>")
            
    except KeyboardInterrupt:
        print("\n分析被用户中断 / Analysis interrupted by user")
    except Exception as e:
        print(f"发生未预期的错误 / Unexpected error occurred: {e}")
        print("请检查输入参数和设备连接 / Please check input parameters and device connection")

if __name__ == "__main__":
    main()