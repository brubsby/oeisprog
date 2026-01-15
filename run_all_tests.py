import random
import os
import sys
import multiprocessing
import subprocess
import time
import argparse
from datetime import datetime

# Try to import DockerWorker
try:
    from docker_manager import DockerWorker
except ImportError:
    DockerWorker = None

# Configuration
PYTHON_PROGS_DIR = "sanitized"
REPORT_FILE = "test_report.txt"
FAILURES_FILE = "failures.txt"
TIMEOUT = 1.0
WORKERS = max(1, os.cpu_count() or 4)

# Global variable for worker processes
WORKER_CONTAINER_NAME = None

def init_worker_process(container_name):
    """Initializer for pool workers to set the global container name."""
    global WORKER_CONTAINER_NAME
    WORKER_CONTAINER_NAME = container_name

def get_sequences(shuffle=True):
    sequences = []
    for root, dirs, files in os.walk(PYTHON_PROGS_DIR):
        for file in files:
            if file.startswith("A") and "_python_" in file and file.endswith(".py"):
                parts = file.split('_')
                if len(parts) >= 1:
                    a_num = parts[0]
                    if len(a_num) == 7 and a_num[0] == 'A':
                        sequences.append(a_num)
    sequences = sorted(list(set(sequences)))
    if shuffle:
        random.shuffle(sequences)
    return sequences

def test_sequence(a_num):
    """
    Runs test_sequence.py for a single sequence.
    Returns (a_num, status, output_summary)
    """
    global WORKER_CONTAINER_NAME
    
    try:
        if WORKER_CONTAINER_NAME:
            # Docker Mode
            # We use 'python3' assuming PATH is correctly set in the container to find it (host-bin or local)
            cmd = [
                "docker", "exec", 
                WORKER_CONTAINER_NAME, 
                "python3", "test_sequence.py", 
                a_num, 
                "--timeout", str(TIMEOUT)
            ]
        else:
            # Local Mode
            cmd = [sys.executable, "test_sequence.py", a_num, "--timeout", str(TIMEOUT)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            #timeout=TIMEOUT * 2 + 5
        )
        
        output = result.stdout
        
        if "ERROR" in output:
            status = "ERROR"
        elif "possible offset issue" in output:
            status = "OFFSET"
        elif "FAIL" in output:
            status = "FAIL"
        elif "PASS" in output:
            status = "PASS"
        elif "SKIP" in output:
            status = "SKIP"
        else:
            status = "UNKNOWN"
            
        summary = ""
        if status != "PASS":
            for line in output.splitlines():
                if status == "OFFSET" and "possible offset issue" in line:
                    summary = line.strip()
                    break
                elif status in line:
                    summary = line.strip()
                    break
            if not summary:
                # Capture stderr if stdout is empty/useless
                if not output.strip() and result.stderr:
                    summary = "STDERR: " + result.stderr.strip()[:100]
                else:
                    summary = output.strip().replace('\n', '; ')[:100]
        
        return (a_num, status, summary)

    except subprocess.TimeoutExpired:
        return (a_num, "TIMEOUT", f"Execution exceeded {TIMEOUT}s")
    except Exception as e:
        return (a_num, "EXEC_ERROR", str(e))

