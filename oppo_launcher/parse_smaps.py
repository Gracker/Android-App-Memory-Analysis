#!/usr/bin/env python
#
# Author: Craig Chi <craig10624@gmail.com>
#

import sys
import os
import getopt
from subprocess import check_output

mem_types = ["Private_Clean", "Private_Dirty", "Shared_Clean", "Shared_Dirty"]

def usage():
    print """
usage: parse_smaps.py [-p process_name] [-t memory_type] [-h] [smaps_filename]
example: parse_smaps.py /proc/12424/smaps
         parse_smaps.py -p smbd
         parse_smaps.py -p smbd -t Pss
         parse_smaps.py -p smbd -t Private (the line starts with "Private")
"""

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "p:t:ah", ["process-name=", "memory-type=", "all", "help"])
    except getopt.GetoptError as err:
        print err
        usage()
        sys.exit(2)

    ps_name = ""
    mem_type = ""
    for o, a in opts:
        if o in ("-p", "--process-name"):
            ps_name = a
        elif o in ("-t", "--memory-type"):
            mem_type = a
        else:
            usage()
            sys.exit(2)

    if (len(args) == 0 and ps_name == "") or len(args) > 1:
        usage()
        sys.exit(2)

    smaps_file = ""
    if ps_name == "":
        smaps_file = os.path.abspath(args[0])
    else:
        try:
            pid = str(check_output(["pidof", ps_name])).strip().split()[0]
        except:
            print "pidof failed or no such process[{0}]".format(ps_name)
            sys.exit(1)

        smaps_file = "/proc/" + pid + "/smaps"

    fileinfo = {}

    with open(smaps_file, 'r') as smap:
        for line in smap:
            if '-' in line:
                line_arr = line.split()
                if len(line_arr) < 6:
                    filename = "[anonymous]"
                else:
                    filename = line_arr[5].split('/').pop()

            elif mem_type == "":
                for idx, name in enumerate(mem_types):
                    if line.startswith(name):
                        if filename in fileinfo:
                            fileinfo[filename][idx] += int(line.split()[1])
                        else:
                            fileinfo[filename] = [0] * 4;
                            fileinfo[filename][idx] += int(line.split()[1])

            elif line.lower().startswith(mem_type.lower()):
                if filename in fileinfo:
                    fileinfo[filename] += int(line.split()[1])
                else:
                    fileinfo[filename] = int(line.split()[1])

    if mem_type == "":
        arr = []
        total = [0] * 4

        for k, v in fileinfo.items():
            arr.append((v, k))
            total = list(map(sum, zip(total, v)))

        arr.sort(cmp=lambda x,y: cmp(sum(y[0]), sum(x[0])))

        print "==============================================================================="
        print "{:^8}   {:^8}   {:^8}   {:^8}".format(mem_types[0].split('_')[0], mem_types[1].split('_')[0], mem_types[2].split('_')[0], mem_types[3].split('_')[0])
        print "{:^8} + {:^8} + {:^8} + {:^8} = {:^8} : library".format(mem_types[0].split('_')[1], mem_types[1].split('_')[1], mem_types[2].split('_')[1], mem_types[3].split('_')[1], "Total")
        print "==============================================================================="

        for tup in arr:
            print "{:>5} kB + {:>5} kB + {:>5} kB + {:>5} kB = {:>5} kB : {:<}".format(tup[0][0], tup[0][1], tup[0][2], tup[0][3], sum(tup[0]), tup[1])

        print "==============================================================================="
        print "{:>5} kB + {:>5} kB + {:>5} kB + {:>5} kB = {:>5} kB : Total".format(total[0], total[1], total[2], total[3], sum(total))

    else:
        arr = []
        total = 0

        for k, v in fileinfo.items():
            arr.append((v, k))
            total += v

        arr.sort(reverse=True)

        for tup in arr:
            print "{:>5} kB {:<}".format(tup[0], tup[1])

        print "====================="
        print "Total: {0} kB".format(total)

if __name__ == "__main__":
    main()