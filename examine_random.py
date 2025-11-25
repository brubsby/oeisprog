import os
import random
import subprocess
import sys
import re

def get_available_sequences(base_dir):
    sequences = []
    for root, _, files in os.walk(base_dir):
        for file in files:
            if re.match(r'^A\d{6}\.py$', file):
                sequences.append(file[:-3]) # Strip .py
    return sequences

def main():
    python_progs_dir = 'pythonprogs'
    if not os.path.exists(python_progs_dir):
        print(f"Directory '{python_progs_dir}' not found.")
        return

    sequences = get_available_sequences(python_progs_dir)
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
