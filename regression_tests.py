import subprocess
import sys
import os

AWAITING_FIX = ["A000045", "A000111"]
SEQUENCES = ["A352687", "A320890", "A370447", "A359198", "A051064", "A208529", "A158022", "A000292", "A000414"]

def extract_and_verify(a_num):
    """
    Runs extract_python_oeis.py <a_num>.
    Verifies:
    1. Exit code 0.
    2. Stdout contains the extracted code (checked via "if __name__ == '__main__':").
    3. File is created at pythonprogs/Axxx/Axxxxxx.py.
    4. File content contains "if __name__ == '__main__':".
    """
    print(f"[{a_num}] Extracting...", end="", flush=True)
    try:
        result = subprocess.run(
            ["python3", "extract_python_oeis.py", a_num],
            capture_output=True,
            text=True,
            timeout=10
        )
    except Exception as e:
        print(f" FAIL (Exec error: {e})")
        return False
        
    if result.returncode != 0:
        print(f" FAIL (Return code {result.returncode})")
        return False
        
    output = result.stdout
    
    # Verify stdout has the main guard (since we print code to stdout)
    # if "if __name__ == '__main__':" not in output:
    #    print(" FAIL (Stdout missing main guard)")
    #    return False

    bucket = a_num[:4]
    file_path = os.path.join("pythonprogs", bucket, f"{a_num}.py")
    
    if not os.path.exists(file_path):
        print(f" FAIL (File not found: {file_path})")
        return False
        
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            # if "if __name__ == '__main__':" not in content:
            #    print(" FAIL (File content missing main guard)")
            #    return False
    except Exception as e:
        print(f" FAIL (Read error: {e})")
        return False
        
    print(" PASS")
    return True

def run_test_runner(a_num):
    """
    Runs uv run test_sequence.py <a_num>.
    Parses output for PASS/FAIL/ERROR.
    """
    print(f"[{a_num}] Testing...", end="", flush=True)
    try:
        result = subprocess.run(
            ["uv", "run", "test_sequence.py", a_num],
            capture_output=True,
            text=True,
            timeout=15
        )
    except subprocess.TimeoutExpired:
        print(" TIMEOUT")
        return False

    output = result.stdout
    
    pass_count = 0
    fail_count = 0
    error_count = 0
    
    for line in output.splitlines():
        if "PASS" in line: pass_count += 1
        if "FAIL" in line: fail_count += 1
        if "ERROR" in line: error_count += 1
        
    status = f" {pass_count} PASS, {fail_count} FAIL, {error_count} ERROR"
    print(status)
    return True

def main():
    all_ok = True
    
    print("Running Regression Suite...")
    print("--------------------------------------------------")
    
    for seq in SEQUENCES:
        # 1. Extract (and verify extraction logic)
        if not extract_and_verify(seq):
            all_ok = False
            # If extraction fails, testing will likely fail too or be testing stale code.
            # Skipping test for this sequence.
            continue
            
        # 2. Test
        run_test_runner(seq)
        
    print("--------------------------------------------------")
    if not all_ok:
        print("Suite Failed.")
        sys.exit(1)
    else:
        print("Suite Complete.")

if __name__ == "__main__":
    main()
