import os
import sys
import multiprocessing
import subprocess
import time
from datetime import datetime

# Configuration
PYTHON_PROGS_DIR = "pythonprogs"
REPORT_FILE = "test_report.txt"
FAILURES_FILE = "failures.txt"
TIMEOUT = 2.0  # Slightly higher timeout for safety
WORKERS = max(1, os.cpu_count() or 4)

def get_sequences():
    sequences = []
    for root, dirs, files in os.walk(PYTHON_PROGS_DIR):
        for file in files:
            if file.startswith("A") and file.endswith(".py"):
                # Extract A-number (filename minus extension)
                a_num = os.path.splitext(file)[0]
                # Verify format roughly
                if len(a_num) == 7 and a_num[0] == 'A':
                    sequences.append(a_num)
    return sorted(sequences)

def test_sequence(a_num):
    """
    Runs test_sequence.py for a single sequence.
    Returns (a_num, status, output_summary)
    """
    try:
        # Run the test script
        # We use the current sys.executable to ensure we use the same venv
        cmd = [sys.executable, "test_sequence.py", a_num, "--timeout", str(TIMEOUT)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 2 # Buffer for process overhead
        )
        
        output = result.stdout
        
        # Determine status
        if "ERROR" in output:
            status = "ERROR"
        elif "FAIL" in output:
            status = "FAIL"
        elif "PASS" in output:
            status = "PASS"
        elif "SKIP" in output:
            status = "SKIP"
        else:
            status = "UNKNOWN"
            
        # Create a one-line summary of the failure/error if applicable
        summary = ""
        if status != "PASS":
            for line in output.splitlines():
                if status in line:
                    summary = line.strip()
                    break
            if not summary:
                summary = output.strip().replace('\n', '; ')[:100]
        
        return (a_num, status, summary)

    except subprocess.TimeoutExpired:
        return (a_num, "TIMEOUT", f"Execution exceeded {TIMEOUT}s")
    except Exception as e:
        return (a_num, "EXEC_ERROR", str(e))

def main():
    print(f"Scanning {PYTHON_PROGS_DIR} for sequences...")
    sequences = get_sequences()
    total = len(sequences)
    print(f"Found {total} sequences.")
    print(f"Starting tests with {WORKERS} workers (timeout={TIMEOUT}s)...")
    
    start_time = time.time()
    
    # Results containers
    results = {
        "PASS": 0,
        "FAIL": 0,
        "ERROR": 0,
        "SKIP": 0,
        "TIMEOUT": 0,
        "UNKNOWN": 0,
        "EXEC_ERROR": 0
    }
    
    failed_details = []
    
    with open(REPORT_FILE, "w") as report_f, open(FAILURES_FILE, "w") as fail_f:
        report_f.write(f"Test Run: {datetime.now()}\n")
        report_f.write(f"Total Sequences: {total}\n")
        report_f.write("-" * 40 + "\n")
        
        fail_f.write(f"Failures Report: {datetime.now()}\n")
        fail_f.write("-" * 40 + "\n")
        
        with multiprocessing.Pool(processes=WORKERS) as pool:
            # Use imap_unordered for responsiveness
            for i, (a_num, status, summary) in enumerate(pool.imap_unordered(test_sequence, sequences), 1):
                # Update stats
                results[status] = results.get(status, 0) + 1
                
                # Console progress
                sys.stdout.write(f"\r[{i}/{total}] {a_num}: {status.ljust(10)}")
                sys.stdout.flush()
                
                # Log to report
                report_f.write(f"{a_num}: {status} | {summary}\n")
                
                # Log failures
                if status not in ["PASS", "SKIP"]:
                    fail_f.write(f"{a_num}: {status} | {summary}\n")
                    fail_f.flush() # Ensure partial writes are saved
                    
                # Periodic stats print
                if i % 1000 == 0:
                    report_f.flush()

    elapsed = time.time() - start_time
    print(f"\n\nDone in {elapsed:.2f} seconds.")
    print("Results:")
    for k, v in results.items():
        print(f"  {k}: {v}")
        
    print(f"\nFull report written to {REPORT_FILE}")
    print(f"Failures written to {FAILURES_FILE}")

if __name__ == "__main__":
    main()
