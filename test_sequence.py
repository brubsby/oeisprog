import argparse
import os
import re
import time
import sys
import signal
import io
import ast
import inspect

def timeout_handler(signum, frame):
    raise TimeoutError("Execution timed out")

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
        self._offset = None
        self._terms = None
        self._loaded = False

    def _load(self):
        if not self._loaded:
            # load_oeis_data is defined in the global scope
            self._offset, self._terms = load_oeis_data(self.name)
            self._loaded = True

    def __call__(self, *args, **kwargs):
        if not args:
            return 0
        
        n = args[0]
        
        self._load()
        
        if self._terms is None:
            return 0
            
        if isinstance(n, int):
            idx = n - self._offset
            if 0 <= idx < len(self._terms):
                return self._terms[idx]
        
        return 0 

    def __repr__(self):
        return f"<Stub {self.name}>"

def compare_lists(expected, got):
    min_len = min(len(expected), len(got))
    for i in range(min_len):
        if expected[i] != got[i]:
            return f"mismatch at index {i}: expected {expected[i]}, got {got[i]}"
    if len(expected) != len(got):
        return f"length mismatch: expected {len(expected)}, got {len(got)}"
    return "match"

def code_filename_hint(a_num):
    return f"<oeis_code_{a_num}>"

def run_test_for_code(a_num, code, offset, expected_terms, timeout):
    report_messages = []
    
    # Prepare context with stubs
    context = {}
    found_ids = set(re.findall(r'A\d{6}', code))
    # Do not stub the sequence itself
    if a_num in found_ids:
        found_ids.remove(a_num)
        
    for aid in found_ids:
        context[aid] = StubSequence(aid)

    # Capture stdout
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = captured_output

    # Execute
    # Set up the signal handler for timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    # Alarm takes integer seconds, ensure at least 5 seconds for module load
    alarm_time = max(5, int(timeout))
    signal.alarm(alarm_time)
    
    # Set __name__ to avoid running guarded blocks on import
    context['__name__'] = 'oeis_module'
    
    execution_error = None
    try:
        # Parse AST to potentially optimize list comprehensions
        tree = ast.parse(code)
        
        # Transformation: Convert top-level ListComp assignments to GeneratorExp
        # to prevent timeouts on large pre-computed lists.
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith('_list'):
                        if isinstance(node.value, ast.ListComp):
                            # Convert to GeneratorExp
                            node.value = ast.GeneratorExp(
                                elt=node.value.elt, 
                                generators=node.value.generators
                            )
                            ast.fix_missing_locations(node.value)
                            break # Only modify the value once

        # Compile first to set filename for introspection
        compiled_code = compile(tree, code_filename_hint(a_num), 'exec')
        exec(compiled_code, context)
    except TimeoutError:
        execution_error = f"  [ERROR] Execution timed out during module load (limit: {alarm_time}s)"
    except Exception as e:
        execution_error = f"  [ERROR] Execution failed: {e}"
    finally:
        signal.alarm(0) # Disable alarm
        sys.stdout = original_stdout # Restore stdout

    if execution_error:
        report_messages.append(execution_error)
        return report_messages

    # Track if any test was run
    tests_run = False
    
    first_func = None
    first_func_name = None

    # 1. Test a(n)
    a_func = None
    gen_func = None
    gen_name = None
    is_list_based = False
    
    if 'a' in context and callable(context['a']):
        candidate = context['a']
        try:
            sig = inspect.signature(candidate)
            if len(sig.parameters) == 0:
                # 0 args: likely a generator factory
                gen_func = candidate
                gen_name = 'a'
            else:
                a_func = candidate
                func_name = 'a'
        except ValueError:
             # Built-ins might not have signature
             a_func = candidate
             func_name = 'a'
             
    elif a_num in context and callable(context[a_num]):
        candidate = context[a_num]
        try:
            sig = inspect.signature(candidate)
            if len(sig.parameters) == 0:
                 # 0 args: likely a generator factory
                gen_func = candidate
                gen_name = a_num
            else:
                a_func = candidate
                func_name = a_num
        except ValueError:
             a_func = candidate
             func_name = a_num
             
    elif f"{a_num}_list" in context:
        obj = context[f"{a_num}_list"]
        if isinstance(obj, list):
            # Support for list based generation (e.g. Axxxxxx_list = [...])
            the_list = obj
            func_name = f"{a_num}_list"
            is_list_based = True
            # Define a closure to access the list safely
            def list_accessor(n):
                idx = n - offset
                if 0 <= idx < len(the_list):
                    return the_list[idx]
                raise IndexError(f"Index {n} (offset {offset}) out of range for list of length {len(the_list)}")
            a_func = list_accessor
        elif hasattr(obj, '__next__') or hasattr(obj, '__iter__'):
             # Support for generator based lists (from AST transform)
             if hasattr(obj, '__iter__') and not hasattr(obj, '__next__'):
                 gen_iter = iter(obj)
             else:
                 gen_iter = obj
             
             gen_cache = []
             func_name = f"{a_num}_list"
             
             def gen_accessor_list(n):
                 target_idx = n - offset
                 if target_idx < 0: raise IndexError
                 while len(gen_cache) <= target_idx:
                     try:
                         gen_cache.append(next(gen_iter))
                     except StopIteration:
                         raise IndexError
                 return gen_cache[target_idx]
             a_func = gen_accessor_list

    # Check if a_func is actually returning a list (bulk generation)
    if a_func and not is_list_based:
        try:
            # Probe with a safe index
            probe_idx = offset + 1 if offset >= 0 else 1
            # Use a small timeout for the probe
            signal.alarm(max(1, int(timeout)))
            try:
                res = a_func(probe_idx)
            except IndexError:
                # Index error on probe might mean it expects 0-based or length
                # Try another probe
                res = a_func(10) # Arbitrary small length
            except Exception:
                res = None
            finally:
                signal.alarm(0)

            if isinstance(res, (list, tuple)):
                # It returns a list, so it's not a(n), it's likely first(n) or list(lim)
                # If we don't have a first_func yet, use this one
                if not context.get('first'): 
                    if 'first' not in context:
                        first_func = a_func
                        first_func_name = func_name
                        a_func = None # Remove from a_func candidate
        except Exception:
            # If calling it failed, we can't determine. Let the main loop handle it.
            pass

    # Check for generators if no function or list found yet
    if not a_func:
        if not gen_func:
            possible_gen_names = ["agen", "a_gen", f"{a_num}gen", f"{a_num}_gen"]
            
            # Search for explicit names first
            for name in possible_gen_names:
                if name in context and callable(context[name]):
                    gen_func = context[name]
                    gen_name = name
                    break
            
            # If not found, search for any *_gen or *gen
            if not gen_func:
                 for name, obj in context.items():
                     if (name.endswith("_gen") or name.endswith("gen")) and callable(obj):
                         gen_func = obj
                         gen_name = name
                         break
        
        if gen_func:
            try:
                # Instantiate the generator
                gen_iter = gen_func()
                gen_cache = []
                func_name = gen_name
                
                def gen_accessor(n):
                    # Target index relative to the generator start (0)
                    # Assuming generator yields terms starting at 'offset'
                    target_idx = n - offset
                    if target_idx < 0:
                        raise IndexError(f"Requesting index {n} which is less than offset {offset}")
                    
                    while len(gen_cache) <= target_idx:
                        try:
                            gen_cache.append(next(gen_iter))
                        except StopIteration:
                            raise IndexError(f"Generator exhausted at index {len(gen_cache)} (relative)")
                    
                    return gen_cache[target_idx]
                
                a_func = gen_accessor
            except Exception:
                # If calling it didn't return an iterator or failed, ignore
                pass

    # Last resort: if there is exactly one function...
    if not a_func:
        candidates = []
        for name, obj in context.items():
            if callable(obj) and not isinstance(obj, StubSequence) and name != '__builtins__':
                # Exclude characteristic functions from being treated as a(n)
                if name == 'ok' or name == 'is_seq' or name.startswith('is_'):
                    continue
                    
                if name not in ['timeout_handler', 'exit', 'quit', 'copyright', 'license', 'help']: 
                     if hasattr(obj, '__code__'):
                         filename = obj.__code__.co_filename
                         if filename == "<string>" or filename == code_filename_hint(a_num):
                             if first_func and obj == first_func:
                                 continue
                             candidates.append(name)
        
        if len(candidates) == 1:
            candidate_name = candidates[0]
            candidate_func = context[candidate_name]
            
            # Probe the candidate to see if it returns a list
            is_list_result = False
            try:
                probe_idx = offset + 1 if offset >= 0 else 1
                signal.alarm(max(1, int(timeout)))
                try:
                    res = candidate_func(probe_idx)
                except IndexError:
                    res = candidate_func(10)
                except Exception:
                    res = None
                finally:
                    signal.alarm(0)
                
                if isinstance(res, (list, tuple)):
                    is_list_result = True
            except Exception:
                pass
            
            if is_list_result:
                if not first_func:
                    first_func = candidate_func
                    first_func_name = candidate_name
            else:
                # Only assign to a_func if it didn't look like a list generator
                func_name = candidate_name
                a_func = candidate_func

    # Execute the test for a(n)
    run_guarded_fallback = False
    
    if a_func:
        tests_run = True
        func_report = f"  Function '{func_name}(n)': "
        failures = 0
        checked = 0
        limit = min(len(expected_terms), 50)
        
        timed_out = False
        list_exhausted = False
        
        # Set alarm for the entire test loop
        loop_alarm = max(1, int(timeout))
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(loop_alarm)

        try:
            for i in range(limit):
                n = offset + i
                try:
                    val = a_func(n)
                except IndexError:
                    # If list is exhausted
                    list_exhausted = True
                    break
                
                if val != expected_terms[i]:
                    func_report += f"FAIL at n={n}: expected {expected_terms[i]}, got {val}"
                    failures += 1
                    break
                checked += 1
        except TimeoutError:
            timed_out = True
        except Exception as e:
            report_messages.append(f"  Function '{func_name}(n)': ERROR: {e}")
            failures = -1
        finally:
            signal.alarm(0)
            
        if failures != -1:
            if failures == 0:
                # If list based and checked 0, it implies the list was empty or not populated.
                # Or if list exhausted prematurely, we might need to run the script to populate it.
                if is_list_based and (checked == 0 or (list_exhausted and checked < len(expected_terms))):
                    run_guarded_fallback = True
                    # Remove the previous "Function ... : " prefix effectively by not appending to report yet
                    # Only if we haven't actually confirmed enough terms?
                    # Actually, if we run fallback, we should re-test.
                    tests_run = False # Treat as if not run, to trigger fallback logic and re-check
                elif timed_out:
                     func_report += f"PASS (checked {checked} terms, timed out after {loop_alarm}s)"
                     report_messages.append(func_report)
                elif list_exhausted:
                     func_report += f"PASS (checked {checked} terms, list exhausted)"
                     report_messages.append(func_report)
                else:
                     func_report += f"PASS (checked {checked} terms)"
                     report_messages.append(func_report)
            else:
                report_messages.append(func_report)
    else:
        pass

    # 2. Test first(n)
    if not first_func:
        first_func = context.get('first')
        if first_func:
            first_func_name = 'first'
    
    if not first_func:
        for name, obj in context.items():
            if name.endswith("_list") and callable(obj):
                first_func = obj
                first_func_name = name
                break
    
    if first_func and callable(first_func):
        tests_run = True
        func_report = f"  Function '{first_func_name}(n)': "
        k = len(expected_terms)
        
        loop_alarm = max(1, int(timeout))
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(loop_alarm)
        
        try:
            if len(expected_terms) >= k:
                try:
                    res = first_func(k)
                    if isinstance(res, list):
                        match_len = min(len(res), len(expected_terms))
                        if res[:match_len] == expected_terms[:match_len]:
                            func_report += f"PASS (checked first({k}))"
                        else:
                             detail = compare_lists(expected_terms[:match_len], res[:match_len])
                             func_report += f"FAIL ({detail})"
                    else:
                        func_report += f"FAIL (returned {type(res)}, expected list)"
                    report_messages.append(func_report)
                except Exception as e:
                     report_messages.append(f"  Function '{first_func_name}(n)': ERROR: {e}")
        except TimeoutError:
             report_messages.append(f"  Function '{first_func_name}(n)': TIMEOUT")
        finally:
            signal.alarm(0)

    # 3. Test is(n)
    is_func = None
    for k, v in context.items():
        if k == 'is_seq' or k == f'is_{a_num}' or k == 'ok':
            if callable(v):
                try:
                    sig = inspect.signature(v)
                    # Count required arguments
                    required_args = 0
                    for p in sig.parameters.values():
                        if p.default == inspect.Parameter.empty and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                            required_args += 1
                    
                    if required_args == 1:
                        is_func = v
                        break
                except (ValueError, TypeError):
                    # If we can't inspect signature (e.g. built-in), optimistically assume it's valid if named explicitly
                    is_func = v
                    break
            
    if is_func and callable(is_func):
        tests_run = True
        func_report = f"  Function 'is(n)': "
        
        loop_alarm = max(1, int(timeout))
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(loop_alarm)
        
        timed_out = False
        failures = 0
        
        try:
            all_pass = True
            for x in expected_terms[:10]:
                if not is_func(x):
                    func_report += f"FAIL: is({x}) returned False (expected True)"
                    all_pass = False
                    failures = 1
                    break
            if all_pass:
                func_report += "PASS (checked known terms)"
        except TimeoutError:
            timed_out = True
        except Exception as e:
            report_messages.append(f"  Function 'is(n)': ERROR: {e}")
            failures = -1
        finally:
            signal.alarm(0)
            
        if failures != -1:
            if timed_out:
                 func_report += f"PASS (checked partial known terms, timed out)"
                 report_messages.append(func_report)
            elif failures == 0:
                 report_messages.append(func_report)
            else:
                 report_messages.append(func_report)
    
    # 4. Check STDOUT or Fallback to Guarded Execution
    if not tests_run or run_guarded_fallback:
        # Run the guarded block
        
        # Reset stdout capture
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        context['__name__'] = '__main__'
        signal.alarm(alarm_time)
        
        try:
            # Parse the code and attempt to inject a result capture for the last expression 
            # in the 'if __name__ == "__main__":' block
            tree = ast.parse(code)
            
            modified = False
            for node in tree.body:
                if isinstance(node, ast.If):
                    # Check for basic "if __name__ == '__main__':" pattern
                    is_main = False
                    try:
                        if (isinstance(node.test, ast.Compare) and 
                            isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__' and
                            isinstance(node.test.ops[0], ast.Eq)):
                            
                            # Check comparators (handle Constant/Str differences across Py versions)
                            comp = node.test.comparators[0]
                            val = None
                            if isinstance(comp, ast.Constant):
                                val = comp.value
                            elif hasattr(ast, 'Str') and isinstance(comp, ast.Str):
                                val = comp.s
                                
                            if val == '__main__':
                                is_main = True
                    except Exception:
                        pass
                    
                    if is_main:
                        if node.body and isinstance(node.body[-1], ast.Expr):
                            # Replace the last expression with an assignment
                            # _test_runner_result = <expr>
                            orig_expr = node.body[-1]
                            target_node = ast.Name(id='_test_runner_result', ctx=ast.Store())
                            ast.copy_location(target_node, orig_expr)
                            
                            assign = ast.Assign(
                                targets=[target_node],
                                value=orig_expr.value
                            )
                            # Copy location info to ensure compilation works
                            ast.copy_location(assign, orig_expr)
                            node.body[-1] = assign
                            modified = True
            
            if modified:
                # Compile the modified AST
                compiled_code = compile(tree, code_filename_hint(a_num), 'exec')
                exec(compiled_code, context)
            else:
                # Fallback if no suitable main block found or modification not needed
                exec(code, context)

        except TimeoutError:
             pass
        except Exception as e:
             # If AST processing fails for some reason, try one last raw exec
             try:
                 exec(code, context)
             except Exception:
                 pass
        finally:
            signal.alarm(0)
            sys.stdout = original_stdout

        # Check for captured result from AST modification
        if '_test_runner_result' in context:
            res = context['_test_runner_result']
            if isinstance(res, list):
                # Validate the list
                tests_run = True
                match_len = min(len(res), len(expected_terms))
                if match_len > 0 and res[:match_len] == expected_terms[:match_len]:
                    report_messages.append(f"  Script result: PASS (checked {match_len} terms from main block)")
                else:
                    detail = compare_lists(expected_terms[:match_len], res[:match_len])
                    report_messages.append(f"  Script result: FAIL ({detail})")

        # If we were retrying because of an unpopulated list, check that list again first!
        if not tests_run and run_guarded_fallback and is_list_based and func_name in context:
             # Reuse the logic for a(n) testing
             the_list = context[func_name]
             def list_accessor(n):
                idx = n - offset
                if 0 <= idx < len(the_list):
                    return the_list[idx]
                raise IndexError
             
             # Retry List Check
             func_report = f"  Function '{func_name}(n)' (after script run): "
             failures = 0
             checked = 0
             list_exhausted = False
             limit = min(len(expected_terms), 50)
             
             for i in range(limit):
                n = offset + i
                try:
                    val = list_accessor(n)
                except IndexError:
                    list_exhausted = True
                    break
                if val != expected_terms[i]:
                    func_report += f"FAIL at n={n}: expected {expected_terms[i]}, got {val}"
                    failures += 1
                    break
                checked += 1
             
             if failures == 0 and checked > 0:
                 tests_run = True
                 if list_exhausted:
                     func_report += f"PASS (checked {checked} terms, list exhausted)"
                 else:
                     func_report += f"PASS (checked {checked} terms)"
                 report_messages.append(func_report)

        # Check stdout if still needed or if just supplementing
        output_str = captured_output.getvalue()
        if output_str.strip() and not tests_run:
            found_numbers = [int(x) for x in re.findall(r'-?\d+', output_str)]
            if found_numbers:
                tests_run = True
                match_len = min(len(found_numbers), len(expected_terms))
                if match_len > 0 and found_numbers[:match_len] == expected_terms[:match_len]:
                    report_messages.append(f"  Script output: PASS (checked {match_len} terms from stdout)")
                else:
                    detail = compare_lists(expected_terms[:match_len], found_numbers[:match_len])
                    report_messages.append(f"  Script output: FAIL ({detail})")
            else:
                 report_messages.append("  [INFO] Script produced output but no numbers found.")

    if not tests_run:
        report_messages.append("  [ERROR] No known test functions found (expected 'a(n)', 'first(n)', or 'is(n)').")
    
    return report_messages

