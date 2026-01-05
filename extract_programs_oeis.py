import os
import re
import ast
import sys
import config

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(config.get_oeis_data_dir(), 'seq')
RAW_DIR = os.path.join(SCRIPT_DIR, 'progs')
SANITIZED_DIR = os.path.join(SCRIPT_DIR, 'sanitized')

def is_safe_top_level(node):
    """
    Determines if an AST node is safe to keep at the top level (definitions/imports)
    or if it should be guarded (loops, prints, function calls).
    """
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return True
    
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return True
    
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        return True
        
    return False

def sanitize_code(source_code):
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return source_code, False

    def wrap_in_print(node):
        if isinstance(node, ast.Expr):
             if isinstance(node.value, (ast.ListComp, ast.List, ast.BinOp, ast.GeneratorExp, ast.SetComp, ast.DictComp, ast.Call)):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name) and node.value.func.id == 'print':
                        return node
                
                print_call = ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[node.value],
                    keywords=[]
                )
                return ast.Expr(value=print_call)
        return node

    main_block_node = None
    for node in tree.body:
        if isinstance(node, ast.If):
            try:
                if (isinstance(node.test, ast.Compare) and 
                    isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__' and
                    isinstance(node.test.ops[0], ast.Eq)):
                     
                     comp = node.test.comparators[0]
                     val = None
                     if isinstance(comp, ast.Constant): val = comp.value
                     elif hasattr(ast, 'Str') and isinstance(comp, ast.Str): val = comp.s
                     
                     if val == '__main__':
                         main_block_node = node
                         break
            except Exception:
                pass

    if sys.version_info < (3, 9):
        print("Python 3.9+ required for ast.unparse")
        return source_code, False

    if main_block_node:
        if main_block_node.body:
            main_block_node.body[-1] = wrap_in_print(main_block_node.body[-1])
            try:
                return ast.unparse(tree), True
            except Exception as e:
                print(f"Error unparsing code: {e}")
                return source_code, False
        else:
            return source_code, False

    keep_nodes = []
    guard_nodes = []

    for node in tree.body:
        if is_safe_top_level(node):
            keep_nodes.append(node)
        else:
            guard_nodes.append(node)

    if not guard_nodes:
        return source_code, False

    if guard_nodes:
        guard_nodes[-1] = wrap_in_print(guard_nodes[-1])

    guard_test = ast.Compare(
        left=ast.Name(id='__name__', ctx=ast.Load()),
        ops=[ast.Eq()],
        comparators=[ast.Constant(value='__main__')]
    )
    guard_block = ast.If(test=guard_test, body=guard_nodes, orelse=[])
    
    new_tree = ast.Module(body=keep_nodes + [guard_block], type_ignores=[])
    
    try:
        return ast.unparse(new_tree), True
    except Exception as e:
        print(f"Error unparsing code: {e}")
        return source_code, False

