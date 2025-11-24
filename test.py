import argparse
import os
import re
import time
import sys

def load_oeis_data(a_num):
    """
    Locates and parses the OEIS sequence data for the given A-number.
    Returns (offset, terms_list).
    """
    if not re.match(r'^A\d{6}$', a_num):
        return None, None

    bucket = a_num[:4]
    base_oeis_path = os.path.join('..', 'oeisdata', 'seq')
    seq_file_path = os.path.join(base_oeis_path, bucket, f"{a_num}.seq")

    if not os.path.exists(seq_file_path):
        return None, None
        
    terms = []
    offset = 0
    
    try:
        with open(seq_file_path, 'r') as f:
            lines = f.readlines()
            
        term_lines = []
        for line in lines:
            if line.startswith(f'%O {a_num}'):
                parts = line.split()
                if len(parts) >= 3:
                    offset_str = parts[2].split(',')[0]
                    try:
                        offset = int(offset_str)
                    except ValueError:
                        pass
            elif line.startswith(f'%S {a_num}') or \
                 line.startswith(f'%T {a_num}') or \
                 line.startswith(f'%U {a_num}'):
                parts = line.split()
                if len(parts) >= 3:
                    term_chunk = parts[2].strip()
                    term_lines.append(term_chunk)
        
        full_str = "".join(term_lines)
        terms = [int(x) for x in full_str.split(',') if x.strip()]
        
    except Exception:
        return None, None
        
    return offset, terms

class StubSequence:
    def __init__(self, name):
        self.name = name
    def __call__(self, *args, **kwargs):
        return 0 
    def __repr__(self):
        return f"<Stub {self.name}>"

def test_file(a_num):
    bucket = a_num[:4]
    file_path = os.path.join('pythonprogs', bucket, f"{a_num}.py")
    file_path = os.path.abspath(file_path)

    report_messages = []

    if not os.path.exists(file_path):
        report_messages.append(f"File not found for {a_num}: {file_path}")
        return report_messages

    report_messages.append(f"Testing {a_num} ({file_path})...")
    
    offset, expected_terms = load_oeis_data(a_num)
    if expected_terms is None:
        report_messages.append(f"  [SKIP] No data found for {a_num}")
        return report_messages

    # Read code
    try:
        with open(file_path, 'r') as f:
            code = f.read()
    except Exception as e:
        report_messages.append(f"  [ERROR] Could not read file: {e}")
        return report_messages

    # Prepare context with stubs
    context = {}
    found_ids = set(re.findall(r'A\d{6}', code))
    for aid in found_ids:
        context[aid] = StubSequence(aid)

    # Execute
    try:
        exec(code, context)
    except Exception as e:
        report_messages.append(f"  [ERROR] Execution failed: {e}")
        return report_messages

    # 1. Test a(n)
    a_func = None
    if 'a' in context and callable(context['a']):
        a_func = context['a']
        func_name = 'a'
    elif a_num in context and callable(context[a_num]):
        a_func = context[a_num]
        func_name = a_num
    
    if a_func:
        func_report = f"  Function '{func_name}(n)': "
        failures = 0
        checked = 0
        limit = min(len(expected_terms), 50)
        
        try:
            for i in range(limit):
                n = offset + i
                val = a_func(n)
                if val != expected_terms[i]:
                    func_report += f"FAIL at n={n}: expected {expected_terms[i]}, got {val}"
                    failures += 1
                    break
                checked += 1
            
            if failures == 0:
                func_report += f"PASS (checked {checked} terms)"
            report_messages.append(func_report)
        except Exception as e:
            report_messages.append(f"  Function '{func_name}(n)': ERROR: {e}")
    else:
        pass

    # 2. Test first(n)
    first_func = context.get('first')
    
    if first_func and callable(first_func):
        func_report = f"  Function 'first(n)': "
        k = 10
        if len(expected_terms) >= k:
            try:
                res = first_func(k)
                if isinstance(res, list):
                    match_len = min(len(res), len(expected_terms))
                    if res[:match_len] == expected_terms[:match_len]:
                        func_report += f"PASS (checked first({k}))"
                    else:
                         func_report += f"FAIL (mismatch)"
                else:
                    func_report += f"FAIL (returned {type(res)}, expected list)"
                report_messages.append(func_report)
            except Exception as e:
                 report_messages.append(f"  Function 'first(n)': ERROR: {e}")
                 
    # 3. Test is(n)
    is_func = None
    for k, v in context.items():
        if k == 'is_seq' or k == f'is_{a_num}':
            is_func = v
            break
            
    if is_func and callable(is_func):
        func_report = f"  Function 'is(n)': "
        try:
            all_pass = True
            for x in expected_terms[:10]:
                if not is_func(x):
                    func_report += f"FAIL: is({x}) returned False (expected True)"
                    all_pass = False
                    break
            if all_pass:
                func_report += "PASS (checked known terms)"
            report_messages.append(func_report)
        except Exception as e:
            report_messages.append(f"  Function 'is(n)': ERROR: {e}")
    
    return report_messages


def main():
    parser = argparse.ArgumentParser(description="Test OEIS Python programs.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    args = parser.parse_args()
    
    # Basic validation for A-number format
    if not re.match(r'^A\d{6}$', args.a_number):
        print(f"Invalid A-number format: {args.a_number}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    messages = test_file(args.a_number)
    for msg in messages:
        print(msg)
if __name__ == "__main__":
    main()