def main():
    parser = argparse.ArgumentParser(description="Run OEIS Python programs.")
    parser.add_argument("--docker", action="store_true", help="Run tests inside Docker container.")
    parser.add_argument("--timeout", type=float, default=1.0, help="Timeout per sequence.")
    parser.add_argument("--workers", type=int, default=WORKERS, help="Number of worker processes.")
    parser.add_argument("--first-failure", action="store_true", help="Stop after the first failure.")
    parser.add_argument("-r", "--random", action="store_true", help="Run tests in random order (default).")
    parser.add_argument("-s", "--sorted", dest="random", action="store_false", help="Run tests in sorted order.")
    parser.add_argument("-f", "--from", dest="start_at", help="Start tests from this sequence (e.g., A000001). Requires --sorted.")
    parser.set_defaults(random=True)
    args = parser.parse_args()

    global TIMEOUT
    TIMEOUT = args.timeout
    workers_count = args.workers
    use_random = args.random
    start_at = args.start_at

    if start_at and use_random:
        print("Error: --from can only be used with --sorted.")
        sys.exit(1)

    if args.docker and DockerWorker is None:
        print("Error: docker_manager.py not found. Cannot run in Docker mode.")
        sys.exit(1)

    print(f"Scanning {PYTHON_PROGS_DIR} for sequences...")
    sequences = get_sequences(shuffle=use_random)
    
    if start_at:
        # Validate format
        if not (len(start_at) == 7 and start_at.startswith('A') and start_at[1:].isdigit()):
            print(f"Error: Invalid sequence format '{start_at}'. Expected format like A000001.")
            sys.exit(1)
        
        original_count = len(sequences)
        sequences = [s for s in sequences if s >= start_at]
        if not sequences:
            print(f"Error: No sequences found starting from {start_at}.")
            sys.exit(1)
        print(f"Filtered to {len(sequences)} sequences (starting from {start_at}).")
    
    total = len(sequences)
    print(f"Found {total} sequences.")
    
    mode_msg = "Docker Container" if args.docker else "Local Process"
    order_msg = "random" if use_random else "sorted"
    print(f"Starting tests with {workers_count} workers ({mode_msg}, order={order_msg}, timeout={TIMEOUT}s)...")
    
    start_time = time.time()
    
    results = {k: 0 for k in ["PASS", "FAIL", "ERROR", "SKIP", "TIMEOUT", "UNKNOWN", "EXEC_ERROR", "OFFSET"]}
    
    # Manager Context
    worker_context = None
    container_name = None
    
    try:
        if args.docker:
            # Initialize the shared container
            # Using use_host_nix_store=True as requested/inferred
            worker_context = DockerWorker(use_host_nix_store=True)
            worker_context.start()
            container_name = worker_context.container_name
            print(f"Docker container started: {container_name}")

        with open(REPORT_FILE, "w") as report_f, open(FAILURES_FILE, "w") as fail_f:
            report_f.write(f"Test Run: {datetime.now()} (Mode: {mode_msg}, Order: {order_msg})\n")
            report_f.write(f"Total Sequences: {total}\n")
            report_f.write("-" * 40 + "\n")
            fail_f.write(f"Failures Report: {datetime.now()}\n")
            fail_f.write("-" * 40 + "\n")
            
            # Setup Pool with Initializer if Docker
            init_args = (container_name,) if container_name else (None,)
            
            with multiprocessing.Pool(processes=workers_count, initializer=init_worker_process, initargs=init_args) as pool:
                # Use imap for sorted (to preserve order) or imap_unordered for random
                imap_func = pool.imap_unordered if use_random else pool.imap
                
                for i, (a_num, status, summary) in enumerate(imap_func(test_sequence, sequences), 1):
                    results[status] = results.get(status, 0) + 1
                    
                    sys.stdout.write(f"\r[{i}/{total}] {a_num}: {status.ljust(10)}")
                    sys.stdout.flush()
                    
                    report_f.write(f"{a_num}: {status} | {summary}\n")
                    if status not in ["PASS", "SKIP"]:
                        fail_f.write(f"{a_num}: {status} | {summary}\n")
                        fail_f.flush()
                        
                        if args.first_failure and status != "OFFSET":
                            print(f"\nFirst failure encountered: {a_num} ({status})")
                            print(f"Summary: {summary}")
                            pool.terminate()
                            break
                        
                    if i % 1000 == 0:
                        report_f.flush()

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if worker_context:
            worker_context.stop()

    elapsed = time.time() - start_time
    print(f"\n\nDone in {elapsed:.2f} seconds.")
    print("Results:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print(f"\nFull report written to {REPORT_FILE}")

if __name__ == "__main__":
    main()
