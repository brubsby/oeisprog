import os
import re

SOURCE_DIR = os.path.join('..', 'oeisdata', 'seq')
TARGET_DIR = 'pythonprogs'

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
        
    return "\n".join(python_code)

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
