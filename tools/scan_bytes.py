
import sys

def scan_bytes(filename):
    with open(filename, 'rb') as f:
        for i in range(40):
            byte = f.read(1)
            if not byte:
                break
            print(f"Offset: {i}, Byte: {byte.hex()}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scan_bytes.py <filename>")
        sys.exit(1)
    
    filename = sys.argv[1]
    scan_bytes(filename)
