#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Android 内存全景分析器

整合多数据源进行深度关联分析：
- meminfo: Native Allocations（Bitmap 精确统计）
- gfxinfo: GPU 缓存、GraphicBuffer
- hprof: Java 堆对象详情（可选）
- smaps: 进程内存映射（需要 root）

核心功能：
- Bitmap 深度关联：Java 对象 ↔ Native 像素数据
- Native 内存追踪：可追踪 vs 未追踪
- 内存分布可视化
- 综合优化建议
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any

# Import parsers
from meminfo_parser import parse_meminfo_file, MeminfoParser, MeminfoData
from gfxinfo_parser import parse_gfxinfo_file, GfxinfoData
from hprof_parser import HprofParser
from proc_meminfo_parser import parse_proc_meminfo_file, ProcMeminfoData
from dmabuf_parser import parse_dmabuf_file, DmaBufData
from zram_parser import parse_zram_swap_file, ZramSwapData


@dataclass
class BitmapCorrelation:
    """Bitmap 关联分析结果"""
    # 来自 meminfo
    meminfo_count: int = 0
    meminfo_malloced_count: int = 0
    meminfo_malloced_kb: float = 0
    meminfo_nonmalloced_count: int = 0
    meminfo_nonmalloced_kb: float = 0
    meminfo_total_kb: float = 0

    # 来自 gfxinfo
    gpu_cache_mb: float = 0
    graphic_buffers_kb: float = 0
    graphic_buffers_count: int = 0

    # 来自 HPROF（如果有）
    hprof_count: int = 0
    hprof_estimated_kb: float = 0

    # 分析结论
    correlation_notes: List[str] = field(default_factory=list)


@dataclass
class NativeMemoryTracking:
    """Native 内存追踪结果"""
    # 来自 meminfo
    native_heap_pss_kb: int = 0

    # 可追踪部分
    bitmap_kb: float = 0
    other_malloced_kb: float = 0
    other_nonmalloced_kb: float = 0
    tracked_total_kb: float = 0

    # 未追踪部分
    untracked_kb: float = 0
    untracked_percent: float = 0

    # 分析结论
    tracking_notes: List[str] = field(default_factory=list)


@dataclass
class HprofSummary:
    """HPROF 堆分析摘要"""
    # 基础统计
    total_instances: int = 0
    total_arrays: int = 0
    total_memory_mb: float = 0
    instance_size_mb: float = 0
    array_size_mb: float = 0

    # Bitmap 统计
    bitmap_count: int = 0
    bitmap_size_mb: float = 0

    # TOP 类统计
    top_classes: List[Dict] = field(default_factory=list)

    # 分析结论
    hprof_notes: List[str] = field(default_factory=list)


@dataclass
class SystemMemoryContext:
    """系统内存上下文"""
    # 基础内存
    total_mb: float = 0
    available_mb: float = 0
    used_mb: float = 0
    available_percent: float = 0

    # 缓存
    cached_mb: float = 0
    buffers_mb: float = 0

    # Swap
    swap_total_mb: float = 0
    swap_used_mb: float = 0
    swap_used_percent: float = 0

    # ION (GPU/Camera)
    ion_heap_mb: float = 0

    # 内存压力
    pressure_level: str = ""
    pressure_level_cn: str = ""

    # 分析结论
    system_notes: List[str] = field(default_factory=list)


@dataclass
class DmaBufContext:
    """DMA-BUF 内存分析结果"""
    total_mb: float = 0
    total_count: int = 0

    # 分类统计
    gpu_mb: float = 0
    gpu_count: int = 0
    display_mb: float = 0
    display_count: int = 0
    camera_mb: float = 0
    camera_count: int = 0
    video_mb: float = 0
    video_count: int = 0
    audio_mb: float = 0
    audio_count: int = 0
    other_mb: float = 0
    other_count: int = 0

    # 分析结论
    dmabuf_notes: List[str] = field(default_factory=list)


@dataclass
class ZramSwapContext:
    """zRAM/Swap 分析结果"""
    # Swap 统计
    swap_total_mb: float = 0
    swap_used_mb: float = 0
    swap_used_percent: float = 0
    swap_device_count: int = 0

    # zRAM 统计
    has_zram: bool = False
    zram_disk_mb: float = 0
    zram_orig_mb: float = 0
    zram_compr_mb: float = 0
    zram_mem_used_mb: float = 0
    zram_compression_ratio: float = 0
    zram_space_saving_percent: float = 0
    zram_memory_saved_mb: float = 0
    zram_device_count: int = 0

    # 分析结论
    zram_swap_notes: List[str] = field(default_factory=list)


@dataclass
class PanoramaResult:
    """全景分析结果"""
    package_name: str = ""
    pid: int = 0

    # 内存概览
    total_pss_mb: float = 0
    java_heap_mb: float = 0
    native_heap_mb: float = 0
    graphics_mb: float = 0
    code_mb: float = 0
    stack_mb: float = 0

    # Bitmap 关联
    bitmap_correlation: BitmapCorrelation = field(default_factory=BitmapCorrelation)

    # Native 追踪
    native_tracking: NativeMemoryTracking = field(default_factory=NativeMemoryTracking)

    # HPROF 堆分析
    hprof_summary: HprofSummary = field(default_factory=HprofSummary)

    # 系统内存上下文
    system_memory: SystemMemoryContext = field(default_factory=SystemMemoryContext)

    # DMA-BUF 分析
    dmabuf_context: DmaBufContext = field(default_factory=DmaBufContext)

    # zRAM/Swap 分析
    zram_swap_context: ZramSwapContext = field(default_factory=ZramSwapContext)

    # UI 资源
    views_count: int = 0
    activities_count: int = 0
    viewrootimpl_count: int = 0
    webviews_count: int = 0

    # 帧率
    janky_percent: float = 0
    p50_ms: int = 0
    p90_ms: int = 0

    # 异常
    anomalies: List[Dict] = field(default_factory=list)

    # 优化建议
    recommendations: List[Dict] = field(default_factory=list)


@dataclass
class ThresholdConfig:
    """阈值配置"""
    # 内存阈值 (MB)
    pss_mb: Optional[float] = None
    java_heap_mb: Optional[float] = None
    native_heap_mb: Optional[float] = None
    graphics_mb: Optional[float] = None

    # 比例阈值 (%)
    native_untracked_percent: Optional[float] = None
    janky_percent: Optional[float] = None
    system_available_percent: Optional[float] = None  # 低于此值告警

    # 数量阈值
    views_count: Optional[int] = None
    activities_count: Optional[int] = None
    bitmap_count: Optional[int] = None

    # Bitmap 大小阈值 (MB)
    bitmap_total_mb: Optional[float] = None


@dataclass
class ThresholdViolation:
    """阈值违规"""
    name: str
    threshold: float
    actual: float
    unit: str = ""
    severity: str = "WARNING"  # WARNING, ERROR

    def __str__(self):
        if self.unit == "%":
            return f"{self.name}: {self.actual:.1f}% (阈值: {self.threshold:.1f}%)"
        elif self.unit == "MB":
            return f"{self.name}: {self.actual:.1f} MB (阈值: {self.threshold:.1f} MB)"
        else:
            return f"{self.name}: {self.actual:.0f} (阈值: {self.threshold:.0f})"


