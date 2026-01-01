import argparse
import os
import sys
import re
import config

def main():
    parser = argparse.ArgumentParser(description="Read and print an OEIS sequence file.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    args = parser.parse_args()

    a_num = args.a_number
    if not re.match(r'^A\d{6}$', a_num):
        print(f"Invalid A-number format: {a_num}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    # Construct the path
    bucket = a_num[:4]
    file_path = os.path.join(config.get_oeis_data_dir(), 'seq', bucket, f"{a_num}.seq")
    
    if not os.path.exists(file_path):
        print(f"Sequence file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            print(f.read())
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()