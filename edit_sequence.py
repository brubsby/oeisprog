import argparse
import os
import sys
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(description="Open the extracted script for an OEIS sequence in your EDITOR or a REPL.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    parser.add_argument("extra_args", nargs='*', help="Language and/or index (e.g., 'python 2' or just '2' or 'mathematica').")
    parser.add_argument("--repl", action="store_true", help="Print the code and open a REPL for the language.")
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

    if args.repl:
        # Print the code
        print(f"--- Code for {target_file} ---")
        try:
            with open(abs_path, 'r') as f:
                print(f.read())
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
        print("-" * (14 + len(target_file)))

        # REPL mapping
        # Each entry is a list of args. The file path will be appended or substituted.
        repl_cmds = {
            "python": [sys.executable, "-i"],
            "pari": ["gp"],
            "mathematica": ["wolframscript", "-i", "-file"], 
            "gap": ["gap"],
            "maple": ["maple"],
            "magma": ["magma"],
            "maxima": ["maxima"],
            "sagemath": ["sage"],
            "julia": ["julia", "-i"],
            "haskell": ["ghci"],
            "scala": ["scala"],
            "axiom": ["fricas", "-nosman", "-eval", f')read "{abs_path}"'],
            "fricas": ["fricas", "-nosman", "-eval", f')read "{abs_path}"'],
            "scheme": ["guile", "-l"],
            "guile": ["guile", "-l"],
            "perl": ["perl", "-d"],    # Perl debugger
            "ruby": ["irb", "-r"],     # irb for interactive ruby
            "r": ["R", "--interactive", "--file"],
        }

        cmd_template = repl_cmds.get(lang.lower())
        if not cmd_template:
            print(f"No REPL command known for language '{lang}'. Trying to run it as a command...")
            full_cmd = [lang.lower(), abs_path]
        else:
            # If the template already contains the path (e.g. FriCAS), don't append it
            if any(abs_path in arg for arg in cmd_template):
                full_cmd = cmd_template
            else:
                full_cmd = cmd_template + [abs_path]
        
        print(f"Launching REPL: {' '.join(full_cmd)}")
        try:
            # We use subprocess.run without piping to allow full terminal interaction
            subprocess.run(full_cmd)
        except FileNotFoundError:
            print(f"Error: REPL command '{full_cmd[0]}' not found in PATH.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error launching REPL: {e}", file=sys.stderr)
            sys.exit(1)
        return

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

    # Auto-sanitize for Python
    if lang.lower() == 'python':
        print(f"Sanitizing {target_file}...")
        try:
            import extract_programs_oeis
            
            with open(abs_path, 'r') as f:
                code = f.read()
            
            sanitized_code, success = extract_programs_oeis.sanitize_code(code)
            
            if success:
                # Construct sanitized path
                # sanitized/Axxx/Axxxxxx/filename
                sanitized_dir = os.path.join('sanitized', bucket, a_num)
                if not os.path.exists(sanitized_dir):
                    os.makedirs(sanitized_dir)
                    
                sanitized_path = os.path.join(sanitized_dir, target_file)
                with open(sanitized_path, 'w') as f:
                    f.write(sanitized_code)
                print(f"  -> Written to {sanitized_path}")
            else:
                print("  [ERROR] Sanitization failed (syntax error or invalid AST).")
                
        except ImportError:
            print("Error: Could not import 'extract_programs_oeis'. Make sure it is in the same directory.")
        except Exception as e:
            print(f"Error during refresh: {e}")

if __name__ == "__main__":
    main()
