import os
import re
import ast
import sys

SOURCE_DIR = os.path.join('..', 'oeisdata', 'seq')
TARGET_DIR = 'pythonprogs'

def is_safe_top_level(node):
    """
    Determines if an AST node is safe to keep at the top level (definitions/imports)
    or if it should be guarded (loops, prints, function calls).
    """
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return True
    
    # assignments: simple assignments (literals) are safe.
    # complex assignments (function calls) might be unsafe, but usually are config.
    # For now, let's assume assignments are safe-ish, but we might want to be stricter.
    # Actually, if a script calculates a list 'a_list = [...]' via list comp, that might be heavy.
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        # Check value. If it's a list comp or call, it might be heavy.
        # But usually these define the sequence. We probably want them global.
        return True
    
    # Comments (Expr with string) -> safe (docstrings)
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        return True
        
    return False

def sanitize_code(source_code):
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # If syntax error, can't sanitize, return as is
        return source_code, False

    # Check if already has "if __name__ == '__main__':"
    # Simple check: look for an If node comparing __name__ and '__main__'
    for node in tree.body:
        if isinstance(node, ast.If):
            # This is a rough check, could be more precise
            try:
                if node.test.left.id == '__name__' and node.test.comparators[0].value == '__main__':
                    return source_code, False
            except AttributeError:
                pass

    keep_nodes = []
    guard_nodes = []

    for node in tree.body:
        if is_safe_top_level(node):
            keep_nodes.append(node)
        else:
            guard_nodes.append(node)

    if not guard_nodes:
        return source_code, False

    # Construct new tree
    if sys.version_info < (3, 9):
        print("Python 3.9+ required for ast.unparse")
        return source_code, False

    # AST Transformation: Check if the last node in guard_nodes is an Expr (expression statement)
    # and if it is a ListComp or List. If so, wrap it in print().
    if guard_nodes:
        last_node = guard_nodes[-1]
        if isinstance(last_node, ast.Expr) and isinstance(last_node.value, (ast.ListComp, ast.List)):
            # Replace Expr(value) with Expr(Call(func=Name('print'), args=[value]))
            print_call = ast.Call(
                func=ast.Name(id='print', ctx=ast.Load()),
                args=[last_node.value],
                keywords=[]
            )
            guard_nodes[-1] = ast.Expr(value=print_call)

    # Create the guard: if __name__ == "__main__":
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

def extract_python_from_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

    python_code = []
    extracting = False
    prefix_len = 0
    
    # Regex to detect any language header: %o ID (Language)
    header_pattern = re.compile(r'^(%o\s+(A\d+)\s+)\((.+?)\)')
    
    for line in lines:
        header_match = header_pattern.match(line)
        
        if header_match:
            lang = header_match.group(3)
            if lang == 'Python':
                # If we already have code, this indicates a new block/implementation
                if python_code:
                    python_code.append("# OEIS_PYTHON_SEPARATOR")
                extracting = True
                prefix_len = len(header_match.group(1))
            else:
                extracting = False
            # Skip the header line itself
            continue
            
        if extracting:
            # Check if the line is still a %o line
            if not line.startswith('%o'):
                extracting = False
                continue
                
            # Check for safety (prefix should match)
            if len(line) < prefix_len:
                extracting = False
                continue
                
            code_line = line[prefix_len:].rstrip('\n')
            python_code.append(code_line)

    if not python_code:
        return None
        
    full_code = "\n".join(python_code)
    
    # Sanitize sections
    sections = full_code.split("# OEIS_PYTHON_SEPARATOR")
    sanitized_sections = []
    for section in sections:
        # Strip leading/trailing whitespace to avoid parse errors on empty lines if any
        s_code = section.strip()
        if s_code:
            sanitized_code, _ = sanitize_code(s_code)
            sanitized_sections.append(sanitized_code)
        else:
            # Preserve empty sections? probably not useful.
            pass
            
    return "\n# OEIS_PYTHON_SEPARATOR\n".join(sanitized_sections)

def main():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    print(f"Scanning {SOURCE_DIR} for Python code...")
    
    files_processed = 0
    scripts_extracted = 0
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            # We are looking for sequence files. 
            # They seem to have .seq extension or no extension?
            # We'll process everything.
            
            file_path = os.path.join(root, file)
            code = extract_python_from_file(file_path)
            
            if code:
                # Construct mirror path
                rel_path = os.path.relpath(root, SOURCE_DIR)
                target_subdir = os.path.join(TARGET_DIR, rel_path)
                
                if not os.path.exists(target_subdir):
                    os.makedirs(target_subdir)
                
                # Filename: Axxxxxx.py
                # If original is Axxxxxx.seq, strip .seq
                filename_base = os.path.splitext(file)[0]
                target_file = os.path.join(target_subdir, filename_base + ".py")
                
                with open(target_file, 'w', encoding='utf-8') as out:
                    out.write(code)
                
                scripts_extracted += 1
            
            files_processed += 1
            if files_processed % 1000 == 0:
                print(f"Processed {files_processed} files, extracted {scripts_extracted} scripts...")

    print(f"Complete. Processed {files_processed} files. Extracted {scripts_extracted} Python scripts to '{TARGET_DIR}'.")

if __name__ == '__main__':
    main()
