#!/bin/bash
# Android App Memory Analysis Automation Script
# 自动化内存分析脚本

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印彩色消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    print_info "检查依赖..."
    
    # 检查ADB
    if ! command -v adb &> /dev/null; then
        print_error "ADB未找到，请安装Android SDK"
        exit 1
    fi
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3未找到"
        exit 1
    fi
    
    # 检查设备连接
    if ! adb devices | grep -q "device$"; then
        print_error "未检测到Android设备，请连接设备并启用USB调试"
        exit 1
    fi
    
    print_success "依赖检查完成"
}

# 显示帮助信息
show_help() {
    echo "Android App Memory Analysis Script"
    echo ""
    echo "用法:"
    echo "  $0 [选项] <包名或PID>"
    echo ""
    echo "选项:"
    echo "  -h, --help           显示帮助信息"
    echo "  -l, --list           列出正在运行的应用"
    echo "  -p, --pid PID        指定进程PID"
    echo "  -pkg, --package PKG  指定应用包名"
    echo "  -o, --output DIR     指定输出目录 (默认: ./output)"
    echo "  --hprof-only         仅分析HPROF"
    echo "  --smaps-only         仅分析SMAPS"
    echo "  --full              完整分析 (HPROF + SMAPS + 综合分析)"
    echo ""
    echo "示例:"
    echo "  $0 --list                           # 列出正在运行的应用"
    echo "  $0 -pkg com.example.app             # 分析指定包名应用"
    echo "  $0 -p 12345                         # 分析指定PID进程"
    echo "  $0 --full -pkg com.example.app      # 完整分析指定应用"
    echo "  $0 --hprof-only -pkg com.example.app # 仅分析Java堆"
}

# 列出正在运行的应用
list_running_apps() {
    print_info "正在运行的应用进程:"
    python3 hprof_dumper.py --list
}

# 获取PID通过包名
get_pid_by_package() {
    local package_name="$1"
    local pid=$(adb shell "ps | grep $package_name" | awk '{print $2}' | head -n1)
    
    if [ -z "$pid" ]; then
        print_error "未找到包名为 $package_name 的运行进程"
        return 1
    fi
    
    echo "$pid"
}

