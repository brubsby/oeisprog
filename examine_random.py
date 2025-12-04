import os
import random
import subprocess
import sys
import re
import argparse

def get_available_sequences(base_dir):
    sequences = set()
    for root, _, files in os.walk(base_dir):
        for file in files:
            m = re.match(r'^(A\d{6})\.py$', file)
            if m:
                sequences.add(m.group(1))
    return sequences

def get_sequences_from_stdin():
    sequences = []
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        sequences = re.findall(r'A\d{6}', content)
    return sequences

def get_all_oeis_data_sequences():
    sequences = set()
    base_dir = os.path.join('..', 'oeisdata', 'seq')
    if not os.path.exists(base_dir):
        print(f"Warning: Data directory '{base_dir}' not found.")
        return sequences

    for root, _, files in os.walk(base_dir):
        for file in files:
            m = re.match(r'^(A\d{6})\.seq$', file)
            if m:
                sequences.add(m.group(1))
    return sequences

def get_random_no_prog_sequence(python_seqs, max_attempts=5000):
    # Heuristic max
    MAX_A_NUM = 380000
    
    print(f"Searching for sequence with no OEIS program (max {max_attempts} attempts)...")
    
    for attempt in range(max_attempts):
        num = random.randint(1, MAX_A_NUM)
        a_num = f"A{num:06d}"
        
        if a_num in python_seqs:
            continue
            
        # Check if data exists
        bucket = a_num[:4]
        path = os.path.join('..', 'oeisdata', 'seq', bucket, f"{a_num}.seq")
        if not os.path.exists(path):
            continue

        # Check content for programs
        has_prog = False
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('%o') or line.startswith('%p') or line.startswith('%t'):
                        has_prog = True
                        break
        except:
            continue
            
        if not has_prog:
            print(f"Found {a_num} after {attempt+1} attempts.")
            return a_num
            
    return None

def main():
    parser = argparse.ArgumentParser(description="Pick a random OEIS sequence to examine.")
    parser.add_argument("--no-python", action="store_true", help="Pick a random sequence that does NOT have a python program locally.")
    parser.add_argument("--no-prog", action="store_true", help="Pick a random sequence that also has NO program in OEIS data.")
    parser.add_argument("--search-terms", dest="search_terms", type=str, help="Filter the chosen sequence by whether these terms all appear")
    args = parser.parse_args()

    choice = None
    filter_strings = args.search_terms.split(" ") if args.search_terms else []

    if args.no_prog:
        print("Scanning python sequences...")
        python_seqs = get_available_sequences('pythonprogs')
        choice = get_random_no_prog_sequence(python_seqs)
        if not choice:
            print("Could not find a sequence with no program after many attempts.")
            return

    elif args.no_python:
        print("Scanning available OEIS data sequences...")
        all_seqs = get_all_oeis_data_sequences()
        print(f"Found {len(all_seqs)} sequences with data.")
        
        print("Scanning python sequences...")
        python_seqs = get_available_sequences('pythonprogs')
        print(f"Found {len(python_seqs)} python sequences.")
        
        non_python_seqs = list(all_seqs - python_seqs)
        print(f"Found {len(non_python_seqs)} sequences with no python program.")
        
        if not non_python_seqs:
            print("No sequences without python program found!")
            return
            
        choice = random.choice(non_python_seqs)
    else:
        # Try getting sequences from stdin first
        sequences = get_sequences_from_stdin()
        
        if sequences:
            print(f"Found {len(sequences)} sequences from stdin.")
        else:
            # Fallback to directory walk
            python_progs_dir = 'pythonprogs'
            if not os.path.exists(python_progs_dir):
                print(f"Directory '{python_progs_dir}' not found.")
                return

            sequences = list(get_available_sequences(python_progs_dir))
            if not sequences:
                print("No extracted Python sequences found.")
                return
        
        choice = random.choice(sequences)
    
    # Call examine_sequence.py
    try:
        subprocess.run([sys.executable, 'examine_sequence.py', choice], check=False)
    except Exception as e:
        print(f"Error running examine_sequence.py: {e}")

    print(f"To re-examine this sequence:\nuv run examine_sequence.py {choice}")

if __name__ == "__main__":
    main()
