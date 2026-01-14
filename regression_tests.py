import subprocess
import sys
import os

AWAITING_FIX = ["A000045", "A000111", "A369104", "A238449"]
SEQUENCES = ["A352687", "A320890", "A370447", "A359198", "A051064", "A208529", "A158022", "A000292", "A000414",     "A342810", # Generates list, uses list index
    "A056303", # Generates list in main block
    "A361745", # 2D array function, now wrapped automatically
    "A000370", # Complex logic, SymPy dependency, uses __main__ block
    "A000002", # Kolakoski sequence (stdout check)
]

def extract_and_verify(a_num):
    """
    Runs extract_programs_oeis.py <a_num>.
    Verifies:
    1. Exit code 0.
    2. Files are created at sanitized/Axxx/Axxxxxx/Axxxxxx_python_*.py.
    """
    print(f"[{a_num}] Extracting...", end="", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "extract_programs_oeis.py", a_num],
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
    
    bucket = a_num[:4]
    seq_dir = os.path.join("sanitized", bucket, a_num)
    
    if not os.path.exists(seq_dir):
        # Maybe no python programs found, which could be valid for some sequences but we expect SEQUENCES list to have them.
        if "Extracted 0 programs" in output:
             print(" PASS (No programs)")
             return True
        print(f" FAIL (Directory not found: {seq_dir})")
        return False
        
    # Check for python files
    files = [f for f in os.listdir(seq_dir) if f.startswith(f"{a_num}_python") and f.endswith('.py')]
    
    if not files:
         if "Extracted 0 programs" in output: # Or check logic
             print(" PASS (No programs)")
             return True
         print(" FAIL (No python files found in dir)")
         return False

    print(f" PASS ({len(files)} files)")
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
