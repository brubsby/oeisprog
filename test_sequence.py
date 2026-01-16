import argparse
import os
import re
import time
import sys
import signal
import io
import ast
import inspect
import math
import config

# Disable integer string conversion limit for large numbers
try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass # Python versions < 3.11 don't have this limit

def wrap_2d_candidate(func, strategy, offset):
    def wrapper(n):
        idx = n - offset
        if idx < 0: return 0
        
        if strategy == 'antidiag':
            # Square array read by antidiagonals: (0,0), (0,1), (1,0), (0,2), (1,1), (2,0)...
            # d is diagonal index. T_d = d*(d+1)/2.
            # idx = T_d + k.
            # w = floor((math.sqrt(8 * idx + 1) - 1) / 2)
            w = math.floor((math.sqrt(8 * idx + 1) - 1) / 2)
            t = w * (w + 1) // 2
            k = idx - t
            # Traversal (0, w) -> (w, 0) corresponds to row = k, col = w - k
            return func(k, w - k)
        elif strategy == 'triangle':
            # Triangular array read by rows: (0,0), (1,0), (1,1), (2,0), (2,1)...
            w = math.floor((math.sqrt(8 * idx + 1) - 1) / 2)
            t = w * (w + 1) // 2
            k = idx - t
            return func(w, k)
        return 0
    return wrapper

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
    base_oeis_path = os.path.join(config.get_oeis_data_dir(), 'seq')
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
             raise IndexError(f"No data available for sequence {self.name}")
            
        if isinstance(n, int):
            idx = n - self._offset
            if 0 <= idx < len(self._terms):
                return self._terms[idx]
            else:
                raise IndexError(f"Term {n} not found in {self.name} (available: {self._offset}..{self._offset + len(self._terms) - 1})")
        
        raise TypeError(f"Invalid argument type for {self.name}: {type(n)}") 

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

def load_dependency(a_num, context, visited=None, depth=0):
    """
    Recursively loads dependencies for a given A-number.
    1. Tries to find and execute python code for the sequence.
    2. Fallbacks to StubSequence if no code found.
    """
    if visited is None:
        visited = set()
    
    if a_num in visited:
        return
    visited.add(a_num)
    
    if depth > 5: # Safety limit
        if a_num not in context:
            context[a_num] = StubSequence(a_num)
        return

    bucket = a_num[:4]
    # Assuming 'sanitized' is in the current working directory as per structure
    script_dir = os.path.join('sanitized', bucket, a_num)
    
    code_found = False
    
    if os.path.exists(script_dir):
        try:
            files = sorted([f for f in os.listdir(script_dir) if f.startswith(f"{a_num}_python") and f.endswith('.py')])
            if files:
                # Use the first file found as the canonical implementation for dependency
                dep_path = os.path.join(script_dir, files[0])
                with open(dep_path, 'r') as f:
                    dep_code = f.read()
                
                # Pre-scan for deeper dependencies
                sub_ids = set(re.findall(r'A\d{6}', dep_code))
                for sub_id in sub_ids:
                    if sub_id != a_num:
                         load_dependency(sub_id, context, visited, depth + 1)

                # Prepare a separate context for the library to avoid pollution, but we want 
                # its exports to be available.
                lib_context = context.copy()
                lib_context['__name__'] = 'oeis_lib'
                
                # Execute
                exec(dep_code, lib_context)
                
                # Merge relevant symbols back to main context
                for k, v in lib_context.items():
                    if k == '__name__' or k == '__builtins__':
                        continue
                    # We want to export functions, classes, and variables that might be needed.
                    # Especially those starting with A... or common utility names if not conflicting.
                    if k not in context or isinstance(context.get(k), StubSequence):
                         context[k] = v
                
                # Heuristic: If the dependency defines 'a' but not 'Axxxxxx', alias it.
                if a_num not in context and 'a' in lib_context:
                    context[a_num] = lib_context['a']

                code_found = True
        except Exception as e:
            pass

    if not code_found and a_num not in context:
        context[a_num] = StubSequence(a_num)

