#!/usr/bin/env python
# -*- coding:utf-8 -*-
#@Time  : 2019/6/13 上午10:55
#@Author: yangzhiting
#@File  : parse.py

import argparse
import re
from collections import Counter
import os
import subprocess

type_length = 17
pssSum_count = [0] * type_length
pss_count = [0] * type_length
swapPss_count = [0] * type_length

HEAP_UNKNOWN = 0
HEAP_DALVIK = 1
HEAP_NATIVE = 2

HEAP_DALVIK_OTHER = 3
HEAP_STACK = 4
HEAP_CURSOR = 5 
HEAP_ASHMEM = 6
HEAP_GL_DEV = 7
HEAP_UNKNOWN_DEV = 8
HEAP_SO = 9
HEAP_JAR = 10 
HEAP_APK = 11
HEAP_TTF = 12
HEAP_DEX = 13
HEAP_OAT = 14
HEAP_ART = 15
HEAP_UNKNOWN_MAP = 16
HEAP_GRAPHICS = 17
HEAP_GL = 18
HEAP_OTHER_MEMTRACK = 19

# Dalvik extra sections (heap)
HEAP_DALVIK_NORMAL = 20
HEAP_DALVIK_LARGE = 21
HEAP_DALVIK_ZYGOTE = 22
HEAP_DALVIK_NON_MOVING = 23

# Dalvik other extra sections.
HEAP_DALVIK_OTHER_LINEARALLOC = 24
HEAP_DALVIK_OTHER_ACCOUNTING = 25
HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE = 26
HEAP_DALVIK_OTHER_APP_CODE_CACHE = 27
HEAP_DALVIK_OTHER_COMPILER_METADATA = 28
HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE = 29

# Boot vdex / app dex / app vdex
HEAP_DEX_BOOT_VDEX = 30
HEAP_DEX_APP_DEX = 31
HEAP_DEX_APP_VDEX = 32

# App art, boot art.
HEAP_ART_APP = 33
HEAP_ART_BOOT = 34

_NUM_HEAP = 35
_NUM_EXCLUSIVE_HEAP = HEAP_OTHER_MEMTRACK+1
_NUM_CORE_HEAP = HEAP_NATIVE+1

#pss_type = ["HEAP_UNKNOWN", "HEAP_DALVIK", "HEAP_NATIVE", "HEAP_DALVIK_OTHER", "HEAP_STACK", "HEAP_CURSOR", "HEAP_ASHMEM", "HEAP_GL_DEV", \
#            "HEAP_UNKNOWN_DEV", "HEAP_SO", "HEAP_JAR", "HEAP_APK", "HEAP_TTF", "HEAP_DEX", "HEAP_OAT", "HEAP_ART", "HEAP_UNKNOWN_MAP" ,\
#            "HEAP_GRAPHICS","HEAP_GL","HEAP_OTHER_MEMTRACK",\
#           "HEAP_DALVIK_NORMAL,"HEAP_DALVIK_LARGE","HEAP_DALVIK_ZYGOTE","HEAP_DALVIK_NON_MOVING" ,\
#           "HEAP_DALVIK_OTHER_LINEARALLOC","HEAP_DALVIK_OTHER_ACCOUNTING","HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE","HEAP_DALVIK_OTHER_APP_CODE_CACHE","HEAP_DALVIK_OTHER_COMPILER_METADATA","HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE", \
#           "HEAP_DEX_BOOT_VDEX", "HEAP_DEX_APP_DEX","HEAP_DEX_APP_VDEX", \
#           "HEAP_ART_APP","HEAP_ART_BOOT" ]
pss_type = ["Unknown", "Dalvik", "Native", "Dalvik Other", "Stack", "Cursor", "Ashmem", "Gfx dev", \
            "Other dev", ".so mmap", ".jar mmap", ".apk mmap", ".ttf mmap", ".dex mmap", ".oat mmap", ".art mmap", "Other mmap", \
            "graphics","gl","other memtrack", \
                "dalvik normal","dalvik large","dalvik zygote","dalvik non moving" ,\
                    "dalvik other lineralloc","dalvik other accounting","dalvik other zygote code cache","dalvik other app code cache","dalvik other compiler metadata","dalvik other indirect reference table" ,\
                        "dex boot vdex","dex app dex","dex app vdex", \
                            "heap art app","heap art boot"]
type_list = []
for i in range(type_length):
    type_list.append({})

