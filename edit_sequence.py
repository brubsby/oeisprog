import argparse
import os
import sys
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(description="Open the extracted script for an OEIS sequence in your EDITOR.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    parser.add_argument("extra_args", nargs='*', help="Language and/or index (e.g., 'python 2' or just '2' or 'mathematica').")
    args = parser.parse_args()

    a_num = args.a_number
    if not re.match(r'^A\d{6}$', a_num):
        print(f"Invalid A-number format: {a_num}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    lang = "python"
    index = "1"

    if len(args.extra_args) == 1:
        if args.extra_args[0].isdigit():
            index = args.extra_args[0]
        else:
            lang = args.extra_args[0]
    elif len(args.extra_args) >= 2:
        lang = args.extra_args[0]
        index = args.extra_args[1]

    bucket = a_num[:4]
    # Structure: progs/Axxx/Axxxxxx/Axxxxxx_lang_N.extension
    dir_path = os.path.join('progs', bucket, a_num)
    
    if not os.path.exists(dir_path):
        print(f"Error: Directory not found at {dir_path}", file=sys.stderr)
        print("Run 'extract_programs_oeis.py' first.")
        sys.exit(1)

    # Find the file with any extension
    prefix = f"{a_num}_{lang}_{index}."
    target_file = None
    for f in os.listdir(dir_path):
        if f.startswith(prefix):
            target_file = f
            break

    if not target_file:
        print(f"Error: No file found for {a_num}, language '{lang}', index '{index}' in {dir_path}", file=sys.stderr)
        print(f"Available files in {dir_path}:")
        for f in sorted(os.listdir(dir_path)):
            print(f"  {f}")
        sys.exit(1)

    abs_path = os.path.abspath(os.path.join(dir_path, target_file))

    editor = os.environ.get('EDITOR')
    if not editor:
        # Fallbacks
        if sys.platform == 'win32':
            editor = 'notepad'
        else:
            editor = 'nano' # or vi, but nano is friendlier default
        print(f"EDITOR environment variable not set. Defaulting to '{editor}'.")

    print(f"Opening {abs_path} in {editor}...")
    
    try:
        # Use shell=True if editor contains flags, or split simple string
        # Better to just split the editor string just in case it's "code -w"
        import shlex
        cmd = shlex.split(editor) + [abs_path]
        subprocess.call(cmd)
    except Exception as e:
        print(f"Error launching editor: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