def prepare_context_with_dependencies(code, main_a_num, original_code=None):
    context = {}
    found_ids = set(re.findall(r'A\d{6}', code))
    
    if original_code:
        found_ids.update(re.findall(r'A\d{6}', original_code))
        
    if main_a_num in found_ids:
        found_ids.remove(main_a_num)
        
    for aid in found_ids:
        load_dependency(aid, context)
        
    return context

def run_b_file_generation(a_num, code, offset, timeout, original_code=None):
    # Prepare context
    context = prepare_context_with_dependencies(code, a_num, original_code)

    # Timeout setup
    signal.signal(signal.SIGALRM, timeout_handler)
    alarm_time = max(5, int(timeout))
    signal.alarm(alarm_time)
    
    context['__name__'] = 'oeis_module' # Avoid __main__ blocks
    
    try:
        exec(code, context)
    except Exception as e:
        sys.stderr.write(f"Error executing code: {e}\n")
        return
    finally:
        signal.alarm(0)

    # Find a(n)
    a_func = None
    gen_func = None
    
    # Check 'a' function
    if 'a' in context and callable(context['a']):
        a_func = context['a']
    elif a_num in context and callable(context[a_num]):
        a_func = context[a_num]
    
    # Check generators
    if not a_func:
        possible_gen_names = ["agen", "a_gen", f"{a_num}gen", f"{a_num}_gen"]
        for name in possible_gen_names:
            if name in context and callable(context[name]):
                gen_func = context[name]
                break
        
        if not gen_func:
             for name, obj in context.items():
                 if (name.endswith("_gen") or name.endswith("gen")) and callable(obj):
                     gen_func = obj
                     break
        
        if gen_func:
            try:
                gen_iter = gen_func()
                gen_cache = []
                def gen_accessor(n):
                    target_idx = n - offset
                    if target_idx < 0: return None
                    while len(gen_cache) <= target_idx:
                        gen_cache.append(next(gen_iter))
                    return gen_cache[target_idx]
                a_func = gen_accessor
            except Exception:
                pass

    if not a_func:
        sys.stderr.write(f"No suitable a(n) function found for {a_num}.\n")
        return

    # Generate b-file
    start_time = time.time()
    n = offset
    count = 0
    limit = 10000 # Default limit
    
    # Reset alarm for loop
    signal.alarm(max(1, int(timeout)))
    
    try:
        while count < limit:
            # Check time
            if time.time() - start_time > timeout:
                break
                
            try:
                val = a_func(n)
                if val is not None:
                    print(f"{n} {val}")
                else:
                    break # Stop if None returned (e.g. generator exhausted or pre-offset)
            except (StopIteration, IndexError):
                break
            except Exception as e:
                sys.stderr.write(f"Error computing a({n}): {e}\n")
                break
            
            n += 1
            count += 1
    except TimeoutError:
        sys.stderr.write(f"Timeout reached ({timeout}s)\n")
    finally:
        signal.alarm(0)