#制作提示
def help():
    parse = argparse.ArgumentParser(description="smaps parser")
    parse.add_argument('-p', '--pid', help="pid")
    parse.add_argument('-f', '--filename', help="smaps file")
    parse.add_argument('-t', '--type', help="Unknown, Dalvik, Native, Dalvik Other, Stack, Cursor, Ashmem, Gfx dev, \
            Other dev, .so mmap, .jar mmap, .apk mmap, .ttf mmap, .dex mmap, .oat mmap, .art mmap, Other mmap", default="ALL")
    parse.add_argument('-o', '--output', help="output file", default="smaps_analysis.txt")
    parse.add_argument('-s', '--simple', action="store_true", help="simple output", default=False)
    return parse.parse_args()

def match_head(line):
    return re.match(r'(\w*)-(\w*) (\S*) (\w*) (\w*):(\w*) (\w*)\s*(.+)$', line, re.I)

def match_type(name, prewhat):
    which_heap = HEAP_UNKNOWN
    sub_heap = HEAP_UNKNOWN
    is_swappable = False

    if(name.endswith(" (deleted)")):
        name = name[0 : len(name)- len(' (deleted)')]

    size = len(name)

    if name.startswith("[heap]"):
        which_heap = HEAP_NATIVE
    elif name.startswith("[anon:libc_malloc]"):
        which_heap = HEAP_NATIVE
    elif name.startswith("[anon:scudo:"):
        which_heap = HEAP_NATIVE
    elif name.startswith("[anon:GWP-ASan"):
        which_heap = HEAP_NATIVE
    elif name.startswith("[stack"):
        which_heap = HEAP_STACK
    elif name.startswith("[anon:stack_and_tls:"):
        which_heap = HEAP_STACK
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
    elif name.endswith(".odex") | (size > 4 and name.__contains__(".dex")) :
        which_heap = HEAP_DEX
        sub_heap = HEAP_DEX_APP_DEX
        is_swappable = True
    elif name.endswith(".vdex"):
        which_heap = HEAP_DEX
        # Handle system@framework@boot and system/framework/boot|apex
        if name.__contains__("@boot") | name.__contains__("/boot") | name.__contains__("/apex"):
            sub_heap = HEAP_DEX_BOOT_VDEX
        else:
            sub_heap = HEAP_DEX_APP_VDEX
        is_swappable = True
    elif name.endswith(".oat"):
        which_heap = HEAP_OAT
        is_swappable = True
    elif name.endswith(".art") | name.endswith(".art]"):
        which_heap = HEAP_ART
        # Handle system@framework@boot* and system/framework/boot|apex*
        if name.__contains__("@boot") | name.__contains__("/boot") | name.__contains__("/apex"):
            sub_heap = HEAP_ART_BOOT
        else:
            sub_heap = HEAP_ART_APP
        is_swappable = True
    elif name.startswith("/dev"):
        which_heap = HEAP_UNKNOWN_DEV
        if name.startswith("/dev/kgsl-3d0"):
            which_heap = HEAP_GL_DEV
        elif name.__contains__("/dev/ashmem/CursorWindow"):
            which_heap = HEAP_CURSOR
        elif name.startswith("/dev/ashmem/jit-zygote-cache"):
            which_heap = HEAP_DALVIK_OTHER
            sub_heap = HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE
        elif name.__contains__("/dev/ashmem"):
            which_heap = HEAP_ASHMEM
    elif name.startswith("/memfd:jit-cache"):
        which_heap = HEAP_DALVIK_OTHER
        sub_heap = HEAP_DALVIK_OTHER_APP_CODE_CACHE
    elif name.startswith("/memfd:jit-zygote-cache"):
        which_heap = HEAP_DALVIK_OTHER;
        sub_heap = HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE;
    elif name.startswith("[anon:"):
        which_heap = HEAP_UNKNOWN
        if name.startswith("[anon:dalvik-"):
            which_heap = HEAP_DALVIK_OTHER
            if name.startswith("[anon:dalvik-LinearAlloc"):
                sub_heap = HEAP_DALVIK_OTHER_LINEARALLOC
            elif name.startswith("[anon:dalvik-alloc space") | name.startswith("[anon:dalvik-main space"):
                # This is the regular Dalvik heap.
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_NORMAL
            elif name.startswith("[anon:dalvik-large object space") | name.startswith("[anon:dalvik-free list large object space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_LARGE
            elif name.startswith("[anon:dalvik-non moving space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_NON_MOVING
            elif name.startswith("[anon:dalvik-zygote space"):
                which_heap = HEAP_DALVIK
                sub_heap = HEAP_DALVIK_ZYGOTE           
            elif name.startswith("[anon:dalvik-indirect ref"):
                sub_heap = HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE
            elif name.startswith("[anon:dalvik-jit-code-cache") | name.startswith("[anon:dalvik-data-code-cache"):
                sub_heap = HEAP_DALVIK_OTHER_APP_CODE_CACHE
            elif name.startswith("[anon:dalvik-CompilerMetadata"):
                sub_heap = HEAP_DALVIK_OTHER_COMPILER_METADATA
            else:
                sub_heap = HEAP_DALVIK_OTHER_ACCOUNTING
    elif not name.__eq__(" "):
        if name.__sizeof__() > 0:
            which_heap = HEAP_UNKNOWN_MAP
    elif prewhat == 10:
        which_heap = 10
    return which_heap

def match_pss(line):
    tmp = re.match('Pss:\s+([0-9]*) kB', line, re.I)
    if tmp:
        return tmp

def match_swapPss(line):
    tmp = re.match('SwapPss:\s+([0-9]*) kB', line, re.I)
    if tmp:
        return tmp

def parse_smaps(filename):
    file = open(filename, 'r')
    line = file.readline()
    if not line:
        return
    what = 0
    prewhat = 0
    while 1:
        tmp = match_head(line)
        if tmp:
            name = tmp.group(8)
            # print("name:" + name)
            what = match_type(name, prewhat)
            # print "name = " + name + "what = " + str(what)
        while 1:
            line2 = file.readline()
            if not line2:
                return
            tmp2 = match_pss(line2)
            tmp3 = match_swapPss(line2)
            if tmp2 or tmp3:
                if what >= 0:
                    if tmp2:
                        pss = int(tmp2.group(1))
                        pss_count[what] += pss
                    if tmp3:
                        pss = int(tmp3.group(1))
                        swapPss_count[what] += pss
                    # print("what:%d, pss:%d" % (what, pss))
                    if pss > 0:
                        pssSum_count[what] += pss
                        tmplist = type_list[what]
                        if name in tmplist:
                            tmplist[name] += pss
                        else:
                            tmplist[name] = pss
            else:
                tmp3 = match_head(line2)
                if tmp3:
                    line = line2
                    prewhat = what
                    break

def print_result(args):
    if args.pid and not args.output:
            output = "%d_smaps_analysis.txt" % pid
    else:
        output = args.output
    type = args.type
    simple = args.simple
    index = -1
    if not type == "ALL":
        if type in pss_type:
            index = pss_type.index(type)
        else:
            print("Please enter a correct memory type")
            return
    output_file = open(output, 'w')
    if index == -1:
        for i,j,m,n,z in zip(pss_type, pssSum_count, pss_count, swapPss_count, type_list):
            tmp = "%s : %.3f M" % (i, float(j)/1000)
            print(tmp)
            output_file.write(tmp)
            output_file.write("\n")
            tmp = "\tpss: %.3f M" % (float(m) / 1000)
            print(tmp)
            output_file.write(tmp)
            output_file.write("\n")
            tmp = "\tswapPss: %.3f M" % (float(n) / 1000)
            print(tmp)
            output_file.write(tmp)
            output_file.write("\n")
            if not simple:
                count = Counter(z)
                for j in count.most_common():
                    tmp = "\t\t%s : %d kB" % (j[0], j[1])
                    print(tmp)
                    output_file.write(tmp)
                    output_file.write("\n")
    else:
        tmp = "%s : %.3f M" % (pss_type[index], float(pssSum_count[index]) / 1000)
        print(tmp)
        output_file.write(tmp)
        output_file.write("\n")
        tmp = "\tpss: %.3f M" % (float(pss_count[index]) / 1000)
        print(tmp)
        output_file.write(tmp)
        output_file.write("\n")
        tmp = "\tswapPss: %.3f M" % (float(swapPss_count[index]) / 1000)
        print(tmp)
        output_file.write(tmp)
        output_file.write("\n")
        if not simple:
            count = Counter(type_list[index])
            for j in count.most_common():
                tmp = "\t\t%s : %d kB" % (j[0], j[1])
                print(tmp)
                output_file.write(tmp)
                output_file.write("\n")

if __name__ == "__main__":
    args = help()
    if args.filename:
        if os.path.exists(args.filename):
            parse_smaps(args.filename)
            print_result(args)
        else:
            print("smaps is not exist")
    elif args.pid:
        if args.pid.isdigit():
            pid = int(args.pid)
            if pid > 0:
                check_cmd = "adb shell su root ls /proc/%d/smaps >> /dev/null" % int(pid)
                ret = os.system(check_cmd)
                if ret == 0:
                    cmd = "adb shell su root cat /proc/%d/smaps" % int(pid)
                    smaps_filename = "%d_smaps_file.txt" % pid
                    ret = os.popen(cmd)
                    new_file = open(smaps_filename, 'w')
                    lines = ret.readlines()
                    for line in lines:
                        new_file.write(line)
                    parse_smaps(smaps_filename)
                    print_result(args)
                else:
                    print("/proc/%d/smaps cannot be accessed" % pid)
            else:
                print("Please enter a correct pid")
        else:
            print("Please enter a correct pid")
    else:
        print("Please provide a pid or a smaps file")
