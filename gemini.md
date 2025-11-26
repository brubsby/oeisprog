# OEIS Python Project Context

This document outlines the environment, tools, and conventions for the `oeisprog` project. It serves as a guide for maintaining and improving the collection of Python programs for OEIS sequences.

## 1. Directory Structure

*   **`pythonprogs/`**: The main repository of Python scripts. Organized into buckets of 1000 (e.g., `A000/`, `A001/`).
    *   File path format: `pythonprogs/Axxx/Axxxxxx.py`.
*   **`../oeisdata/seq/`**: (External) Raw OEIS data files (`.seq`) containing terms, offsets, and other metadata.
*   **`test.py`**: The core testing framework. It loads the code, mocks `load_oeis_data`, and attempts to verify `a(n)`, `first(n)`, or `is(n)` against known terms.
*   **`examine_sequence.py`**: The primary entry point for developers. It combines data fetching, code display, and testing into a single report.
*   **`extract_python_oeis.py`**: Utility to scrape/update Python code from raw OEIS data files.

## 2. Tooling & Usage

### `examine_sequence.py`
**Usage:** `uv run examine_sequence.py Axxxxxx`
**Purpose:**
1.  Fetches OEIS data (terms, name, offsets).
2.  Displays the extracted Python code from `pythonprogs/`.
3.  Runs `test.py` against the code.
4.  Provides a link to the OEIS page.

### `test.py`
**Usage:** `uv run test.py Axxxxxx`
**Logic:**
*   **Stubbing:** Mocks `Axxxxxx` references in the code to prevent infinite recursion or dependency issues (unless defined locally).
*   **Heuristics:** auto-detects function types:
    *   **`a(n)`**: Computes the n-th term.
    *   **`first(n)`**: Returns a list of the first n terms.
    *   **`is(n)`**: Returns boolean (membership check).
    *   **List Generators**: If a function returns a list, it is treated as `first(n)`.
*   **Guard Blocks:** Executes code within `if __name__ == '__main__':` as a fallback if no functions are callable.

## 3. Coding Conventions

When writing or fixing scripts, adhere to these naming conventions to ensure `test.py` can verify them automatically.

*   **`a(n)`**: Computes the **n-th term** (respecting the sequence offset).
    *   *Preferred* for simple sequences.
*   **`first(n)`** or **`list(n)`**: Returns a list of the **first n terms**.
    *   *Preferred* for sequences where computing `a(n)` requires previous terms (e.g., recursive sequences).
*   **`is(n)`** or **`is_seq(n)`**: Returns `True`/`False` if `n` is in the sequence.
*   **`Axxxxxx_list`**: A list variable containing known terms (supported by the tester).

### Indexing & Offsets
*   **OEIS implies 1-based indexing** for `a(n)` in its descriptions usually, but `test.py` passes the actual index `n`.
*   **Critical:** Ensure your function handles the **OEIS Offset**.
    *   If the sequence starts at `n=1`, `a(1)` should return the first term.
    *   If `n=0`, `a(0)` should return the first term.
    *   The `test.py` framework extracts the offset from the `.seq` file (`%O`) and aligns tests accordingly.

## 4. Common Issues & Fixes

### "Expected Integer, Got List"
*   **Cause:** The tester found a function (often named `Axxxxxx`) and tried to use it as `a(n)`, but it returned the whole sequence.
*   **Fix:** Rename the function to `Axxxxxx_list` or `first`, or ensure the "Last Resort" logic in `test.py` probes it correctly (already patched, but keep in mind).
*   **Fix (Code side):** Change the return to `sequence[n]` if it was meant to be `a(n)`.

### Offset Mismatches
*   **Cause:** OEIS data expects terms starting at index `1`, but Python list is 0-indexed, or the script generates an implicit `a(0)` term.
*   **Fix:** Adjust the return slice (e.g., `return sequence[1:]`) or the loop range to match the expected terms.

### Infinite Recursion / Timeout
*   **Cause:** `a(n)` calls `a(n-1)` without a base case, or calls the global `Axxxxxx` stub instead of the local function.
*   **Fix:** Ensure internal recursion calls the *defined function name*, not the A-number (unless self-referential via OEIS links). Use `@cache` or `@lru_cache` for recursion.

## 5. Philosophy (Condensed)
*   **Clarity > Golfing:** Code should be readable.
*   **No Input Validation:** Assume `n` is valid per the domain. Don't return `0` for invalid input; let it crash or be undefined.
*   **Minimal Comments:** Only explain complex math or algorithm tricks.

## 6. Workflow for Fixing Sequences
1.  Run `uv run examine_sequence.py Axxxxxx`.
2.  Identify the failure (Mismatch? Timeout? Error?).
3.  Edit `pythonprogs/.../Axxxxxx.py`.
    *   *Tip:* Use `replace` tool for targeted fixes.
    *   *Tip:* Rename functions to match conventions (`a`, `first`).
4.  Re-run `examine_sequence.py` to verify.