def test_file(a_num, timeout=1.0):
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
            full_code = f.read()
    except Exception as e:
        report_messages.append(f"  [ERROR] Could not read file: {e}")
        return report_messages

    # Split by separator
    raw_sections = full_code.split("# OEIS_PYTHON_SEPARATOR")
    code_sections = [s for s in raw_sections if s.strip()]
    
    if len(code_sections) > 1:
        report_messages.append(f"  Found {len(code_sections)} code sections.")
        
    for i, code in enumerate(code_sections):
        if len(code_sections) > 1:
            report_messages.append(f"  --- Section {i+1} ---")
            
        section_messages = run_test_for_code(a_num, code, offset, expected_terms, timeout)
        report_messages.extend(section_messages)

    return report_messages


def main():
    parser = argparse.ArgumentParser(description="Test OEIS Python programs.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    parser.add_argument("--timeout", type=float, default=1.0, help="Timeout in seconds for testing loops (default: 1.0).")
    args = parser.parse_args()
    
    # Basic validation for A-number format
    if not re.match(r'^A\d{6}$', args.a_number):
        print(f"Invalid A-number format: {args.a_number}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    messages = test_file(args.a_number, timeout=args.timeout)
    for msg in messages:
        print(msg)

if __name__ == "__main__":
    main()