# dump HPROF文件
dump_hprof() {
    local target="$1"
    local output_dir="$2"
    local is_pid="$3"
    
    print_info "开始dump HPROF文件..."
    
    if [ "$is_pid" = "true" ]; then
        python3 hprof_dumper.py -p "$target" -o "$output_dir"
    else
        python3 hprof_dumper.py -pkg "$target" -o "$output_dir"
    fi
    
    if [ $? -eq 0 ]; then
        print_success "HPROF文件dump完成"
        # 查找最新的hprof文件
        latest_hprof=$(find "$output_dir" -name "*.hprof" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
        echo "$latest_hprof"
    else
        print_error "HPROF文件dump失败"
        return 1
    fi
}

# 获取SMAPS数据
get_smaps() {
    local pid="$1"
    local output_dir="$2"
    
    print_info "获取进程 $pid 的SMAPS数据..."
    
    local smaps_file="$output_dir/${pid}_smaps_file.txt"
    
    # 检查是否有root权限
    if ! adb shell "su root ls /proc/$pid/smaps" >/dev/null 2>&1; then
        print_error "无法访问 /proc/$pid/smaps，请确保设备已root并授权"
        return 1
    fi
    
    # 获取smaps数据
    adb shell "su root cat /proc/$pid/smaps" > "$smaps_file"
    
    if [ $? -eq 0 ] && [ -s "$smaps_file" ]; then
        print_success "SMAPS数据获取完成: $smaps_file"
        echo "$smaps_file"
    else
        print_error "SMAPS数据获取失败"
        return 1
    fi
}

# 分析HPROF文件
analyze_hprof() {
    local hprof_file="$1"
    local output_dir="$2"
    
    print_info "分析HPROF文件: $hprof_file"
    
    local analysis_file="$output_dir/$(basename "$hprof_file" .hprof)_hprof_analysis.txt"
    
    python3 hprof_parser.py -f "$hprof_file" -o "$analysis_file"
    
    if [ $? -eq 0 ]; then
        print_success "HPROF分析完成: $analysis_file"
        echo "$analysis_file"
    else
        print_error "HPROF分析失败"
        return 1
    fi
}

# 分析SMAPS文件
analyze_smaps() {
    local smaps_file="$1"
    local output_dir="$2"
    
    print_info "分析SMAPS文件: $smaps_file"
    
    local analysis_file="$output_dir/$(basename "$smaps_file" .txt)_smaps_analysis.txt"
    
    python3 smaps_parser.py -f "$smaps_file" -o "$analysis_file"
    
    if [ $? -eq 0 ]; then
        print_success "SMAPS分析完成: $analysis_file"
        echo "$analysis_file"
    else
        print_error "SMAPS分析失败"
        return 1
    fi
}

# 综合分析
comprehensive_analysis() {
    local hprof_file="$1"
    local smaps_file="$2"
    local output_dir="$3"
    
    print_info "开始综合内存分析..."
    
    local cmd="python3 memory_analyzer.py"
    
    if [ -n "$hprof_file" ]; then
        cmd="$cmd --hprof \"$hprof_file\""
    fi
    
    if [ -n "$smaps_file" ]; then
        cmd="$cmd --smaps \"$smaps_file\""
    fi
    
    local analysis_file="$output_dir/comprehensive_memory_analysis_$(date +%Y%m%d_%H%M%S).txt"
    cmd="$cmd --json-output \"$analysis_file\""
    
    eval "$cmd"
    
    if [ $? -eq 0 ]; then
        print_success "综合分析完成: $analysis_file"
        echo "$analysis_file"
    else
        print_error "综合分析失败"
        return 1
    fi
}

# 主函数
main() {
    local package_name=""
    local pid=""
    local output_dir="./output"
    local hprof_only=false
    local smaps_only=false
    local full_analysis=false
    local list_apps=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -l|--list)
                list_apps=true
                shift
                ;;
            -p|--pid)
                pid="$2"
                shift 2
                ;;
            -pkg|--package)
                package_name="$2"
                shift 2
                ;;
            -o|--output)
                output_dir="$2"
                shift 2
                ;;
            --hprof-only)
                hprof_only=true
                shift
                ;;
            --smaps-only)
                smaps_only=true
                shift
                ;;
            --full)
                full_analysis=true
                shift
                ;;
            *)
                # 如果没有指定选项，尝试作为包名处理
                if [ -z "$package_name" ] && [ -z "$pid" ]; then
                    package_name="$1"
                fi
                shift
                ;;
        esac
    done
    
    # 检查依赖
    check_dependencies
    
    # 处理列出应用请求
    if [ "$list_apps" = true ]; then
        list_running_apps
        exit 0
    fi
    
    # 验证输入
    if [ -z "$package_name" ] && [ -z "$pid" ]; then
        print_error "请指定包名 (-pkg) 或 PID (-p)"
        show_help
        exit 1
    fi
    
    # 创建输出目录
    mkdir -p "$output_dir"
    
    # 如果指定了包名，获取PID
    if [ -n "$package_name" ] && [ -z "$pid" ]; then
        pid=$(get_pid_by_package "$package_name")
        if [ $? -ne 0 ]; then
            exit 1
        fi
    fi
    
    print_info "开始分析进程 PID: $pid"
    
    local hprof_file=""
    local smaps_file=""
    
    # 执行分析
    if [ "$smaps_only" = false ]; then
        # dump和分析HPROF
        if [ -n "$package_name" ]; then
            hprof_file=$(dump_hprof "$package_name" "$output_dir" false)
        else
            hprof_file=$(dump_hprof "$pid" "$output_dir" true)
        fi
        
        if [ $? -eq 0 ] && [ -n "$hprof_file" ]; then
            analyze_hprof "$hprof_file" "$output_dir"
        fi
    fi
    
    if [ "$hprof_only" = false ]; then
        # 获取和分析SMAPS
        smaps_file=$(get_smaps "$pid" "$output_dir")
        
        if [ $? -eq 0 ] && [ -n "$smaps_file" ]; then
            analyze_smaps "$smaps_file" "$output_dir"
        fi
    fi
    
    # 综合分析
    if [ "$full_analysis" = true ] || ([ "$hprof_only" = false ] && [ "$smaps_only" = false ]); then
        if [ -n "$hprof_file" ] || [ -n "$smaps_file" ]; then
            comprehensive_analysis "$hprof_file" "$smaps_file" "$output_dir"
        fi
    fi
    
    print_success "内存分析完成！结果保存在: $output_dir"
    
    # 显示生成的文件
    print_info "生成的文件:"
    find "$output_dir" -name "*$(date +%Y%m%d)*" -type f | sort
}

# 执行主函数
main "$@"