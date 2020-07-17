# Android-App-Memory-Analysis

单纯使用 Meminfo 的数据，可以看到是哪部分比较大，但是没有具体的信息也不好分析，而 smaps 中则有比较详细的数据，此脚本就是结合 smaps 和 meminfo

# 脚本使用

1. 获取对应进程的 smaps 文件 ： adb pull /proc/pid_of_app/smaps . 
2. 执行解析脚本：python /smap/smaps_parser.py -f <path_of_smaps>

# 对比

## Meminfo 数据

Meminfo 可以看到的数据

![Meminfo](pic/meminfo.png)

## Smap 数据

Smaps 包含的数据

![Smap](pic/image0.png)

## 脚本解析后的视图

![Smap](pic/image1.png)

![Smap](pic/image2.png)