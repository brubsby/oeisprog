import argparse
import os
import subprocess
import sys
import re

def main():
    parser = argparse.ArgumentParser(description="Examine an OEIS sequence: data, code, and test results.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    args = parser.parse_args()

    choice = args.a_number
    python_progs_dir = 'pythonprogs'
    
    if not re.match(r'^A\d{6}$', choice):
        print(f"Invalid A-number format: {choice}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    print(f"Examining Sequence: {choice}")
    print("=" * 60)

    # 1. Print Sequence Data
    print(f"\n>>> OEIS Data (via read_sequence.py {choice})")
    print("-" * 60)
    sys.stdout.flush()
    try:
        subprocess.run([sys.executable, 'read_sequence.py', choice], check=False)
    except Exception as e:
        print(f"Error running read_sequence.py: {e}")

    # 2. Print Extracted Code
    print(f"\n>>> Extracted Python Code (pythonprogs/.../{choice}.py)")
    print("-" * 60)
    # Reconstruct path
    bucket = choice[:4]
    file_path = os.path.join(python_progs_dir, bucket, f"{choice}.py")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                print(f.read())
        except Exception as e:
            print(f"Error reading extracted file: {e}")
    else:
        print(f"Extracted file not found at {file_path}")

    # 3. Run Test
    print(f"\n>>> Test Results (via test_sequence.py {args.a_number})")
    print("-" * 60)
    
    # Use 'uv run' to execute the test script in the environment
    try:
        test_proc = subprocess.run(
            ['uv', 'run', 'test_sequence.py', args.a_number],
            capture_output=True,
            text=True
        )
        print(test_proc.stdout)
        if test_proc.stderr:
            print(test_proc.stderr)
    except Exception as e:
        print(f"Error running test_sequence.py: {e}")
    
    print("-" * 60)
    print(f"URL: https://oeis.org/{choice}")
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
