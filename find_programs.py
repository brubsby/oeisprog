import os
import argparse
import re

def main():
    parser = argparse.ArgumentParser(description="Find sequence numbers for a specific programming language.")
    parser.add_argument("language", help="The programming language to search for (e.g., python, pari, haskell). Case-insensitive.")
    args = parser.parse_args()

    target_lang = args.language.lower()
    
    # Base directory for extracted programs
    progs_dir = os.path.expanduser("~/Repos/oeisprog/progs/")
    
    if not os.path.exists(progs_dir):
        print(f"Error: Directory not found: {progs_dir}")
        return

    # Use 'find' command for performance
    # Filename format: Axxxxxx_langname_index.ext
    # We search for *_{target_lang}_*
    # But strictly, we want it to match the lang_name part.
    # The format is Axxxxxx_LANG_index.ext.
    # So we search for pattern "*_LANG_[0-9]*.*"
    
    import subprocess
    
    # Construct glob pattern
    # We want to match /Axxxxxx_targetlang_index.ext
    # target_lang might have underscores.
    
    pattern = f"*_{target_lang}_[0-9]*.*"
    
    try:
        # Run find command
        # -name is case sensitive (linux find). Python script said case-insensitive arg?
        # If user wants case-insensitive, we should use -iname.
        # But we lowercased target_lang and we saved files with lowercased lang names.
        # So -name should be fine if we use the lowercased target_lang.
        
        cmd = ["find", progs_dir, "-name", pattern]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error running find: {result.stderr}")
            return

        paths = result.stdout.splitlines()
        found_sequences = set()
        
        for path in paths:
            filename = os.path.basename(path)
            # Axxxxxx_lang_index.ext
            parts = filename.split('_')
            if len(parts) >= 3:
                a_num = parts[0]
                if re.match(r'^A\d{6}$', a_num):
                    found_sequences.add(a_num)
                    
        for seq in sorted(list(found_sequences)):
            print(seq)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
