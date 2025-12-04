import argparse
import os
import sys
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(description="Open the extracted Python script for an OEIS sequence in your EDITOR.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    args = parser.parse_args()

    a_num = args.a_number
    if not re.match(r'^A\d{6}$', a_num):
        print(f"Invalid A-number format: {a_num}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    bucket = a_num[:4]
    file_path = os.path.join('pythonprogs', bucket, f"{a_num}.py")
    
    # Resolve to absolute path to be safe
    abs_path = os.path.abspath(file_path)

#    if not os.path.exists(abs_path):
#        print(f"Error: File not found at {abs_path}", file=sys.stderr)
#        print("Run 'examine_sequence.py' first or check the A-number.", file=sys.stderr)
#        sys.exit(1)

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