def extract_programs_from_file(filepath):
    """
    Extracts programs from a .seq file.
    Returns a list of tuples: (language, code_content)
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

    programs = []
    current_code = []
    current_lang = None
    prefix_len = 0
    
    header_pattern = re.compile(r'^(%[opt]\s+(A\d+)\s+)\(([A-Z][a-zA-Z0-9\+\-\s]*)\)')
    legacy_pattern = re.compile(r'^(%([pt])\s+(A\d+)[ \t])(.*)')
    
    for line in lines:
        header_match = header_pattern.match(line)
        legacy_match = legacy_pattern.match(line) if not header_match else None
        
        if header_match:
            # New program start with explicit language tag: (Language)
            if current_lang and current_code:
                programs.append((current_lang, "\n".join(current_code)))
                current_code = []

            current_lang = header_match.group(3)
            prefix_len = len(header_match.group(1))
            
            # Check for inline code after the tag
            full_header_len = len(header_match.group(0))
            if len(line) > full_header_len:
                remainder = line[full_header_len:].rstrip('\n')
                if remainder.strip():
                    current_code.append(remainder)
            continue

        elif legacy_match:
            # Legacy field code start: %p (Maple) or %t (Mathematica)
            tag = legacy_match.group(2)
            new_lang = 'Maple' if tag == 'p' else 'Mathematica'
            
            # If we are already collecting this language, treat as continuation
            if current_lang == new_lang:
                 remainder = legacy_match.group(4).rstrip('\n')
                 if remainder.strip():
                     current_code.append(remainder)
                 continue

            if current_lang and current_code:
                programs.append((current_lang, "\n".join(current_code)))
                current_code = []

            current_lang = new_lang
            prefix_len = len(legacy_match.group(1))
            
            remainder = legacy_match.group(4).rstrip('\n')
            if remainder.strip():
                current_code.append(remainder)
            continue
            
        if current_lang:
            # Check if the line belongs to the current program block
            # A program block continues as long as it starts with %o, %p, or %t 
            # and follows the same prefix length / structure.
            if not (line.startswith('%o') or line.startswith('%p') or line.startswith('%t')):
                programs.append((current_lang, "\n".join(current_code)))
                current_code = []
                current_lang = None
                continue
                
            if len(line) < prefix_len:
                 programs.append((current_lang, "\n".join(current_code)))
                 current_code = []
                 current_lang = None
                 continue
                
            code_line = line[prefix_len:].rstrip('\n')
            current_code.append(code_line)
            
    # End of file, save last program
    if current_lang and current_code:
        programs.append((current_lang, "\n".join(current_code)))

    return programs

def save_program(base_dir, a_num, lang, code, index):
    bucket = a_num[:4]
    # Structure: base_dir/A000/A000002/
    target_dir = os.path.join(base_dir, bucket, a_num)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        
    # Map language to extension and normalized name
    lang_map = {
        'Python': ('python', 'py'),
        'PARI': ('pari', 'gp'),
        'Mathematica': ('mathematica', 'wl'),
        'Maple': ('maple', 'mpl'),
        'Magma': ('magma', 'mag'),
        'SageMath': ('sagemath', 'sage'),
        'Haskell': ('haskell', 'hs'),
        'GAP': ('gap', 'g'),
        'Scheme': ('scheme', 'scm'),
        'Maxima': ('maxima', 'mac'),
        'C': ('c', 'c'),
        'C++': ('cpp', 'cpp'),
        'Perl': ('perl', 'pl'),
        'MATLAB': ('matlab', 'm'),
        'Ruby': ('ruby', 'rb'),
        'Julia': ('julia', 'jl'),
        'Scala': ('scala', 'scala'),
        'R': ('r', 'r'),
        'Java': ('java', 'java'),
        'MuPAD': ('mupad', 'mu'),
        'JavaScript': ('javascript', 'js'),
        'Aribas': ('aribas', 'ari'),
        'UBASIC': ('ubasic', 'bas'),
        'Fortran': ('fortran', 'f'),
        'Rust': ('rust', 'rs'),
        'Go': ('go', 'go'),
        'Pascal': ('pascal', 'pas'),
        'BASIC': ('basic', 'bas'),
        'Visual Basic': ('visual_basic', 'vb'),
        'PHP': ('php', 'php'),
        'Smalltalk': ('smalltalk', 'st'),
        'Common Lisp': ('common_lisp', 'lisp'),
        'Lisp': ('lisp', 'lisp'),
        'Sidef': ('sidef', 'sf'),
        'MiniZinc': ('minizinc', 'mzn'),
        'APL': ('apl', 'apl'),
        'Kotlin': ('kotlin', 'kt'),
        'AWK': ('awk', 'awk'),
        'Tcl': ('tcl', 'tcl'),
        'Lua': ('lua', 'lua'),
        'Clojure': ('clojure', 'clj'),
        'OCaml': ('ocaml', 'ml'),
        'REXX': ('rexx', 'rexx'),
        'Swift': ('swift', 'swift')
    }
    
    if lang in lang_map:
        lang_name, ext = lang_map[lang]
    else:
        # Sanitize language name for filename
        lang_name = lang.lower().replace(' ', '_')
        # Allow alphanumeric, underscores, plus, minus
        lang_name = re.sub(r'[^a-z0-9_\+\-]', '', lang_name)
        if not lang_name:
            lang_name = "unknown"
        ext = 'txt'
        
    filename = f"{a_num}_{lang_name}_{index}.{ext}"
    filepath = os.path.join(target_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    return filepath

def split_legacy_program(code_block):
    """
    Splits a merged block of legacy code (Maple/Mathematica) into separate programs.
    """
    lines = code_block.split('\n')
    sig_pattern = re.compile(r'_\s*,\s*[A-Z][a-z]{2}\s+\d{2}\s+\d{4}')
    comment_pattern = re.compile(r'^\s*(#|--|\(\*)')
    
    programs = []
    current_prog = []
    pending_comments = []
    
    for i, line in enumerate(lines):
        line_content = line.strip()
        if not line_content:
            continue
            
        has_sig = bool(sig_pattern.search(line))
        is_comment = bool(comment_pattern.match(line))
        is_indented = line.startswith(' ') or line.startswith('\t')
        
        # If it's a comment line (and not part of a signature line unless sig logic handles it),
        # we treat it as a preamble to the NEXT program, unless we are INSIDE a block?
        # But if we are inside a block (indented), comments are just code.
        # So "is_comment" only applies if NOT indented?
        # Actually, indented comments are part of the code block.
        if is_comment and not is_indented and not has_sig:
            pending_comments.append(line)
            continue
            
        if has_sig:
            # Ends the current program.
            # Attach any pending comments to THIS program?
            # Or did they belong to the next?
            # Usually comments precede code.
            # If we have accumulated code, pending comments belonged to IT.
            # If we have NO code, pending comments belong to THIS line.
            
            # Actually, `pending_comments` should be attached to `current_prog` as soon as we start adding code.
            # So if we are here, we append line and flush.
            
            # But wait, if `current_prog` is empty, attach `pending_comments` now.
            if not current_prog:
                current_prog.extend(pending_comments)
                pending_comments = []
                
            current_prog.append(line)
            programs.append("\n".join(current_prog))
            current_prog = []
            continue
            
        if is_indented:
            # Continuation.
            current_prog.append(line)
            continue
            
        # Unindented Code (No Sig)
        # Check next line
        is_next_indented = False
        if i + 1 < len(lines):
            next_line = lines[i+1]
            is_next_indented = next_line.startswith(' ') or next_line.startswith('\t')
            
        # Start of new code block (or one-liner)
        # Attach pending comments
        current_prog.extend(pending_comments)
        pending_comments = []
        current_prog.append(line)
        
        if not is_next_indented:
            # One-liner. Flush.
            programs.append("\n".join(current_prog))
            current_prog = []
            
    # Flush leftovers
    if current_prog or pending_comments:
        current_prog.extend(pending_comments)
        programs.append("\n".join(current_prog))
        
    return programs

def is_code_empty(code):
    lines = code.splitlines()
    for line in lines:
        s = line.strip()
        if s and not s.startswith('#'):
            return False
    return True

def process_file(file_path, a_num):
    programs = extract_programs_from_file(file_path)
    if not programs:
        return 0
        
    counters = {} # lang -> count
    
    extracted_count = 0
    for lang, code in programs:
        # Filter for Python only if strictly required, but user wants to separate programs.
        # User said: "We now have sagemath ... I want to use ... to come up with a language agnostic 'program runner'"
        # So we should save all of them.
        
        # Strip code
        code = code.strip()
        if not code:
            continue
            
        if lang == 'Python' and is_code_empty(code):
            continue

        # Handle Legacy Splitting
        if lang in ['Maple', 'Mathematica']:
            sub_programs = split_legacy_program(code)
        else:
            sub_programs = [code]
            
        for sub_code in sub_programs:
            sub_code = sub_code.strip()
            if not sub_code:
                continue
            
            if lang == 'Python' and is_code_empty(sub_code):
                continue
                
            counters[lang] = counters.get(lang, 0) + 1
            index = counters[lang]
            
            # Save Raw
            save_program(RAW_DIR, a_num, lang, sub_code, index)
            
            # Save Sanitized (Python only for now)
            if lang == 'Python':
                sanitized_code, _ = sanitize_code(sub_code)
                save_program(SANITIZED_DIR, a_num, lang, sanitized_code, index)
                
            extracted_count += 1
        
    return extracted_count

def main():
    import argparse
    import shutil
    
    parser = argparse.ArgumentParser(description="Extract programs from OEIS sequence files.")
    parser.add_argument("a_number", nargs="?", help="The OEIS A-number (e.g., A000045). If omitted, runs in batch mode.")
    parser.add_argument("-c", "--clean", action="store_true", help="Clean existing extracted programs before running.")
    args = parser.parse_args()

    if args.a_number:
        # Single sequence mode
        a_num = args.a_number
        if not re.match(r'^A\d{6}$', a_num):
            print(f"Invalid A-number: {a_num}. Expected format Axxxxxx.")
            sys.exit(1)
            
        bucket = a_num[:4]
        seq_file_path = os.path.join(SOURCE_DIR, bucket, f"{a_num}.seq")
        
        if not os.path.exists(seq_file_path):
             seq_file_path_no_ext = os.path.join(SOURCE_DIR, bucket, a_num)
             if os.path.exists(seq_file_path_no_ext):
                 seq_file_path = seq_file_path_no_ext
             else:
                 print(f"Sequence file not found: {seq_file_path}")
                 sys.exit(1)
        
        if args.clean:
            # Clean specifically for this sequence
            # RAW_DIR/Bucket/Axxxxxx
            # SANITIZED_DIR/Bucket/Axxxxxx
            for base_dir in [RAW_DIR, SANITIZED_DIR]:
                target_dir = os.path.join(base_dir, bucket, a_num)
                if os.path.exists(target_dir):
                    print(f"Cleaning {target_dir}...")
                    shutil.rmtree(target_dir)

        count = process_file(seq_file_path, a_num)
        print(f"Extracted {count} programs for {a_num}")
            
    else:
        # Batch mode
        if args.clean:
            print(f"Cleaning all programs in '{RAW_DIR}' and '{SANITIZED_DIR}'...")
            if os.path.exists(RAW_DIR):
                shutil.rmtree(RAW_DIR)
            if os.path.exists(SANITIZED_DIR):
                shutil.rmtree(SANITIZED_DIR)

        if not os.path.exists(RAW_DIR):
            os.makedirs(RAW_DIR)
        if not os.path.exists(SANITIZED_DIR):
            os.makedirs(SANITIZED_DIR)
            
        print(f"Scanning {SOURCE_DIR} for programs...")
        
        files_processed = 0
        programs_extracted = 0
        
        for root, dirs, files in os.walk(SOURCE_DIR):
            for file in files:
                # Assuming filename is Axxxxxx.seq or Axxxxxx
                if not file.startswith('A'):
                    continue
                
                a_num = os.path.splitext(file)[0]
                if not re.match(r'^A\d{6}$', a_num):
                    continue

                file_path = os.path.join(root, file)
                count = process_file(file_path, a_num)
                
                programs_extracted += count
                files_processed += 1
                
                if files_processed % 1000 == 0:
                    print(f"Processed {files_processed} files, extracted {programs_extracted} programs...")

        print(f"Complete. Processed {files_processed} files. Extracted {programs_extracted} programs.")

if __name__ == '__main__':
    main()
