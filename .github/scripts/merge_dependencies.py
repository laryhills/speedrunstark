#!/usr/bin/env python3

import json
import sys
import os
import traceback
from collections import OrderedDict

# Attempt to import TOML libraries
try:
    import tomli
except ImportError:
    print("Error: 'tomli' library not found. Please install it (`pip install tomli`)", file=sys.stderr)
    sys.exit(127) # Indicate dependency missing

try:
    import tomli_w
except ImportError:
    print("Error: 'tomli_w' library not found. Please install it (`pip install tomli_w`)", file=sys.stderr)
    sys.exit(127) # Indicate dependency missing


# --- Configuration ---
# List of keys known to contain dependency *tables/objects* in either format
# Adjust this list if Scarb.toml uses other dependency keys
DEPENDENCY_KEYS = ["dependencies", "dev-dependencies", "peerDependencies", "optionalDependencies"]

# --- Helper Functions ---

def load_config(filepath):
    """Loads JSON or TOML from a file based on its likely content or name."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return OrderedDict() # Treat missing or empty file as empty

    try:
        with open(filepath, 'rb') as f: # Read in binary mode for tomli
            # Try TOML first as it's stricter
            try:
                return tomli.load(f)
            except tomli.TOMLDecodeError:
                # If TOML fails, rewind and try JSON
                f.seek(0)
                try:
                    # Read as text for JSON, assuming utf-8
                    # Need to reopen in text mode or decode bytes
                    f.close() # Close binary handle first
                    with open(filepath, 'r', encoding='utf-8') as f_text:
                       return json.load(f_text, object_pairs_hook=OrderedDict)
                except json.JSONDecodeError as json_err:
                    print(f"Error: File {filepath} is not valid TOML or JSON: {json_err}", file=sys.stderr)
                    return None # Signal critical error
                except Exception as e: # Catch other potential issues reopening/reading
                    print(f"Error reading {filepath} as JSON after TOML failure: {e}", file=sys.stderr)
                    return None
            except Exception as e: # Catch other potential issues reading TOML
                print(f"Unexpected error reading {filepath} as TOML: {e}", file=sys.stderr)
                return None

    except FileNotFoundError:
        return OrderedDict() # Should be caught by os.path.exists, but be safe
    except Exception as e:
        print(f"Unexpected error opening/reading {filepath}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None


def dump_config(data, filepath, original_format='json'):
    """Writes data as JSON or TOML, guessing format if needed."""
    format_to_write = original_format
    if format_to_write not in ['json', 'toml']:
        # Basic guess if format wasn't determined reliably
        format_to_write = 'toml' if filepath.lower().endswith('.toml') else 'json'

    try:
        if format_to_write == 'toml':
            with open(filepath, 'wb') as f: # Write in binary mode for tomli_w
                tomli_w.dump(data, f)
        else: # Default to JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n') # Add trailing newline
        return True
    except Exception as e:
        print(f"Error writing merged file {filepath} as {format_to_write}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False


def merge_dependency_section(ancestor_deps, ours_deps, theirs_deps):
    """
    Merges dependency sections (dictionaries/tables).
    - Theirs wins version conflicts.
    - Keeps deps unique to ours.
    - Keeps deps unique to theirs.
    """
    # Ensure inputs are dicts, default to empty OrderedDict if not
    def ensure_dict(d):
        return d if isinstance(d, dict) else OrderedDict()

    ancestor_deps = ensure_dict(ancestor_deps)
    ours_deps = ensure_dict(ours_deps)
    theirs_deps = ensure_dict(theirs_deps)

    # Start with ancestor, overwrite with theirs (theirs wins version conflicts)
    merged = OrderedDict({**ancestor_deps, **theirs_deps})

    # Add dependencies that are ONLY in ours
    for key, value in ours_deps.items():
        if key not in merged: # If not in ancestor or theirs already
            merged[key] = value

    # Sort alphabetically by key for consistent output? TOML often preserves order.
    # For now, rely on OrderedDict's insertion order preservation primarily.
    # merged = OrderedDict(sorted(merged.items())) # Optional strict sort
    return merged


# --- Main Script Logic ---
if __name__ == "__main__":
    if len(sys.argv) < 5: # Now expect %P as the 4th arg (index 4)
        print("Usage: merge_config.py <ancestor_file> <current_file> <other_file> <pathname>", file=sys.stderr)
        sys.exit(1)

    ancestor_filepath = sys.argv[1]
    current_filepath = sys.argv[2]  # This is '%A', the file Git expects us to modify
    other_filepath = sys.argv[3]
    pathname = sys.argv[4]          # This is '%P', the original filename

    print(f"Attempting custom merge for: {pathname}", file=sys.stderr)

    # Determine original format primarily from the pathname
    original_format = 'toml' if pathname.lower().endswith('.toml') else 'json'

    # Load the three file versions
    ancestor_conf = load_config(ancestor_filepath)
    ours_conf = load_config(current_filepath)
    theirs_conf = load_config(other_filepath)

    # Check for critical load errors
    if ancestor_conf is None or ours_conf is None or theirs_conf is None:
       print(f"Error: Failed to load one or more config files for '{pathname}'. Aborting merge.", file=sys.stderr)
       sys.exit(1) # Signal failure to Git

    # --- Perform the Merge ---

    # 1. Merge top-level keys: Start with ancestor, apply ours, then apply theirs.
    #    This makes 'theirs' win simple top-level key conflicts.
    #    Use OrderedDict to try and preserve order where possible.
    merged_conf = OrderedDict()
    merged_conf.update(ancestor_conf)
    merged_conf.update(ours_conf)
    merged_conf.update(theirs_conf)


    # 2. Merge specific dependency sections using our custom logic
    for dep_key in DEPENDENCY_KEYS:
        ancestor_deps = ancestor_conf.get(dep_key, OrderedDict())
        ours_deps = ours_conf.get(dep_key, OrderedDict())
        theirs_deps = theirs_conf.get(dep_key, OrderedDict())

        # Only proceed if at least one side actually has this section defined
        if ancestor_deps or ours_deps or theirs_deps:
             merged_deps_section = merge_dependency_section(ancestor_deps, ours_deps, theirs_deps)

             # Update the merged result, removing the section if it's empty
             if merged_deps_section:
                 merged_conf[dep_key] = merged_deps_section
             elif dep_key in merged_conf:
                 # Explicitly remove if merge resulted in empty and key exists from top-level merge
                 del merged_conf[dep_key]

    # --- Write Result ---
    if dump_config(merged_conf, current_filepath, original_format):
        print(f"Successfully merged '{pathname}' using Python driver.", file=sys.stderr)
        sys.exit(0) # Signal SUCCESS to Git
    else:
        # dump_config already printed error
        print(f"Merge failed for '{pathname}'. Falling back to standard merge.", file=sys.stderr)
        sys.exit(1) # Signal FAILURE to Git