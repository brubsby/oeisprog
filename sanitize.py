import ast
import os
import sys
# import astor # Need to check if astor is available or use ast.unparse (py3.9+)

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
    # We need to reconstruct source. Python 3.9+ has ast.unparse.
    # Assuming environment has 3.9+.
    
    if sys.version_info < (3, 9):
        print("Python 3.9+ required for ast.unparse")
        return source_code, False

    # Create the guard: if __name__ == "__main__":
    guard_test = ast.Compare(
        left=ast.Name(id='__name__', ctx=ast.Load()),
        ops=[ast.Eq()],
        comparators=[ast.Constant(value='__main__')]
    )
    guard_block = ast.If(test=guard_test, body=guard_nodes, orelse=[])
    
    new_tree = ast.Module(body=keep_nodes + [guard_block], type_ignores=[])
    
    return ast.unparse(new_tree), True

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sanitize.py <file>")
        return

    filepath = sys.argv[1]
    with open(filepath, 'r') as f:
        code = f.read()
    
    # Handle separators
    sections = code.split("# OEIS_PYTHON_SEPARATOR")
    new_sections = []
    changed = False
    
    for section in sections:
        sanitized, modified = sanitize_code(section)
        new_sections.append(sanitized)
        if modified:
            changed = True
            
    if changed:
        new_code = "\n# OEIS_PYTHON_SEPARATOR\n".join(new_sections)
        with open(filepath, 'w') as f:
            f.write(new_code)
        print(f"Sanitized {filepath}")
    else:
        print(f"No changes needed for {filepath}")

if __name__ == "__main__":
    main()