class PanoramaAnalyzer:
    """全景分析器"""

    def __init__(self, meminfo_file=None, gfxinfo_file=None, hprof_file=None, smaps_file=None, proc_meminfo_file=None, dmabuf_file=None, zram_swap_file=None, threshold_config=None):
        self.meminfo_file = meminfo_file
        self.gfxinfo_file = gfxinfo_file
        self.hprof_file = hprof_file
        self.smaps_file = smaps_file
        self.proc_meminfo_file = proc_meminfo_file
        self.dmabuf_file = dmabuf_file
        self.zram_swap_file = zram_swap_file
        self.threshold_config = threshold_config

        self.meminfo_data: Optional[MeminfoData] = None
        self.gfxinfo_data: Optional[GfxinfoData] = None
        self.hprof_data: Optional[Dict] = None
        self.smaps_data: Optional[Dict] = None
        self.proc_meminfo_data: Optional[ProcMeminfoData] = None
        self.dmabuf_data: Optional[DmaBufData] = None
        self.zram_swap_data: Optional[ZramSwapData] = None

    def parse_all(self):
        """解析所有可用的数据文件"""
        if self.meminfo_file and os.path.exists(self.meminfo_file):
            self.meminfo_data = parse_meminfo_file(self.meminfo_file)

        if self.gfxinfo_file and os.path.exists(self.gfxinfo_file):
            self.gfxinfo_data = parse_gfxinfo_file(self.gfxinfo_file)

        # 解析 HPROF 文件
        if self.hprof_file and os.path.exists(self.hprof_file):
            try:
                hprof_parser = HprofParser(self.hprof_file, verbose=False)
                if hprof_parser.parse_basic():
                    self.hprof_data = hprof_parser.get_summary(top_n=10)
            except Exception as e:
                print(f"警告: HPROF 解析失败: {e}")
                self.hprof_data = None

        # 解析 /proc/meminfo 文件
        if self.proc_meminfo_file and os.path.exists(self.proc_meminfo_file):
            try:
                self.proc_meminfo_data = parse_proc_meminfo_file(self.proc_meminfo_file)
            except Exception as e:
                print(f"警告: /proc/meminfo 解析失败: {e}")
                self.proc_meminfo_data = None

        # 解析 DMA-BUF 文件
        if self.dmabuf_file and os.path.exists(self.dmabuf_file):
            try:
                self.dmabuf_data = parse_dmabuf_file(self.dmabuf_file)
            except Exception as e:
                print(f"警告: DMA-BUF 解析失败: {e}")
                self.dmabuf_data = None

        # 解析 zRAM/Swap 文件
        if self.zram_swap_file and os.path.exists(self.zram_swap_file):
            try:
                self.zram_swap_data = parse_zram_swap_file(self.zram_swap_file)
            except Exception as e:
                print(f"警告: zRAM/Swap 解析失败: {e}")
                self.zram_swap_data = None

        # TODO: 集成 smaps 解析

    def analyze(self) -> PanoramaResult:
        """执行全景分析"""
        self.parse_all()

        result = PanoramaResult()

        # 基础信息
        if self.meminfo_data:
            result.package_name = self.meminfo_data.package_name
            result.pid = self.meminfo_data.pid

        # 内存概览
        self._analyze_memory_overview(result)

        # Bitmap 关联分析
        self._analyze_bitmap_correlation(result)

        # Native 内存追踪
        self._analyze_native_tracking(result)

        # HPROF 堆分析
        self._analyze_hprof(result)

        # 系统内存上下文
        self._analyze_system_memory(result)

        # DMA-BUF 分析
        self._analyze_dmabuf(result)

        # zRAM/Swap 分析
        self._analyze_zram_swap(result)

        # UI 资源分析
        self._analyze_ui_resources(result)

        # 帧率分析
        self._analyze_frame_stats(result)

        # 异常检测
        self._detect_anomalies(result)

        # 生成优化建议
        self._generate_recommendations(result)

        return result

    def _analyze_memory_overview(self, result: PanoramaResult):
        """分析内存概览"""
        if not self.meminfo_data:
            return

        result.total_pss_mb = self.meminfo_data.total_pss / 1024
        result.java_heap_mb = self.meminfo_data.java_heap_pss / 1024
        result.native_heap_mb = self.meminfo_data.native_heap_pss / 1024
        result.graphics_mb = self.meminfo_data.graphics_pss / 1024
        result.code_mb = self.meminfo_data.code_pss / 1024
        result.stack_mb = self.meminfo_data.stack_pss / 1024

    def _analyze_bitmap_correlation(self, result: PanoramaResult):
        """Bitmap 深度关联分析"""
        bc = result.bitmap_correlation

        # 从 meminfo 提取 Bitmap 统计
        if self.meminfo_data:
            parser = MeminfoParser("")
            parser.data = self.meminfo_data
            bitmap_stats = parser.get_bitmap_stats()

            bc.meminfo_malloced_count = int(bitmap_stats['malloced']['count'])
            bc.meminfo_malloced_kb = bitmap_stats['malloced']['size_kb']
            bc.meminfo_nonmalloced_count = int(bitmap_stats['nonmalloced']['count'])
            bc.meminfo_nonmalloced_kb = bitmap_stats['nonmalloced']['size_kb']
            bc.meminfo_count = bc.meminfo_malloced_count + bc.meminfo_nonmalloced_count
            bc.meminfo_total_kb = bc.meminfo_malloced_kb + bc.meminfo_nonmalloced_kb

        # 从 gfxinfo 提取 GPU 缓存信息
        if self.gfxinfo_data:
            bc.gpu_cache_mb = self.gfxinfo_data.gpu_total_bytes / 1024 / 1024
            bc.graphic_buffers_kb = self.gfxinfo_data.graphic_buffers_total_kb
            bc.graphic_buffers_count = len(self.gfxinfo_data.graphic_buffers)

        # 关联分析
        if bc.meminfo_count > 0:
            bc.correlation_notes.append(
                f"检测到 {bc.meminfo_count} 个 Bitmap，共 {bc.meminfo_total_kb/1024:.2f} MB"
            )

            # malloced vs nonmalloced 比例
            if bc.meminfo_nonmalloced_count > bc.meminfo_malloced_count:
                bc.correlation_notes.append(
                    f"大部分 Bitmap ({bc.meminfo_nonmalloced_count}/{bc.meminfo_count}) 使用 Native 直接分配"
                )

            # GPU 缓存使用
            if bc.gpu_cache_mb > 50:
                bc.correlation_notes.append(
                    f"GPU 缓存较大 ({bc.gpu_cache_mb:.1f} MB)，可能有大量纹理"
                )

            # GraphicBuffer
            if bc.graphic_buffers_count > 0:
                bc.correlation_notes.append(
                    f"GraphicBuffer: {bc.graphic_buffers_count} 个，共 {bc.graphic_buffers_kb/1024:.2f} MB"
                )

    def _analyze_native_tracking(self, result: PanoramaResult):
        """Native 内存追踪分析"""
        nt = result.native_tracking

        if not self.meminfo_data:
            return

        nt.native_heap_pss_kb = self.meminfo_data.native_heap_pss

        # 可追踪部分（来自 Native Allocations）
        for alloc in self.meminfo_data.native_allocations:
            if 'Bitmap' in alloc.name:
                nt.bitmap_kb += alloc.size_kb
            elif 'malloced' in alloc.name and 'non' not in alloc.name:
                nt.other_malloced_kb += alloc.size_kb
            elif 'nonmalloced' in alloc.name:
                nt.other_nonmalloced_kb += alloc.size_kb

        nt.tracked_total_kb = nt.bitmap_kb + nt.other_malloced_kb + nt.other_nonmalloced_kb

        # 未追踪部分
        nt.untracked_kb = nt.native_heap_pss_kb - nt.tracked_total_kb
        if nt.native_heap_pss_kb > 0:
            nt.untracked_percent = (nt.untracked_kb / nt.native_heap_pss_kb) * 100

        # 分析结论
        if nt.untracked_kb > 10 * 1024:  # > 10MB
            nt.tracking_notes.append(
                f"发现 {nt.untracked_kb/1024:.1f} MB ({nt.untracked_percent:.1f}%) 未追踪的 Native 内存"
            )
            nt.tracking_notes.append(
                "可能来源: C/C++ 库分配、JNI 分配、第三方 SDK"
            )
        else:
            nt.tracking_notes.append(
                f"Native 内存追踪良好，{100-nt.untracked_percent:.1f}% 可追踪"
            )

    def _analyze_hprof(self, result: PanoramaResult):
        """HPROF 堆分析"""
        if not self.hprof_data:
            return

        hs = result.hprof_summary
        hs.total_instances = self.hprof_data.get('total_instances', 0)
        hs.total_arrays = self.hprof_data.get('total_arrays', 0)
        hs.total_memory_mb = self.hprof_data.get('total_memory_mb', 0)
        hs.instance_size_mb = self.hprof_data.get('instance_size_mb', 0)
        hs.array_size_mb = self.hprof_data.get('array_size_mb', 0)
        hs.bitmap_count = self.hprof_data.get('bitmap_count', 0)
        hs.bitmap_size_mb = self.hprof_data.get('bitmap_size_mb', 0)
        hs.top_classes = self.hprof_data.get('top_classes', [])

        # 分析结论
        if hs.total_memory_mb > 0:
            hs.hprof_notes.append(
                f"Java 堆共 {hs.total_instances:,} 个实例，{hs.total_arrays:,} 个数组"
            )
            hs.hprof_notes.append(
                f"总内存 {hs.total_memory_mb:.2f} MB (实例 {hs.instance_size_mb:.2f} MB + 数组 {hs.array_size_mb:.2f} MB)"
            )

        # Bitmap 关联
        bc = result.bitmap_correlation
        if hs.bitmap_count > 0 and bc.meminfo_count > 0:
            if hs.bitmap_count != bc.meminfo_count:
                hs.hprof_notes.append(
                    f"Bitmap 统计: HPROF {hs.bitmap_count} 个 vs meminfo {bc.meminfo_count} 个"
                )
            else:
                hs.hprof_notes.append(
                    f"Bitmap 统计一致: {hs.bitmap_count} 个"
                )

    def _analyze_system_memory(self, result: PanoramaResult):
        """系统内存上下文分析"""
        if not self.proc_meminfo_data:
            return

        sm = result.system_memory
        pm = self.proc_meminfo_data

        sm.total_mb = pm.mem_total_mb
        sm.available_mb = pm.mem_available_mb
        sm.used_mb = pm.mem_used_mb
        sm.available_percent = pm.available_percent
        sm.cached_mb = pm.cached_kb / 1024
        sm.buffers_mb = pm.buffers_kb / 1024
        sm.swap_total_mb = pm.swap_total_kb / 1024
        sm.swap_used_mb = pm.swap_used_kb / 1024
        sm.swap_used_percent = pm.swap_used_percent
        sm.ion_heap_mb = pm.ion_heap_kb / 1024
        sm.pressure_level = pm.memory_pressure
        sm.pressure_level_cn = pm.memory_pressure_cn

        # 分析结论
        sm.system_notes.append(
            f"系统可用内存 {sm.available_mb:.0f} MB ({sm.available_percent:.1f}%)"
        )

        if sm.pressure_level in ['HIGH', 'CRITICAL']:
            sm.system_notes.append(
                f"内存压力较高，可能影响应用性能"
            )

        if sm.swap_used_percent > 50:
            sm.system_notes.append(
                f"Swap 使用率 {sm.swap_used_percent:.1f}%，系统内存紧张"
            )

        if sm.ion_heap_mb > 100:
            sm.system_notes.append(
                f"ION 内存 {sm.ion_heap_mb:.0f} MB，GPU/Camera 内存占用较大"
            )

        # 计算进程占系统内存比例
        if result.total_pss_mb > 0 and sm.total_mb > 0:
            app_percent = (result.total_pss_mb / sm.total_mb) * 100
            if app_percent > 10:
                sm.system_notes.append(
                    f"本进程占系统内存 {app_percent:.1f}%"
                )

    def _analyze_dmabuf(self, result: PanoramaResult):
        """DMA-BUF 内存分析"""
        if not self.dmabuf_data:
            return

        dc = result.dmabuf_context
        db = self.dmabuf_data

        dc.total_mb = db.total_mb
        dc.total_count = db.total_count

        # 分类统计
        dc.gpu_mb = db.gpu.total_mb
        dc.gpu_count = db.gpu.count
        dc.display_mb = db.display.total_mb
        dc.display_count = db.display.count
        dc.camera_mb = db.camera.total_mb
        dc.camera_count = db.camera.count
        dc.video_mb = db.video.total_mb
        dc.video_count = db.video.count
        dc.audio_mb = db.audio.total_mb
        dc.audio_count = db.audio.count
        dc.other_mb = db.other.total_mb
        dc.other_count = db.other.count

        # 分析结论
        dc.dmabuf_notes.append(
            f"总 DMA-BUF: {dc.total_mb:.1f} MB ({dc.total_count} buffers)"
        )

        # 主要占用分析
        categories = []
        if dc.gpu_mb > 0:
            categories.append(f"GPU {dc.gpu_mb:.1f} MB")
        if dc.display_mb > 0:
            categories.append(f"Display {dc.display_mb:.1f} MB")
        if dc.camera_mb > 0:
            categories.append(f"Camera {dc.camera_mb:.1f} MB")
        if dc.video_mb > 0:
            categories.append(f"Video {dc.video_mb:.1f} MB")
        if dc.audio_mb > 0:
            categories.append(f"Audio {dc.audio_mb:.1f} MB")

        if categories:
            dc.dmabuf_notes.append(
                f"主要占用: {', '.join(categories)}"
            )

            # 与 Graphics 内存关联
            if result.graphics_mb > 0 and dc.total_mb > 0:
                # DMA-BUF 通常是 Graphics 内存的一部分
                if dc.gpu_mb > result.graphics_mb * 0.5:
                    dc.dmabuf_notes.append(
                        f"GPU DMA-BUF ({dc.gpu_mb:.1f} MB) 占 Graphics ({result.graphics_mb:.1f} MB) 的主要部分"
                    )

    def _analyze_zram_swap(self, result: PanoramaResult):
        """zRAM/Swap 分析"""
        if not self.zram_swap_data:
            return

        zs = result.zram_swap_context
        data = self.zram_swap_data

        # Swap 统计
        zs.swap_total_mb = data.total_swap_mb
        zs.swap_used_mb = data.used_swap_mb
        zs.swap_used_percent = data.swap_used_percent
        zs.swap_device_count = len(data.swap_devices)

        # zRAM 统计
        zs.has_zram = data.has_zram
        if data.has_zram:
            zs.zram_disk_mb = data.total_zram_disk_mb
            zs.zram_orig_mb = data.total_zram_orig_mb
            zs.zram_compr_mb = data.total_zram_compr_mb
            zs.zram_mem_used_mb = data.total_zram_mem_used_mb
            zs.zram_compression_ratio = data.overall_compression_ratio
            zs.zram_space_saving_percent = data.overall_space_saving_percent
            zs.zram_memory_saved_mb = data.memory_saved_mb
            zs.zram_device_count = len(data.zram_devices)

        # 分析结论
        if zs.swap_total_mb > 0:
            zs.zram_swap_notes.append(
                f"Swap 使用: {zs.swap_used_mb:.1f} / {zs.swap_total_mb:.1f} MB ({zs.swap_used_percent:.1f}%)"
            )

        if zs.has_zram:
            if zs.zram_compression_ratio > 0:
                zs.zram_swap_notes.append(
                    f"zRAM 压缩率: {zs.zram_compression_ratio:.2f}x (节省 {zs.zram_space_saving_percent:.1f}%)"
                )
            if zs.zram_memory_saved_mb > 100:
                zs.zram_swap_notes.append(
                    f"zRAM 节省内存: {zs.zram_memory_saved_mb:.1f} MB"
                )

        # 告警
        if zs.swap_used_percent > 80:
            zs.zram_swap_notes.append(
                "⚠️ Swap 使用率较高 (>80%)，系统可能存在内存压力"
            )
        elif zs.swap_used_percent > 50:
            zs.zram_swap_notes.append(
                "⚠️ Swap 使用率中等 (>50%)，建议关注内存使用情况"
            )

        if zs.has_zram and zs.zram_compression_ratio > 0 and zs.zram_compression_ratio < 1.5:
            zs.zram_swap_notes.append(
                "⚠️ zRAM 压缩率较低 (<1.5x)，数据可能不太可压缩"
            )

    def _analyze_ui_resources(self, result: PanoramaResult):
        """UI 资源分析"""
        if self.meminfo_data:
            obj = self.meminfo_data.objects
            result.views_count = obj.views
            result.activities_count = obj.activities
            result.viewrootimpl_count = obj.view_root_impl
            result.webviews_count = obj.webviews

    def _analyze_frame_stats(self, result: PanoramaResult):
        """帧率分析"""
        if self.gfxinfo_data:
            result.janky_percent = self.gfxinfo_data.frame_stats.janky_percent
            result.p50_ms = self.gfxinfo_data.frame_stats.p50_ms
            result.p90_ms = self.gfxinfo_data.frame_stats.p90_ms

    def _detect_anomalies(self, result: PanoramaResult):
        """检测异常"""
        anomalies = result.anomalies

        # 1. 大量未追踪 Native 内存
        nt = result.native_tracking
        if nt.untracked_kb > 20 * 1024:  # > 20MB
            anomalies.append({
                'type': 'UNTRACKED_NATIVE',
                'severity': 'HIGH',
                'description': f"{nt.untracked_kb/1024:.1f} MB 未追踪的 Native 内存",
                'suggestion': '使用 malloc_debug 或 ASan 检测 Native 内存分配'
            })

        # 2. 高卡顿率
        if result.janky_percent > 10:
            anomalies.append({
                'type': 'HIGH_JANK',
                'severity': 'MEDIUM',
                'description': f"卡顿率 {result.janky_percent:.1f}% 较高",
                'suggestion': '使用 Perfetto 或 Systrace 分析卡顿原因'
            })

        # 3. 大量 Views
        if result.views_count > 500:
            anomalies.append({
                'type': 'TOO_MANY_VIEWS',
                'severity': 'MEDIUM',
                'description': f"View 数量 {result.views_count} 较多",
                'suggestion': '考虑使用 RecyclerView、ViewStub 或简化布局'
            })

        # 4. 有 WebView 但内存占用高
        if result.webviews_count > 0 and result.native_heap_mb > 100:
            anomalies.append({
                'type': 'WEBVIEW_MEMORY',
                'severity': 'INFO',
                'description': f"使用 WebView ({result.webviews_count} 个)，Native 内存 {result.native_heap_mb:.1f} MB",
                'suggestion': 'WebView 可能占用大量 Native 内存，考虑及时销毁或使用轻量替代'
            })

        # 5. 大尺寸 Bitmap
        bc = result.bitmap_correlation
        avg_bitmap_kb = bc.meminfo_total_kb / bc.meminfo_count if bc.meminfo_count > 0 else 0
        if avg_bitmap_kb > 500:  # 平均 > 500KB
            anomalies.append({
                'type': 'LARGE_BITMAPS',
                'severity': 'MEDIUM',
                'description': f"Bitmap 平均大小 {avg_bitmap_kb:.0f} KB 较大",
                'suggestion': '检查是否加载了过大的图片，考虑降采样或使用 WebP 格式'
            })

    def _generate_recommendations(self, result: PanoramaResult):
        """生成优化建议"""
        recommendations = result.recommendations

        # 基于异常生成建议
        for anomaly in result.anomalies:
            if anomaly['severity'] in ['HIGH', 'MEDIUM']:
                recommendations.append({
                    'priority': anomaly['severity'],
                    'area': anomaly['type'],
                    'suggestion': anomaly['suggestion']
                })

        # 基于 Bitmap 分析
        bc = result.bitmap_correlation
        if bc.meminfo_total_kb > 50 * 1024:  # > 50MB
            recommendations.append({
                'priority': 'HIGH',
                'area': 'BITMAP',
                'suggestion': f"Bitmap 总共 {bc.meminfo_total_kb/1024:.1f} MB，考虑使用图片加载库 (Glide/Coil) 管理缓存"
            })

        # 基于 GPU 缓存
        if bc.gpu_cache_mb > 100:
            recommendations.append({
                'priority': 'MEDIUM',
                'area': 'GPU_CACHE',
                'suggestion': f"GPU 缓存 {bc.gpu_cache_mb:.1f} MB 较大，检查是否有过多的自定义绘制"
            })

    def check_thresholds(self, result: PanoramaResult) -> List[ThresholdViolation]:
        """检查阈值违规"""
        violations = []
        tc = self.threshold_config

        if not tc:
            return violations

        # 内存阈值检查
        if tc.pss_mb is not None and result.total_pss_mb > tc.pss_mb:
            violations.append(ThresholdViolation(
                name="Total PSS",
                threshold=tc.pss_mb,
                actual=result.total_pss_mb,
                unit="MB",
                severity="ERROR"
            ))

        if tc.java_heap_mb is not None and result.java_heap_mb > tc.java_heap_mb:
            violations.append(ThresholdViolation(
                name="Java Heap",
                threshold=tc.java_heap_mb,
                actual=result.java_heap_mb,
                unit="MB",
                severity="WARNING"
            ))

        if tc.native_heap_mb is not None and result.native_heap_mb > tc.native_heap_mb:
            violations.append(ThresholdViolation(
                name="Native Heap",
                threshold=tc.native_heap_mb,
                actual=result.native_heap_mb,
                unit="MB",
                severity="WARNING"
            ))

        if tc.graphics_mb is not None and result.graphics_mb > tc.graphics_mb:
            violations.append(ThresholdViolation(
                name="Graphics",
                threshold=tc.graphics_mb,
                actual=result.graphics_mb,
                unit="MB",
                severity="WARNING"
            ))

        # 比例阈值检查
        if tc.native_untracked_percent is not None:
            untracked = result.native_tracking.untracked_percent
            if untracked > tc.native_untracked_percent:
                violations.append(ThresholdViolation(
                    name="Native 未追踪",
                    threshold=tc.native_untracked_percent,
                    actual=untracked,
                    unit="%",
                    severity="WARNING"
                ))

        if tc.janky_percent is not None and result.janky_percent > tc.janky_percent:
            violations.append(ThresholdViolation(
                name="卡顿率",
                threshold=tc.janky_percent,
                actual=result.janky_percent,
                unit="%",
                severity="WARNING"
            ))

        if tc.system_available_percent is not None:
            avail = result.system_memory.available_percent
            if avail > 0 and avail < tc.system_available_percent:
                violations.append(ThresholdViolation(
                    name="系统可用内存",
                    threshold=tc.system_available_percent,
                    actual=avail,
                    unit="%",
                    severity="ERROR"
                ))

        # 数量阈值检查
        if tc.views_count is not None and result.views_count > tc.views_count:
            violations.append(ThresholdViolation(
                name="View 数量",
                threshold=tc.views_count,
                actual=result.views_count,
                severity="WARNING"
            ))

        if tc.activities_count is not None and result.activities_count > tc.activities_count:
            violations.append(ThresholdViolation(
                name="Activity 数量",
                threshold=tc.activities_count,
                actual=result.activities_count,
                severity="WARNING"
            ))

        if tc.bitmap_count is not None:
            bitmap_count = result.bitmap_correlation.meminfo_count
            if bitmap_count > tc.bitmap_count:
                violations.append(ThresholdViolation(
                    name="Bitmap 数量",
                    threshold=tc.bitmap_count,
                    actual=bitmap_count,
                    severity="WARNING"
                ))

        # Bitmap 大小阈值
        if tc.bitmap_total_mb is not None:
            bitmap_mb = result.bitmap_correlation.meminfo_total_kb / 1024
            if bitmap_mb > tc.bitmap_total_mb:
                violations.append(ThresholdViolation(
                    name="Bitmap 总大小",
                    threshold=tc.bitmap_total_mb,
                    actual=bitmap_mb,
                    unit="MB",
                    severity="WARNING"
                ))

        return violations

    def print_report(self):
        """打印分析报告"""
        result = self.analyze()

        print("\n" + "=" * 80)
        print("=== Android 内存全景分析报告 ===")
        print("=" * 80)

        print(f"\n包名: {result.package_name}")
        print(f"PID: {result.pid}")

        # 内存概览
        print(f"\n{'─' * 40}")
        print("[ 内存概览 ]")
        print(f"{'─' * 40}")
        print(f"{'总 PSS:':<20} {result.total_pss_mb:>10.2f} MB")
        print(f"{'Java Heap:':<20} {result.java_heap_mb:>10.2f} MB")
        print(f"{'Native Heap:':<20} {result.native_heap_mb:>10.2f} MB")
        print(f"{'Graphics:':<20} {result.graphics_mb:>10.2f} MB")
        print(f"{'Code:':<20} {result.code_mb:>10.2f} MB")
        print(f"{'Stack:':<20} {result.stack_mb:>10.2f} MB")

        # 系统内存上下文
        sm = result.system_memory
        if sm.total_mb > 0:
            pressure_icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
            icon = pressure_icons.get(sm.pressure_level, "⚪")
            print(f"\n{'─' * 40}")
            print("[ 系统内存上下文 ]")
            print(f"{'─' * 40}")
            print(f"系统总内存: {sm.total_mb:.0f} MB ({sm.total_mb/1024:.2f} GB)")
            print(f"系统可用:   {sm.available_mb:.0f} MB ({sm.available_percent:.1f}%)")
            print(f"内存压力:   {icon} {sm.pressure_level_cn} ({sm.pressure_level})")
            if sm.swap_total_mb > 0:
                print(f"Swap 使用:  {sm.swap_used_mb:.0f} / {sm.swap_total_mb:.0f} MB ({sm.swap_used_percent:.1f}%)")
            if sm.ion_heap_mb > 0:
                print(f"ION 内存:   {sm.ion_heap_mb:.0f} MB")
            for note in sm.system_notes:
                print(f"  > {note}")

        # DMA-BUF 分析
        dc = result.dmabuf_context
        if dc.total_mb > 0:
            print(f"\n{'─' * 40}")
            print("[ DMA-BUF 分析 ]")
            print(f"{'─' * 40}")
            print(f"总 DMA-BUF: {dc.total_mb:.1f} MB ({dc.total_count} buffers)")
            # 分类
            if dc.gpu_count > 0:
                print(f"  GPU 图形:  {dc.gpu_mb:>8.2f} MB ({dc.gpu_count} buffers)")
            if dc.display_count > 0:
                print(f"  显示:      {dc.display_mb:>8.2f} MB ({dc.display_count} buffers)")
            if dc.camera_count > 0:
                print(f"  相机:      {dc.camera_mb:>8.2f} MB ({dc.camera_count} buffers)")
            if dc.video_count > 0:
                print(f"  视频:      {dc.video_mb:>8.2f} MB ({dc.video_count} buffers)")
            if dc.audio_count > 0:
                print(f"  音频:      {dc.audio_mb:>8.2f} MB ({dc.audio_count} buffers)")
            if dc.other_count > 0:
                print(f"  其他:      {dc.other_mb:>8.2f} MB ({dc.other_count} buffers)")
            for note in dc.dmabuf_notes:
                print(f"  > {note}")

        # zRAM/Swap 分析
        zs = result.zram_swap_context
        if zs.swap_total_mb > 0 or zs.has_zram:
            print(f"\n{'─' * 40}")
            print("[ zRAM/Swap 分析 ]")
            print(f"{'─' * 40}")
            if zs.swap_total_mb > 0:
                print(f"Swap 总量:   {zs.swap_total_mb:>10.1f} MB ({zs.swap_device_count} 个设备)")
                print(f"Swap 已用:   {zs.swap_used_mb:>10.1f} MB ({zs.swap_used_percent:.1f}%)")
            if zs.has_zram:
                print(f"zRAM 磁盘:   {zs.zram_disk_mb:>10.1f} MB ({zs.zram_device_count} 个设备)")
                print(f"原始数据:    {zs.zram_orig_mb:>10.1f} MB")
                print(f"压缩后数据:  {zs.zram_compr_mb:>10.1f} MB")
                print(f"实际内存占用:{zs.zram_mem_used_mb:>10.1f} MB")
                if zs.zram_compression_ratio > 0:
                    print(f"压缩率:      {zs.zram_compression_ratio:>10.2f}x")
                    print(f"节省空间:    {zs.zram_space_saving_percent:>10.1f}%")
                    print(f"节省内存:    {zs.zram_memory_saved_mb:>10.1f} MB")
            for note in zs.zram_swap_notes:
                print(f"  > {note}")

        # Bitmap 关联分析
        bc = result.bitmap_correlation
        if bc.meminfo_count > 0:
            print(f"\n{'─' * 40}")
            print("[ Bitmap 深度分析 ]")
            print(f"{'─' * 40}")
            print(f"Bitmap 总数: {bc.meminfo_count} 个 ({bc.meminfo_total_kb/1024:.2f} MB)")
            print(f"  - malloced (Java 管理): {bc.meminfo_malloced_count} 个 / {bc.meminfo_malloced_kb/1024:.2f} MB")
            print(f"  - nonmalloced (Native): {bc.meminfo_nonmalloced_count} 个 / {bc.meminfo_nonmalloced_kb/1024:.2f} MB")
            if bc.gpu_cache_mb > 0:
                print(f"GPU 缓存: {bc.gpu_cache_mb:.2f} MB")
            if bc.graphic_buffers_count > 0:
                print(f"GraphicBuffer: {bc.graphic_buffers_count} 个 / {bc.graphic_buffers_kb/1024:.2f} MB")
            for note in bc.correlation_notes:
                print(f"  > {note}")

        # Native 追踪
        nt = result.native_tracking
        print(f"\n{'─' * 40}")
        print("[ Native 内存追踪 ]")
        print(f"{'─' * 40}")
        print(f"Native Heap PSS: {nt.native_heap_pss_kb/1024:.2f} MB")
        print(f"  - 可追踪: {nt.tracked_total_kb/1024:.2f} MB ({100-nt.untracked_percent:.1f}%)")
        print(f"    - Bitmap: {nt.bitmap_kb/1024:.2f} MB")
        print(f"    - Other malloced: {nt.other_malloced_kb/1024:.2f} MB")
        print(f"    - Other nonmalloced: {nt.other_nonmalloced_kb/1024:.2f} MB")
        print(f"  - 未追踪: {nt.untracked_kb/1024:.2f} MB ({nt.untracked_percent:.1f}%)")
        for note in nt.tracking_notes:
            print(f"  > {note}")

        # HPROF 堆分析
        hs = result.hprof_summary
        if hs.total_memory_mb > 0:
            print(f"\n{'─' * 40}")
            print("[ Java 堆详情 (HPROF) ]")
            print(f"{'─' * 40}")
            print(f"总实例数: {hs.total_instances:,} 个")
            print(f"总数组数: {hs.total_arrays:,} 个")
            print(f"总内存: {hs.total_memory_mb:.2f} MB")
            print(f"  - 实例: {hs.instance_size_mb:.2f} MB")
            print(f"  - 数组: {hs.array_size_mb:.2f} MB")
            if hs.bitmap_count > 0:
                print(f"Bitmap: {hs.bitmap_count} 个 / {hs.bitmap_size_mb:.2f} MB")
            if hs.top_classes:
                print("TOP 类:")
                for i, cls in enumerate(hs.top_classes[:5], 1):
                    print(f"  {i}. {cls['name']}: {cls['size_mb']:.2f} MB ({cls['count']:,} 个)")
            for note in hs.hprof_notes:
                print(f"  > {note}")

        # UI 资源
        print(f"\n{'─' * 40}")
        print("[ UI 资源 ]")
        print(f"{'─' * 40}")
        print(f"Views: {result.views_count} | Activities: {result.activities_count} | ViewRootImpl: {result.viewrootimpl_count} | WebViews: {result.webviews_count}")

        # 帧率
        if result.janky_percent > 0:
            print(f"\n{'─' * 40}")
            print("[ 帧率统计 ]")
            print(f"{'─' * 40}")
            jank_icon = "!" if result.janky_percent > 10 else ""
            print(f"卡顿率: {result.janky_percent:.2f}% {jank_icon}")
            print(f"帧延迟: p50={result.p50_ms}ms | p90={result.p90_ms}ms")

        # 异常
        if result.anomalies:
            print(f"\n{'─' * 40}")
            print("[ 检测到的异常 ]")
            print(f"{'─' * 40}")
            severity_icons = {'HIGH': '!!', 'MEDIUM': '!', 'INFO': 'i', 'LOW': '-'}
            for anomaly in result.anomalies:
                icon = severity_icons.get(anomaly['severity'], ' ')
                print(f"[{icon}] {anomaly['type']}: {anomaly['description']}")
                print(f"    -> {anomaly['suggestion']}")

        # 优化建议
        if result.recommendations:
            print(f"\n{'─' * 40}")
            print("[ 优化建议 ]")
            print(f"{'─' * 40}")
            for rec in result.recommendations:
                priority = rec['priority']
                icon = '!!' if priority == 'HIGH' else ('!' if priority == 'MEDIUM' else '-')
                print(f"[{icon}] [{rec['area']}] {rec['suggestion']}")

        # 阈值检查
        violations = self.check_thresholds(result)
        if violations:
            print(f"\n{'─' * 40}")
            print("[ 阈值告警 ]")
            print(f"{'─' * 40}")
            for v in violations:
                icon = "!!" if v.severity == "ERROR" else "!"
                print(f"[{icon}] {v}")
            print(f"\n总计 {len(violations)} 个阈值违规")

        print("\n" + "=" * 80)

        return violations

    def to_json(self, indent=2) -> str:
        """将分析结果转换为 JSON 格式"""
        result = self.analyze()

        # Convert dataclass to dict
        data = {
            'timestamp': datetime.now().isoformat(),
            'package_name': result.package_name,
            'pid': result.pid,
            'memory_overview': {
                'total_pss_mb': round(result.total_pss_mb, 2),
                'java_heap_mb': round(result.java_heap_mb, 2),
                'native_heap_mb': round(result.native_heap_mb, 2),
                'graphics_mb': round(result.graphics_mb, 2),
                'code_mb': round(result.code_mb, 2),
                'stack_mb': round(result.stack_mb, 2),
            },
            'bitmap_correlation': {
                'total_count': result.bitmap_correlation.meminfo_count,
                'total_mb': round(result.bitmap_correlation.meminfo_total_kb / 1024, 2),
                'malloced_count': result.bitmap_correlation.meminfo_malloced_count,
                'malloced_mb': round(result.bitmap_correlation.meminfo_malloced_kb / 1024, 2),
                'nonmalloced_count': result.bitmap_correlation.meminfo_nonmalloced_count,
                'nonmalloced_mb': round(result.bitmap_correlation.meminfo_nonmalloced_kb / 1024, 2),
                'gpu_cache_mb': round(result.bitmap_correlation.gpu_cache_mb, 2),
                'graphic_buffers_count': result.bitmap_correlation.graphic_buffers_count,
                'graphic_buffers_mb': round(result.bitmap_correlation.graphic_buffers_kb / 1024, 2),
            },
            'native_tracking': {
                'native_heap_pss_mb': round(result.native_tracking.native_heap_pss_kb / 1024, 2),
                'tracked_mb': round(result.native_tracking.tracked_total_kb / 1024, 2),
                'tracked_percent': round(100 - result.native_tracking.untracked_percent, 1),
                'untracked_mb': round(result.native_tracking.untracked_kb / 1024, 2),
                'untracked_percent': round(result.native_tracking.untracked_percent, 1),
            },
            'hprof_summary': {
                'total_instances': result.hprof_summary.total_instances,
                'total_arrays': result.hprof_summary.total_arrays,
                'total_memory_mb': result.hprof_summary.total_memory_mb,
                'instance_size_mb': result.hprof_summary.instance_size_mb,
                'array_size_mb': result.hprof_summary.array_size_mb,
                'bitmap_count': result.hprof_summary.bitmap_count,
                'bitmap_size_mb': result.hprof_summary.bitmap_size_mb,
                'top_classes': result.hprof_summary.top_classes,
            } if result.hprof_summary.total_memory_mb > 0 else None,
            'system_memory': {
                'total_mb': round(result.system_memory.total_mb, 1),
                'available_mb': round(result.system_memory.available_mb, 1),
                'available_percent': round(result.system_memory.available_percent, 1),
                'used_mb': round(result.system_memory.used_mb, 1),
                'cached_mb': round(result.system_memory.cached_mb, 1),
                'swap_total_mb': round(result.system_memory.swap_total_mb, 1),
                'swap_used_mb': round(result.system_memory.swap_used_mb, 1),
                'swap_used_percent': round(result.system_memory.swap_used_percent, 1),
                'ion_heap_mb': round(result.system_memory.ion_heap_mb, 1),
                'pressure_level': result.system_memory.pressure_level,
                'pressure_level_cn': result.system_memory.pressure_level_cn,
            } if result.system_memory.total_mb > 0 else None,
            'dmabuf_context': {
                'total_mb': round(result.dmabuf_context.total_mb, 2),
                'total_count': result.dmabuf_context.total_count,
                'categories': {
                    'gpu': {'mb': round(result.dmabuf_context.gpu_mb, 2), 'count': result.dmabuf_context.gpu_count},
                    'display': {'mb': round(result.dmabuf_context.display_mb, 2), 'count': result.dmabuf_context.display_count},
                    'camera': {'mb': round(result.dmabuf_context.camera_mb, 2), 'count': result.dmabuf_context.camera_count},
                    'video': {'mb': round(result.dmabuf_context.video_mb, 2), 'count': result.dmabuf_context.video_count},
                    'audio': {'mb': round(result.dmabuf_context.audio_mb, 2), 'count': result.dmabuf_context.audio_count},
                    'other': {'mb': round(result.dmabuf_context.other_mb, 2), 'count': result.dmabuf_context.other_count},
                },
            } if result.dmabuf_context.total_mb > 0 else None,
            'zram_swap': {
                'swap': {
                    'total_mb': round(result.zram_swap_context.swap_total_mb, 1),
                    'used_mb': round(result.zram_swap_context.swap_used_mb, 1),
                    'used_percent': round(result.zram_swap_context.swap_used_percent, 1),
                    'device_count': result.zram_swap_context.swap_device_count,
                },
                'zram': {
                    'disk_mb': round(result.zram_swap_context.zram_disk_mb, 1),
                    'orig_mb': round(result.zram_swap_context.zram_orig_mb, 1),
                    'compr_mb': round(result.zram_swap_context.zram_compr_mb, 1),
                    'mem_used_mb': round(result.zram_swap_context.zram_mem_used_mb, 1),
                    'compression_ratio': round(result.zram_swap_context.zram_compression_ratio, 2),
                    'space_saving_percent': round(result.zram_swap_context.zram_space_saving_percent, 1),
                    'memory_saved_mb': round(result.zram_swap_context.zram_memory_saved_mb, 1),
                    'device_count': result.zram_swap_context.zram_device_count,
                } if result.zram_swap_context.has_zram else None,
            } if result.zram_swap_context.swap_total_mb > 0 or result.zram_swap_context.has_zram else None,
            'ui_resources': {
                'views': result.views_count,
                'activities': result.activities_count,
                'viewrootimpl': result.viewrootimpl_count,
                'webviews': result.webviews_count,
            },
            'frame_stats': {
                'janky_percent': round(result.janky_percent, 2),
                'p50_ms': result.p50_ms,
                'p90_ms': result.p90_ms,
            },
            'anomalies': result.anomalies,
            'recommendations': result.recommendations,
        }

        return json.dumps(data, indent=indent, ensure_ascii=False)

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式的分析报告"""
        result = self.analyze()
        lines = []

        # Header
        lines.append("# Android 内存全景分析报告")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**包名**: `{result.package_name}`")
        lines.append(f"**PID**: {result.pid}")
        lines.append("")

        # Memory Overview
        lines.append("## 内存概览")
        lines.append("")
        lines.append("| 类型 | 大小 |")
        lines.append("|------|------|")
        lines.append(f"| Total PSS | {result.total_pss_mb:.2f} MB |")
        lines.append(f"| Java Heap | {result.java_heap_mb:.2f} MB |")
        lines.append(f"| Native Heap | {result.native_heap_mb:.2f} MB |")
        lines.append(f"| Graphics | {result.graphics_mb:.2f} MB |")
        lines.append(f"| Code | {result.code_mb:.2f} MB |")
        lines.append(f"| Stack | {result.stack_mb:.2f} MB |")
        lines.append("")

        # System Memory Context
        sm = result.system_memory
        if sm.total_mb > 0:
            pressure_emojis = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
            emoji = pressure_emojis.get(sm.pressure_level, "⚪")
            lines.append("## 系统内存上下文")
            lines.append("")
            lines.append("| 指标 | 数值 |")
            lines.append("|------|------|")
            lines.append(f"| 系统总内存 | {sm.total_mb:.0f} MB ({sm.total_mb/1024:.2f} GB) |")
            lines.append(f"| 系统可用 | {sm.available_mb:.0f} MB ({sm.available_percent:.1f}%) |")
            lines.append(f"| 内存压力 | {emoji} {sm.pressure_level_cn} |")
            if sm.swap_total_mb > 0:
                lines.append(f"| Swap | {sm.swap_used_mb:.0f} / {sm.swap_total_mb:.0f} MB ({sm.swap_used_percent:.1f}%) |")
            if sm.ion_heap_mb > 0:
                lines.append(f"| ION 内存 | {sm.ion_heap_mb:.0f} MB |")
            lines.append("")

        # DMA-BUF Analysis
        dc = result.dmabuf_context
        if dc.total_mb > 0:
            lines.append("## DMA-BUF 分析")
            lines.append("")
            lines.append(f"**总 DMA-BUF**: {dc.total_mb:.1f} MB ({dc.total_count} buffers)")
            lines.append("")
            lines.append("| 类型 | 大小 | 数量 |")
            lines.append("|------|------|------|")
            if dc.gpu_count > 0:
                lines.append(f"| GPU 图形 | {dc.gpu_mb:.2f} MB | {dc.gpu_count} |")
            if dc.display_count > 0:
                lines.append(f"| 显示 | {dc.display_mb:.2f} MB | {dc.display_count} |")
            if dc.camera_count > 0:
                lines.append(f"| 相机 | {dc.camera_mb:.2f} MB | {dc.camera_count} |")
            if dc.video_count > 0:
                lines.append(f"| 视频 | {dc.video_mb:.2f} MB | {dc.video_count} |")
            if dc.audio_count > 0:
                lines.append(f"| 音频 | {dc.audio_mb:.2f} MB | {dc.audio_count} |")
            if dc.other_count > 0:
                lines.append(f"| 其他 | {dc.other_mb:.2f} MB | {dc.other_count} |")
            lines.append("")

        # zRAM/Swap Analysis
        zs = result.zram_swap_context
        if zs.swap_total_mb > 0 or zs.has_zram:
            lines.append("## zRAM/Swap 分析")
            lines.append("")
            if zs.swap_total_mb > 0:
                swap_status = "🟡 中等" if zs.swap_used_percent > 50 else ("🔴 较高" if zs.swap_used_percent > 80 else "🟢 正常")
                lines.append("### Swap 使用")
                lines.append("")
                lines.append("| 指标 | 数值 |")
                lines.append("|------|------|")
                lines.append(f"| Swap 总量 | {zs.swap_total_mb:.1f} MB |")
                lines.append(f"| Swap 已用 | {zs.swap_used_mb:.1f} MB ({zs.swap_used_percent:.1f}%) |")
                lines.append(f"| 状态 | {swap_status} |")
                lines.append("")
            if zs.has_zram:
                lines.append("### zRAM 压缩")
                lines.append("")
                lines.append("| 指标 | 数值 |")
                lines.append("|------|------|")
                lines.append(f"| zRAM 磁盘大小 | {zs.zram_disk_mb:.1f} MB |")
                lines.append(f"| 原始数据 | {zs.zram_orig_mb:.1f} MB |")
                lines.append(f"| 压缩后数据 | {zs.zram_compr_mb:.1f} MB |")
                lines.append(f"| 实际内存占用 | {zs.zram_mem_used_mb:.1f} MB |")
                if zs.zram_compression_ratio > 0:
                    lines.append(f"| 压缩率 | {zs.zram_compression_ratio:.2f}x |")
                    lines.append(f"| 节省空间 | {zs.zram_space_saving_percent:.1f}% |")
                    lines.append(f"| 节省内存 | {zs.zram_memory_saved_mb:.1f} MB |")
                lines.append("")
                if zs.zram_compression_ratio > 3:
                    lines.append("> ✅ zRAM 压缩效果很好 (>3x)")
                elif zs.zram_compression_ratio < 1.5 and zs.zram_compression_ratio > 0:
                    lines.append("> ⚠️ zRAM 压缩率较低 (<1.5x)")
                lines.append("")

        # Bitmap Analysis
        bc = result.bitmap_correlation
        if bc.meminfo_count > 0:
            lines.append("## Bitmap 深度分析")
            lines.append("")
            lines.append("| 类型 | 数量 | 大小 |")
            lines.append("|------|------|------|")
            lines.append(f"| **总计** | {bc.meminfo_count} | {bc.meminfo_total_kb/1024:.2f} MB |")
            lines.append(f"| malloced (Java 管理) | {bc.meminfo_malloced_count} | {bc.meminfo_malloced_kb/1024:.2f} MB |")
            lines.append(f"| nonmalloced (Native) | {bc.meminfo_nonmalloced_count} | {bc.meminfo_nonmalloced_kb/1024:.2f} MB |")
            if bc.gpu_cache_mb > 0:
                lines.append(f"| GPU 缓存 | - | {bc.gpu_cache_mb:.2f} MB |")
            if bc.graphic_buffers_count > 0:
                lines.append(f"| GraphicBuffer | {bc.graphic_buffers_count} | {bc.graphic_buffers_kb/1024:.2f} MB |")
            lines.append("")

        # Native Tracking
        nt = result.native_tracking
        lines.append("## Native 内存追踪")
        lines.append("")
        lines.append(f"**Native Heap PSS**: {nt.native_heap_pss_kb/1024:.2f} MB")
        lines.append("")
        lines.append("| 分类 | 大小 | 占比 |")
        lines.append("|------|------|------|")
        lines.append(f"| 可追踪 | {nt.tracked_total_kb/1024:.2f} MB | {100-nt.untracked_percent:.1f}% |")
        lines.append(f"| 未追踪 | {nt.untracked_kb/1024:.2f} MB | {nt.untracked_percent:.1f}% |")
        lines.append("")

        if nt.untracked_percent > 20:
            lines.append(f"> **警告**: 未追踪的 Native 内存占比较高 ({nt.untracked_percent:.1f}%)")
            lines.append("")

        # HPROF Summary
        hs = result.hprof_summary
        if hs.total_memory_mb > 0:
            lines.append("## Java 堆详情 (HPROF)")
            lines.append("")
            lines.append("| 指标 | 数值 |")
            lines.append("|------|------|")
            lines.append(f"| 总实例数 | {hs.total_instances:,} |")
            lines.append(f"| 总数组数 | {hs.total_arrays:,} |")
            lines.append(f"| 总内存 | {hs.total_memory_mb:.2f} MB |")
            lines.append(f"| 实例内存 | {hs.instance_size_mb:.2f} MB |")
            lines.append(f"| 数组内存 | {hs.array_size_mb:.2f} MB |")
            if hs.bitmap_count > 0:
                lines.append(f"| Bitmap | {hs.bitmap_count} 个 / {hs.bitmap_size_mb:.2f} MB |")
            lines.append("")

            if hs.top_classes:
                lines.append("### TOP 类 (按内存占用)")
                lines.append("")
                lines.append("| 类名 | 数量 | 大小 |")
                lines.append("|------|------|------|")
                for cls in hs.top_classes[:5]:
                    lines.append(f"| `{cls['name']}` | {cls['count']:,} | {cls['size_mb']:.2f} MB |")
                lines.append("")

        # UI Resources
        lines.append("## UI 资源统计")
        lines.append("")
        lines.append("| 资源 | 数量 |")
        lines.append("|------|------|")
        lines.append(f"| Views | {result.views_count} |")
        lines.append(f"| Activities | {result.activities_count} |")
        lines.append(f"| ViewRootImpl | {result.viewrootimpl_count} |")
        lines.append(f"| WebViews | {result.webviews_count} |")
        lines.append("")

        # Frame Stats
        if result.janky_percent > 0:
            lines.append("## 帧率统计")
            lines.append("")
            jank_status = "**异常**" if result.janky_percent > 10 else "正常"
            lines.append(f"- **卡顿率**: {result.janky_percent:.2f}% ({jank_status})")
            lines.append(f"- **P50**: {result.p50_ms}ms")
            lines.append(f"- **P90**: {result.p90_ms}ms")
            lines.append("")

        # Anomalies
        if result.anomalies:
            lines.append("## 检测到的异常")
            lines.append("")
            severity_emojis = {'HIGH': '🔴', 'MEDIUM': '🟡', 'INFO': '🔵', 'LOW': '⚪'}
            for anomaly in result.anomalies:
                emoji = severity_emojis.get(anomaly['severity'], '⚪')
                lines.append(f"### {emoji} {anomaly['type']}")
                lines.append("")
                lines.append(f"**描述**: {anomaly['description']}")
                lines.append("")
                lines.append(f"**建议**: {anomaly['suggestion']}")
                lines.append("")

        # Recommendations
        if result.recommendations:
            lines.append("## 优化建议")
            lines.append("")
            priority_emojis = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}
            for i, rec in enumerate(result.recommendations, 1):
                emoji = priority_emojis.get(rec['priority'], '⚪')
                lines.append(f"{i}. {emoji} **[{rec['area']}]** {rec['suggestion']}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*由 Android Memory Analysis Tool 生成*")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Android 内存全景分析器",
        epilog="""
