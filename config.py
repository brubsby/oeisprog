import os
import sys

def _find_oeisdata_dir():
    # 1. Environment Variable
    env_path = os.environ.get('OEISDATA_DIR')
    if env_path:
        if os.path.exists(env_path):
            return os.path.abspath(env_path)

    # 2. Sibling Directory
    # current file is in oeisprog/config.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sibling_path = os.path.join(os.path.dirname(current_dir), 'oeisdata')
    if os.path.exists(sibling_path):
        return os.path.abspath(sibling_path)

    return None

OEIS_DATA_DIR = _find_oeisdata_dir()

# Helper for scripts that definitely need it
def get_oeis_data_dir():
    if OEIS_DATA_DIR:
        return OEIS_DATA_DIR
    
    # Fail gracefully-ish
    print(
        "Error: Could not find 'oeisdata' directory.\n"
        "Please either:\n"
        "  1. Clone 'oeisdata' as a sibling directory to 'oeisprog'.\n"
        "  2. Set the 'OEISDATA_DIR' environment variable.",
        file=sys.stderr
    )
    sys.exit(1)
