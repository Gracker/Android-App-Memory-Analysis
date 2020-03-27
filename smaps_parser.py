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

#pss_type = ["HEAP_UNKNOWN", "HEAP_DALVIK", "HEAP_NATIVE", "HEAP_DALVIK_OTHER", "HEAP_STACK", "HEAP_CURSOR", "HEAP_ASHMEM", "HEAP_GL_DEV", \
#            "HEAP_UNKNOWN_DEV", "HEAP_SO", "HEAP_JAR", "HEAP_APK", "HEAP_TTF", "HEAP_DEX", "HEAP_OAT", "HEAP_ART", "HEAP_UNKNOWN_MAP"]
pss_type = ["Unknown", "Dalvik", "Native", "Dalvik Other", "Stack", "Cursor", "Ashmem", "Gfx dev", \
            "Other dev", ".so mmap", ".jar mmap", ".apk mmap", ".ttf mmap", ".dex mmap", ".oat mmap", ".art mmap", "Other mmap"]
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
    what = 1
    if name.__contains__("[heap]"):
        what = 3
    elif name.__contains__("[anon:libc_malloc]"):
        what = 3
    elif name.__contains__("[stack"):
        what = 5
    elif name.endswith(".so"):
        what = 10
    elif name.endswith(".jar"):
        what = 11
    elif name.endswith(".apk"):
        what = 12
    elif name.endswith(".ttf"):
        what = 13
    elif name.endswith(".dex") | name.endswith(".odex") | name.endswith(".vdex"):
        what = 14
    elif name.endswith(".oat"):
        what = 15
    elif name.endswith(".art"):
        what = 16
    elif name.__contains__("/dev"):
        what = 9
        if name.__contains__("/dev/kgsl-3d0"):
            what = 8
        elif name.__contains__("/dev/ashmem/CursorWindow"):
            what = 6
        elif name.__contains__("/dev/ashmem"):
            what = 7
    elif name.__contains__("[anon:"):
        what = 1
        if name.__contains__("[anon:dalvik-alloc space") | name.__contains__("[anon:dalvik-main space") | \
            name.__contains__("[anon:dalvik-large object space") | name.__contains__("[anon:dalvik-free list large object space") | \
            name.__contains__("[anon:dalvik-non moving space") | name.__contains__("[anon:dalvik-zygote space"):
            what = 2
        elif name.__contains__("[anon:dalvik-"):
            what = 4
    elif not name.__eq__(" "):
        if name.__sizeof__() > 0:
            what = 17
    elif prewhat == 10:
        what = 10
    return what

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

        while 1:
            line2 = file.readline()
            if not line2:
                return
            tmp2 = match_pss(line2)
            tmp3 = match_swapPss(line2)
            if tmp2 or tmp3:
                if what > 0:
                    if tmp2:
                        pss = int(tmp2.group(1))
                        pss_count[what - 1] += pss
                    if tmp3:
                        pss = int(tmp3.group(1))
                        swapPss_count[what - 1] += pss
                    # print("what:%d, pss:%d" % (what, pss))
                    if pss > 0:
                        pssSum_count[what - 1] += pss
                        tmplist = type_list[what - 1]
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
