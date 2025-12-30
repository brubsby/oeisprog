import argparse
import os
import sys
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(description="Open the extracted Python script for an OEIS sequence in your EDITOR.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    parser.add_argument("index", nargs='?', default="1", help="The program index to edit (default: 1).")
    args = parser.parse_args()

    a_num = args.a_number
    if not re.match(r'^A\d{6}$', a_num):
        print(f"Invalid A-number format: {a_num}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    bucket = a_num[:4]
    # Structure: sanitized/Axxx/Axxxxxx/Axxxxxx_python_N.py
    filename = f"{a_num}_python_{args.index}.py"
    file_path = os.path.join('sanitized', bucket, a_num, filename)
    
    # Resolve to absolute path to be safe
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        print(f"Error: File not found at {abs_path}", file=sys.stderr)
        # Check if dir exists to give better error
        dir_path = os.path.dirname(abs_path)
        if os.path.exists(dir_path):
             print(f"Available files in {dir_path}:")
             for f in sorted(os.listdir(dir_path)):
                 if f.endswith('.py'):
                     print(f"  {f}")
        else:
             print("Directory does not exist. Run 'extract_programs_oeis.py' first.")
        sys.exit(1)

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
