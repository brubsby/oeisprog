import argparse
import sys
import os
import time
import signal
import importlib.util

# Set a hard timeout for execution to prevent infinite loops from hanging the container
def timeout_handler(signum, frame):
    raise TimeoutError("Execution timed out")

def run_python_or_sage(filepath, a_num, offset, count, is_sage=False):
    """
    Runs Python or SageMath code.
    Assumes the code defines a function 'a(n)' or similar.
    """
    # Load the module
    spec_name = f"oeis_{a_num}"
    
    try:
        if is_sage:
            # For Sage, we might need to use sage's own loading mechanism or 
            # ensure the file is prepared as valid python if possible.
            # But sage -python running this script might not handle .sage files directly 
            # via importlib without preparation. 
            # For now, we'll assume standard python-compatible syntax or pre-prepared files.
            # Real Sage loading often involves 'load(filepath)' in a sage session.
            pass

        # We use standard import machinery
        spec = importlib.util.spec_from_file_location(spec_name, filepath)
        if not spec or not spec.loader:
            print(f"ERROR: Could not load spec from {filepath}")
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec_name] = module
        spec.loader.exec_module(module)
        
        # Find a(n)
        a_func = getattr(module, 'a', None)
        if not a_func:
            a_func = getattr(module, a_num, None)
            
        if not a_func:
            # Try finding a generator
            gen_func = getattr(module, 'agen', None)
            if gen_func:
                iter_gen = gen_func()
                # Wrap generator
                cache = []
                def wrapped_gen(n):
                    idx = n - offset
                    while len(cache) <= idx:
                        cache.append(next(iter_gen))
                    return cache[idx]
                a_func = wrapped_gen

        if not a_func:
            print(f"ERROR: No 'a(n)' function found in {filepath}")
            return

        # Generate terms
        for i in range(count):
            n = offset + i
            try:
                val = a_func(n)
                print(f"{n} {val}")
            except Exception as e:
                print(f"ERROR: computing a({n}): {e}")
                break

    except Exception as e:
        print(f"ERROR: {e}")

def run_pari(filepath, a_num, offset, count):
    """
    Runs PARI/GP code.
    This is trickier as we often need to append a print loop to the user's script.
    """
    # Read the user's script
    with open(filepath, 'r') as f:
        code = f.read()
    
    # Check if it defines a(n)
    if "a(n)" in code or "a(n, " in code or f"a(n)=" in code.replace(" ",""):
        # Append a loop to print terms
        # GP loop: for(n=offset, offset+count-1, print(n, " ", a(n)))
        end = offset + count - 1
        loop_code = f"\nfor(n={offset}, {end}, print(n, \" \", a(n))); quit();"
        
        # Run gp
        import subprocess
        # We pass the combined code via stdin
        full_code = code + loop_code
        
        try:
            # -q: quiet, -f: fast (no rcfile)
            process = subprocess.Popen(['gp', '-q', '-f'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(input=full_code)
            
            if stderr:
                print(f"STDERR: {stderr}")
            print(stdout)
            
        except Exception as e:
            print(f"ERROR: running GP: {e}")
    else:
        print("ERROR: PARI/GP script does not appear to define a(n)")


def main():
    parser = argparse.ArgumentParser(description="Sandbox Runner")
    parser.add_argument("--file", required=True, help="Path to the program file")
    parser.add_argument("--lang", required=True, help="Language (python, sage, pari, etc.)")
    parser.add_argument("--id", required=True, help="A-number (e.g. A000045)")
    parser.add_argument("--offset", type=int, default=0, help="Sequence offset")
    parser.add_argument("--count", type=int, default=10, help="Number of terms to generate")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout in seconds")

    args = parser.parse_args()

    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(args.timeout)

    try:
        if args.lang.lower() in ['python', 'py']:
            run_python_or_sage(args.file, args.id, args.offset, args.count, is_sage=False)
        elif args.lang.lower() in ['sage', 'sagemath']:
            run_python_or_sage(args.file, args.id, args.offset, args.count, is_sage=True)
        elif args.lang.lower() in ['pari', 'gp']:
            run_pari(args.file, args.id, args.offset, args.count)
        else:
            print(f"ERROR: Unsupported language {args.lang}")
            
    except TimeoutError:
        print("ERROR: Timeout")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        signal.alarm(0)

if __name__ == "__main__":
    main()