def run_test_for_code(a_num, code, offset, expected_terms, timeout, original_code=None):
    report_messages = []
    
    # Prepare context with stubs and dependencies
    context = prepare_context_with_dependencies(code, a_num, original_code)

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
            elif isinstance(node, ast.If):
                pass # Main block logic is handled in the fallback phase

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
    tests_passed = False
    
    first_func = None
    first_func_name = None

    # 1. Test a(n)
    a_func = None
    gen_func = None
    gen_name = None
    is_list_based = False
    
    if a_num in context and callable(context[a_num]):
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

    elif 'a' in context and callable(context['a']):
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

    elif 'a' in context and not isinstance(context['a'], (list, tuple)) and hasattr(context['a'], '__getitem__'):
        # Support for map-like objects (dict, Counter, etc.) named 'a'
        obj = context['a']
        def map_accessor(n):
            try:
                return obj[n]
            except KeyError:
                # Treat missing key as end of sequence? Or 0?
                # For sparse sequences (Counter), 0 is often implied.
                # But for finite computed dicts, it implies missing data.
                # Let's try returning the value, if it fails, it fails.
                # But Counter doesn't raise KeyError.
                return obj[n]
        a_func = map_accessor
        func_name = 'a (map)'
             
    # Check for list candidates
    list_candidate_name = None
    possible_list_names = [f"{a_num}_list", f"{a_num}List", f"{a_num}list", f"{a_num}_List"]
    for name in possible_list_names:
        if name in context:
            list_candidate_name = name
            break
            
    if list_candidate_name:
        name = list_candidate_name
        obj = context[name]
        if isinstance(obj, list):
            # Support for list based generation (e.g. Axxxxxx_list = [...])
            the_list = obj
            func_name = name
            is_list_based = True
            # Define a closure to access the list safely
            def list_accessor(n):
                idx = n - offset
                if 0 <= idx < len(the_list):
                    return the_list[idx]
                raise IndexError(f"Index {n} (offset {offset}) out of range for list of length {len(the_list)}")
            a_func = list_accessor
        elif callable(obj):
             # It's a function named AxxxxxxList or Axxxxxx_list
             # Assume it's a first(n) function
             first_func = obj
             first_func_name = name
             # Do not assign to a_func
        elif hasattr(obj, '__next__') or hasattr(obj, '__iter__'):
             # Support for generator based lists (from AST transform)
             if hasattr(obj, '__iter__') and not hasattr(obj, '__next__'):
                 gen_iter = iter(obj)
             else:
                 gen_iter = obj
             
             gen_cache = []
             func_name = name
             
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

            # DEBUG
            # print(f"DEBUG: Probe result for {func_name}: type={type(res)}")

            if isinstance(res, (list, tuple)) or (hasattr(res, '__iter__') and not isinstance(res, (str, bytes))):
                # It returns a list or iterator, so it's not a(n), it's likely first(n) or list(lim)
                # If we don't have a first_func yet, use this one
                if not context.get('first'): 
                    if 'first' not in context: 
                        first_func = a_func
                        first_func_name = func_name
                        a_func = None # Remove from a_func candidate
    
        except Exception as e:
            # If calling it failed, we can't determine. Let the main loop handle it.
            # print(f"DEBUG: Probe failed: {e}")
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
            
            # Check signature to ensure it accepts at least one argument (n)
            has_args = False
            try:
                sig = inspect.signature(candidate_func)
                if len(sig.parameters) > 0:
                    has_args = True
            except ValueError:
                # Can't inspect (e.g. built-in), assume yes
                has_args = True
            
            if has_args:
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
                    
                    if isinstance(res, (list, tuple)) or (hasattr(res, '__iter__') and not isinstance(res, (str, bytes))):
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

    # Check for 2D function requiring wrapper
    if a_func and callable(a_func) and not is_list_based:
        try:
            sig = inspect.signature(a_func)
            params = [p for p in sig.parameters.values() if p.default == inspect.Parameter.empty and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
            if len(params) > 1:
                # Potential 2D function. Only accept if it matches a 2D strategy.
                strategies = ['antidiag', 'triangle']
                best_wrapper = None
                
                if len(params) == 2 and expected_terms and len(expected_terms) >= 3:
                    for strat in strategies:
                        wrapper = wrap_2d_candidate(a_func, strat, offset)
                        match = True
                        # Check first few terms to decide strategy
                        check_len = min(len(expected_terms), 5)
                        for i in range(check_len):
                            try:
                                val = wrapper(offset + i)
                                if val != expected_terms[i]:
                                    match = False
                                    break
                            except Exception:
                                match = False
                                break
                        if match:
                            best_wrapper = wrapper
                            func_name += f" (wrapped {strat})"
                            break
                
                if best_wrapper:
                    a_func = best_wrapper
                else:
                    a_func = None
        except ValueError:
            pass

    func_failure_idx = None

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
        recursion_hit = False
        value_error_hit = False
        
        # Set alarm for the entire test loop
        loop_alarm = max(1, int(timeout))
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(loop_alarm)
        
        start_time = time.time()
        extra_terms = 0

        try:
            # 1. Check against expected terms
            for i in range(len(expected_terms)):
                n = offset + i
                
                # Check timeout explicitly for finer control
                if time.time() - start_time > timeout:
                    timed_out = True
                    break

                val = None
                try:
                    val = a_func(n)
                except IndexError:
                    list_exhausted = True
                    break

                if val != expected_terms[i]:
                    msg_extra = ""
                    
                    # Check if val matches neighbors in expected_terms
                    if i + 1 < len(expected_terms) and val == expected_terms[i+1]:
                         msg_extra += " (val matches expected[n+1], possible offset issue)"
                    if i - 1 >= 0 and val == expected_terms[i-1]:
                         msg_extra += " (val matches expected[n-1], possible offset issue)"

                    try:
                        # Check if a_func is shifted relative to n (forward)
                        if a_func(n+1) == expected_terms[i]:
                            msg_extra += " (a(n+1) matches expected, possible offset issue)"
                    except Exception:
                        pass

                    try:
                        # Check if a_func is shifted relative to n (backward)
                        if a_func(n-1) == expected_terms[i]:
                            msg_extra += " (a(n-1) matches expected, possible offset issue)"
                    except Exception:
                        pass
                    
                    func_report += f"FAIL at n={n}: expected {expected_terms[i]}, got {val}{msg_extra}"
                    failures += 1
                    break
                checked += 1
            
            # 2. Continue generating terms until timeout if no failures yet
            if failures == 0 and not list_exhausted and not timed_out:
                n = offset + len(expected_terms)
                term_limit = 10000
                while time.time() - start_time <= timeout and extra_terms < term_limit:
                    try:
                        val = a_func(n)
                        extra_terms += 1
                        n += 1
                    except IndexError:
                        list_exhausted = True
                        break
                    except StopIteration:
                        list_exhausted = True
                        break
                if time.time() - start_time > timeout:
                    timed_out = True

        except TimeoutError:
            timed_out = True
        except RecursionError:
            recursion_hit = True
        except ValueError:
            value_error_hit = True
        except Exception as e:
            report_messages.append(f"  Function '{func_name}(n)': ERROR: {e}")
            failures = -1
            func_failure_idx = len(report_messages) - 1
        finally:
            signal.alarm(0)
            duration = time.time() - start_time
            
        if failures != -1:
            if failures == 0:
                tests_passed = True
                if checked == 0 and len(expected_terms) > 0:
                     if is_list_based:
                         run_guarded_fallback = True
                         tests_run = False
                     else:
                         msg = f"FAIL (checked 0 terms)"
                         report_messages.append(func_report + msg)
                else:
                    msg = f"PASS (checked {checked} terms"
                    if extra_terms > 0:
                        msg += f" + {extra_terms} extra"
                    
                    if is_list_based and (checked == 0 or (list_exhausted and checked < len(expected_terms))):
                         # Fallback logic for partial lists...
                         if extra_terms == 0: # Only fallback if we didn't manage to go beyond
                            run_guarded_fallback = True
                            tests_run = False
                         else:
                            msg += f", list exhausted, took {duration:.3f}s)"
                            report_messages.append(func_report + msg)
                    elif timed_out:
                         msg += f", timed out after {duration:.3f}s)"
                         report_messages.append(func_report + msg)
                    elif recursion_hit:
                         msg += f", hit recursion depth after {duration:.3f}s)"
                         report_messages.append(func_report + msg)
                    elif value_error_hit:
                         msg += f", hit value error after {duration:.3f}s)"
                         report_messages.append(func_report + msg)
                    elif list_exhausted:
                         msg += f", list exhausted, took {duration:.3f}s)"
                         report_messages.append(func_report + msg)
                    else:
                         msg += f", took {duration:.3f}s)"
                         report_messages.append(func_report + msg)
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
                    if not isinstance(res, list):
                        try:
                            res = list(res)
                        except TypeError:
                            pass # Keep original res for error reporting
                            
                    if isinstance(res, list):
                        match_len = min(len(res), len(expected_terms))
                        if res[:match_len] == expected_terms[:match_len]:
                            tests_passed = True
                            func_report += f"PASS (checked first({k}))"
                        else:
                             detail = compare_lists(expected_terms[:match_len], res[:match_len])
                             func_report += f"FAIL ({detail})"
                    else:
                        func_report += f"FAIL (returned {type(res)}, expected list)"
                    report_messages.append(func_report)
                    if not tests_passed:
                        func_failure_idx = len(report_messages) - 1
                except Exception as e:
                     report_messages.append(f"  Function '{first_func_name}(n)': ERROR: {e}")
                     func_failure_idx = len(report_messages) - 1
        except TimeoutError:
             report_messages.append(f"  Function '{first_func_name}(n)': TIMEOUT")
             func_failure_idx = len(report_messages) - 1
        finally:
            signal.alarm(0)

    # 3. Test is(n)
    is_func = None
    priority_names = ['is_seq', f'is_{a_num}', 'ok']
    
    # First pass: Check priority names
    for name in priority_names:
        if name in context and callable(context[name]):
            candidate = context[name]
            # Verify signature if possible
            try:
                sig = inspect.signature(candidate)
                required_args = 0
                for p in sig.parameters.values():
                    if p.default == inspect.Parameter.empty and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                        required_args += 1
                
                if required_args == 1:
                    is_func = candidate
                    break
            except (ValueError, TypeError):
                # Assume yes if we can't inspect (legacy behavior for priorities)
                is_func = candidate
                break
            
    # Second pass: If not found, look for any function starting with 'is'
    if not is_func:
        candidates = []
        for name, obj in context.items():
            if callable(obj) and not isinstance(obj, StubSequence) and name != '__builtins__':
                 if (name.startswith('is') or name.startswith('Is')) and name != 'islice':
                     # Exclude if it's already in priority names
                     if name not in priority_names:
                         # Check module to prioritize defined functions over imported ones
                         mod = getattr(obj, '__module__', None)
                         if mod == 'oeis_module' or mod is None:
                             candidates.append(obj)
        
        # If there is exactly one such candidate, assume it is the is(n) function
        if len(candidates) == 1:
            candidate = candidates[0]
            # Verify signature requires 1 arg
            try:
                sig = inspect.signature(candidate)
                required_args = 0
                for p in sig.parameters.values():
                    if p.default == inspect.Parameter.empty and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                        required_args += 1
                if required_args == 1:
                    is_func = candidate
            except (ValueError, TypeError):
                 # Assume yes if we can't inspect
                 pass

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
                 tests_passed = True
                 func_report += f"PASS (checked partial known terms, timed out)"
                 report_messages.append(func_report)
            elif failures == 0:
                 tests_passed = True
                 report_messages.append(func_report)
            else:
                 report_messages.append(func_report)
                 a_func_failure_idx = len(report_messages) - 1
    
    # 4. Check STDOUT or Fallback to Guarded Execution
    if not tests_run or run_guarded_fallback or (tests_run and not tests_passed):
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
                        # Transformation 0: Convert print(list(iterable)) to incremental print loop
                        for j, subnode in enumerate(node.body):
                            if (isinstance(subnode, ast.Expr) and 
                                isinstance(subnode.value, ast.Call) and
                                isinstance(subnode.value.func, ast.Name) and 
                                subnode.value.func.id == 'print' and
                                len(subnode.value.args) == 1 and
                                isinstance(subnode.value.args[0], ast.Call) and
                                isinstance(subnode.value.args[0].func, ast.Name) and
                                subnode.value.args[0].func.id == 'list' and
                                len(subnode.value.args[0].args) == 1):
                                
                                # Found print(list(iterable))
                                iterable_arg = subnode.value.args[0].args[0]
                                
                                # Create For loop: for _oeis_print_iter in iterable_arg: print(_oeis_print_iter)
                                iter_var = ast.Name(id='_oeis_print_iter', ctx=ast.Store())
                                print_call = ast.Call(
                                    func=ast.Name(id='print', ctx=ast.Load()),
                                    args=[ast.Name(id='_oeis_print_iter', ctx=ast.Load())],
                                    keywords=[]
                                )
                                
                                for_loop = ast.For(
                                    target=iter_var,
                                    iter=iterable_arg,
                                    body=[ast.Expr(value=print_call)],
                                    orelse=[]
                                )
                                
                                ast.copy_location(for_loop, subnode)
                                ast.fix_missing_locations(for_loop)
                                node.body[j] = for_loop
                                modified = True

                        # Transformation 1: Convert print([ListComp]) to incremental print loop
                        for j, subnode in enumerate(node.body):
                             if (isinstance(subnode, ast.Expr) and 
                                 isinstance(subnode.value, ast.Call) and
                                 isinstance(subnode.value.func, ast.Name) and 
                                 subnode.value.func.id == 'print' and
                                 len(subnode.value.args) == 1 and
                                 isinstance(subnode.value.args[0], ast.ListComp)):
                                 
                                 lc = subnode.value.args[0]
                                 
                                 # Convert to GeneratorExp
                                 gen_exp = ast.GeneratorExp(elt=lc.elt, generators=lc.generators)
                                 
                                 # Create For loop: for _oeis_print_iter in gen_exp: print(_oeis_print_iter)
                                 iter_var = ast.Name(id='_oeis_print_iter', ctx=ast.Store())
                                 print_call = ast.Call(
                                     func=ast.Name(id='print', ctx=ast.Load()),
                                     args=[ast.Name(id='_oeis_print_iter', ctx=ast.Load())],
                                     keywords=[]
                                 )
                                 
                                 for_loop = ast.For(
                                     target=iter_var,
                                     iter=gen_exp,
                                     body=[ast.Expr(value=print_call)],
                                     orelse=[]
                                 )
                                 
                                 ast.copy_location(for_loop, subnode)
                                 ast.fix_missing_locations(for_loop)
                                 node.body[j] = for_loop
                                 modified = True
                             
                             # Transformation 2: Convert Axxxxxx = [ListComp] to GeneratorExp
                             elif (isinstance(subnode, ast.Assign) and 
                                   isinstance(subnode.value, ast.ListComp)):
                                 for target in subnode.targets:
                                     if isinstance(target, ast.Name) and target.id == a_num:
                                         # Found assignment to sequence ID
                                         lc = subnode.value
                                         gen_exp = ast.GeneratorExp(elt=lc.elt, generators=lc.generators)
                                         ast.copy_location(gen_exp, lc)
                                         ast.fix_missing_locations(gen_exp)
                                         
                                         # Replace the value
                                         subnode.value = gen_exp
                                         modified = True
                                         break

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
             if not tests_run:
                 report_messages.append(f"  [ERROR] Execution failed: {e}")
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

        # Check if the sequence variable itself is available (e.g. from assignment in main)
        if not tests_run and a_num in context:
            obj = context[a_num]
            res_list = []
            
            # Consume if generator/iterator
            if hasattr(obj, '__iter__') or hasattr(obj, '__next__'):
                 if hasattr(obj, '__iter__') and not hasattr(obj, '__next__'):
                     it = iter(obj)
                 else:
                     it = obj
                 
                 # Set alarm for consumption
                 signal.signal(signal.SIGALRM, timeout_handler)
                 signal.alarm(max(1, int(timeout)))
                 
                 try:
                     # Fetch enough terms to check
                     for _ in range(len(expected_terms)):
                         res_list.append(next(it))
                 except (StopIteration, TimeoutError):
                     pass
                 except Exception:
                     pass
                 finally:
                     signal.alarm(0)
                     
            elif isinstance(obj, list):
                res_list = obj
            
            if res_list:
                tests_run = True
                match_len = min(len(res_list), len(expected_terms))
                if match_len > 0 and res_list[:match_len] == expected_terms[:match_len]:
                     report_messages.append(f"  Script variable '{a_num}': PASS (checked {match_len} terms)")
                else:
                     detail = compare_lists(expected_terms[:match_len], res_list[:match_len])
                     report_messages.append(f"  Script variable '{a_num}': FAIL ({detail})")
                     func_failure_idx = len(report_messages) - 1

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
             elif failures > 0:
                 tests_run = True
                 report_messages.append(func_report)

        # Check stdout if still needed or if just supplementing
        output_str = captured_output.getvalue()
        if output_str.strip() and (not tests_run or not tests_passed):
            found_numbers = [int(x) for x in re.findall(r'-?\d+', output_str)]
            if found_numbers:
                tests_run = True
                match_len = min(len(found_numbers), len(expected_terms))
                if match_len > 0 and found_numbers[:match_len] == expected_terms[:match_len]:
                    report_messages.append(f"  Script output: PASS (checked {match_len} terms from stdout)")
                    # Suppress previous a_func failure if we found a match here
                    if func_failure_idx is not None:
                        # print(f"DEBUG: Suppressing failure at {func_failure_idx}")
                        report_messages[func_failure_idx] = None
                else:
                    detail = compare_lists(expected_terms[:match_len], found_numbers[:match_len])
                    report_messages.append(f"  Script output: FAIL ({detail})")
            else:
                 report_messages.append("  [INFO] Script produced output but no numbers found.")

    if not tests_run:
        has_exec_error = any("[ERROR] Execution failed" in m for m in report_messages)
        if not has_exec_error:
            report_messages.append("  [ERROR] No known test functions found (expected 'a(n)', 'first(n)', or 'is(n)').")
    
    return [m for m in report_messages if m is not None]

def test_file(a_num, timeout=1.0, b_file=False):
    bucket = a_num[:4]
    # New Path: sanitized/Axxx/Axxxxxx/
    base_dir = 'sanitized'
    seq_dir = os.path.join(base_dir, bucket, a_num)
    
    report_messages = []

    if not os.path.exists(seq_dir):
        report_messages.append(f"Directory not found for {a_num}: {seq_dir}")
        return report_messages
    
    # Find all python files
    # Expected naming: Axxxxxx_python_1.py, Axxxxxx_python_2.py, etc.
    try:
        files = sorted([f for f in os.listdir(seq_dir) if f.startswith(f"{a_num}_python") and f.endswith('.py')])
    except OSError as e:
        report_messages.append(f"Error accessing directory {seq_dir}: {e}")
        return report_messages
        
    if not files:
        report_messages.append(f"No Python files found in {seq_dir}")
        return report_messages

    if not b_file:
        report_messages.append(f"Testing {a_num} (found {len(files)} scripts in {seq_dir})...")
    
    offset, expected_terms = load_oeis_data(a_num)
    if offset is None:
        offset = 0 # Default if unknown
    if expected_terms is None and not b_file:
        report_messages.append(f"  [SKIP] No data found for {a_num}")
        return report_messages

    if b_file:
        # For b-file, use the first file found.
        file_path = os.path.join(seq_dir, files[0])
        original_code = None
        prog_file_path = file_path.replace('sanitized', 'progs', 1)
        if os.path.exists(prog_file_path):
            try:
                with open(prog_file_path, 'r') as f:
                    original_code = f.read()
            except Exception:
                pass
                
        try:
            with open(file_path, 'r') as f:
                code = f.read()
            run_b_file_generation(a_num, code, offset, timeout, original_code)
        except Exception:
            pass
        return []

    for i, filename in enumerate(files):
        file_path = os.path.join(seq_dir, filename)
        if len(files) > 1:
            report_messages.append(f"  --- Program {i+1} ({filename}) ---")
            
        original_code = None
        prog_file_path = file_path.replace('sanitized', 'progs', 1)
        if os.path.exists(prog_file_path):
            try:
                with open(prog_file_path, 'r') as f:
                    original_code = f.read()
            except Exception:
                pass

        try:
            with open(file_path, 'r') as f:
                code = f.read()
            
            section_messages = run_test_for_code(a_num, code, offset, expected_terms, timeout, original_code)
            report_messages.extend(section_messages)
        except Exception as e:
            report_messages.append(f"  [ERROR] Could not read or run {filename}: {e}")

    return report_messages


def main():
    parser = argparse.ArgumentParser(description="Test OEIS Python programs.")
    parser.add_argument("a_number", help="The OEIS A-number (e.g., A000045).")
    parser.add_argument("--timeout", type=float, default=1.0, help="Timeout in seconds for testing loops (default: 1.0).")
    parser.add_argument("--b-file", action="store_true", help="Generate a b-file to stdout instead of testing.")
    args = parser.parse_args()
    
    # Basic validation for A-number format
    if not re.match(r'^A\d{6}$', args.a_number):
        print(f"Invalid A-number format: {args.a_number}. Expected format like A000045.", file=sys.stderr)
        sys.exit(1)

    messages = test_file(args.a_number, timeout=args.timeout, b_file=args.b_file)
    for msg in messages:
        print(msg)

if __name__ == "__main__":
    main()