示例:
  # 分析 meminfo + gfxinfo
  python3 panorama_analyzer.py -m meminfo.txt -g gfxinfo.txt

  # 从 dump 目录分析
  python3 panorama_analyzer.py -d /tmp/com.example.app_20231225_120000

  # 输出 JSON 格式
  python3 panorama_analyzer.py -d ./dump --json -o result.json

  # 输出 Markdown 格式
  python3 panorama_analyzer.py -d ./dump --markdown -o report.md
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-m', '--meminfo', help='meminfo 文件路径')
    parser.add_argument('-g', '--gfxinfo', help='gfxinfo 文件路径')
    parser.add_argument('-H', '--hprof', help='HPROF 文件路径')
    parser.add_argument('-S', '--smaps', help='smaps 文件路径')
    parser.add_argument('-P', '--proc-meminfo', help='/proc/meminfo 文件路径')
    parser.add_argument('-D', '--dmabuf', help='DMA-BUF debug 文件路径')
    parser.add_argument('-Z', '--zram-swap', help='zRAM/Swap 数据文件路径')
    parser.add_argument('-d', '--dump-dir', help='dump 目录（自动查找文件）')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--markdown', '-md', action='store_true', help='输出 Markdown 格式')
    parser.add_argument('-o', '--output', help='输出文件路径（默认输出到 stdout）')

    # 阈值参数
    threshold_group = parser.add_argument_group('阈值告警', '设置内存阈值，超过时返回非零 exit code')
    threshold_group.add_argument('--threshold-pss', type=float, metavar='MB',
                                  help='Total PSS 阈值 (MB)')
    threshold_group.add_argument('--threshold-java-heap', type=float, metavar='MB',
                                  help='Java Heap 阈值 (MB)')
    threshold_group.add_argument('--threshold-native-heap', type=float, metavar='MB',
                                  help='Native Heap 阈值 (MB)')
    threshold_group.add_argument('--threshold-graphics', type=float, metavar='MB',
                                  help='Graphics 阈值 (MB)')
    threshold_group.add_argument('--threshold-native-untracked', type=float, metavar='%',
                                  help='Native 未追踪比例阈值 (%%)')
    threshold_group.add_argument('--threshold-janky', type=float, metavar='%',
                                  help='卡顿率阈值 (%%)')
    threshold_group.add_argument('--threshold-views', type=int,
                                  help='View 数量阈值')
    threshold_group.add_argument('--threshold-activities', type=int,
                                  help='Activity 数量阈值')
    threshold_group.add_argument('--threshold-bitmaps', type=int,
                                  help='Bitmap 数量阈值')
    threshold_group.add_argument('--threshold-bitmap-size', type=float, metavar='MB',
                                  help='Bitmap 总大小阈值 (MB)')

    args = parser.parse_args()

    meminfo_file = args.meminfo
    gfxinfo_file = args.gfxinfo
    hprof_file = args.hprof
    smaps_file = args.smaps
    proc_meminfo_file = args.proc_meminfo
    dmabuf_file = args.dmabuf
    zram_swap_file = args.zram_swap

    # 如果指定了 dump 目录，自动查找文件
    if args.dump_dir:
        if not os.path.isdir(args.dump_dir):
            print(f"错误: 目录不存在: {args.dump_dir}")
            sys.exit(1)

        meminfo_file = meminfo_file or os.path.join(args.dump_dir, 'meminfo.txt')
        gfxinfo_file = gfxinfo_file or os.path.join(args.dump_dir, 'gfxinfo.txt')
        hprof_file = hprof_file or os.path.join(args.dump_dir, 'heap.hprof')
        smaps_file = smaps_file or os.path.join(args.dump_dir, 'smaps.txt')
        proc_meminfo_file = proc_meminfo_file or os.path.join(args.dump_dir, 'proc_meminfo.txt')
        dmabuf_file = dmabuf_file or os.path.join(args.dump_dir, 'dmabuf_debug.txt')
        zram_swap_file = zram_swap_file or os.path.join(args.dump_dir, 'zram_swap.txt')

    if not meminfo_file and not gfxinfo_file:
        print("请至少提供 meminfo 或 gfxinfo 文件")
        parser.print_help()
        sys.exit(1)

    # 创建阈值配置
    threshold_config = None
    if any([
        args.threshold_pss, args.threshold_java_heap, args.threshold_native_heap,
        args.threshold_graphics, args.threshold_native_untracked, args.threshold_janky,
        args.threshold_views, args.threshold_activities, args.threshold_bitmaps,
        args.threshold_bitmap_size
    ]):
        threshold_config = ThresholdConfig(
            pss_mb=args.threshold_pss,
            java_heap_mb=args.threshold_java_heap,
            native_heap_mb=args.threshold_native_heap,
            graphics_mb=args.threshold_graphics,
            native_untracked_percent=args.threshold_native_untracked,
            janky_percent=args.threshold_janky,
            views_count=args.threshold_views,
            activities_count=args.threshold_activities,
            bitmap_count=args.threshold_bitmaps,
            bitmap_total_mb=args.threshold_bitmap_size
        )

    analyzer = PanoramaAnalyzer(
        meminfo_file=meminfo_file,
        gfxinfo_file=gfxinfo_file,
        hprof_file=hprof_file,
        smaps_file=smaps_file,
        proc_meminfo_file=proc_meminfo_file,
        dmabuf_file=dmabuf_file,
        zram_swap_file=zram_swap_file,
        threshold_config=threshold_config
    )

    violations = []

    # 根据输出格式选择输出方式
    if args.json:
        output = analyzer.to_json()
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"JSON 报告已保存到: {args.output}")
        else:
            print(output)
        # 对于 JSON 模式也需要检查阈值
        if threshold_config:
            result = analyzer.analyze()
            violations = analyzer.check_thresholds(result)
    elif args.markdown:
        output = analyzer.generate_markdown_report()
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Markdown 报告已保存到: {args.output}")
        else:
            print(output)
        # 对于 markdown 模式也需要检查阈值
        if threshold_config:
            result = analyzer.analyze()
            violations = analyzer.check_thresholds(result)
    else:
        violations = analyzer.print_report()

    # 如果有阈值违规，返回非零 exit code
    if violations:
        # ERROR 级别的违规返回 exit code 2，WARNING 返回 1
        has_error = any(v.severity == "ERROR" for v in violations)
        sys.exit(2 if has_error else 1)


if __name__ == '__main__':
    main()
