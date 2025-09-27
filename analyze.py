import argparse
import os
import subprocess
import sys

# --- Configuration ---
TOOLS_DIR = os.path.join(os.path.dirname(__file__), 'tools')
HPROF_PARSER = os.path.join(TOOLS_DIR, 'hprof_parser.py')
SMAPS_PARSER = os.path.join(TOOLS_DIR, 'smaps_parser.py')

def analyze_hprof(file_path):
    """Calls the hprof parser script."""
    if not os.path.exists(file_path):
        print(f"Error: HPROF file not found at '{file_path}'")
        sys.exit(1)
    
    print(f"--- Analyzing HPROF file: {file_path} ---")
    command = [sys.executable, HPROF_PARSER, '-f', file_path]
    subprocess.run(command, check=True)

def analyze_smaps(file_path):
    """Calls the smaps parser script."""
    if not os.path.exists(file_path):
        print(f"Error: smaps file not found at '{file_path}'")
        sys.exit(1)
        
    print(f"--- Analyzing smaps file: {file_path} ---")
    command = [sys.executable, SMAPS_PARSER, '-f', file_path]
    subprocess.run(command, check=True)

def main():
    """Main function to parse arguments and dispatch commands."""
    parser = argparse.ArgumentParser(
        description="A unified script for Android memory analysis.",
        epilog="Examples:\n"
               "  python3 analyze.py hprof demo/hprof_sample/heapdump-20250921-122155.hprof\n"
               "  python3 analyze.py smaps demo/smaps_sample/2056_smaps_file.txt",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')
    
    # HPROF command
    hprof_parser = subparsers.add_parser('hprof', help='Analyze a .hprof file.')
    hprof_parser.add_argument('file', type=str, help='Path to the .hprof file')
    
    # SMAPS command
    smaps_parser = subparsers.add_parser('smaps', help='Analyze a smaps file.')
    smaps_parser.add_argument('file', type=str, help='Path to the smaps file')
    
    args = parser.parse_args()
    
    if args.command == 'hprof':
        analyze_hprof(args.file)
    elif args.command == 'smaps':
        analyze_smaps(args.file)
        
    print("\n--- Analysis complete. ---")

if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the analysis script: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
