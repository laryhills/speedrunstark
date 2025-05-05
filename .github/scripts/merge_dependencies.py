#!/usr/bin/env python3

import json
import sys
import os
import traceback

from collections import OrderedDict

# --- Built-in TOML Reader (Python 3.11+) ---
try:
    import tomllib
except ImportError:
    print("Error: 'tomllib' not found. This script requires Python 3.11+.", file=sys.stderr)
    sys.exit(127)

# --- External TOML Writer ---
try:
    import tomli_w
except ImportError:
    print("Error: 'tomli_w' library not found. Please install it (`pip install tomli_w`)", file=sys.stderr)
    sys.exit(127)


# --- Configuration ---
DEPENDENCY_KEYS = ["dependencies", "dev-dependencies", "peerDependencies", "optionalDependencies"]

# --- Helper Functions ---

def load_config(filepath):
    """Loads JSON or TOML from a file based on its likely content or name."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return OrderedDict()

    try:
        with open(filepath, 'rb') as f: # Read in binary mode for tomllib
            try:
                return tomllib.load(f)
            except tomllib.TOMLDecodeError:
                f.seek(0)
                try:
                    f.close()
                    with open(filepath, 'r', encoding='utf-8') as f_text:
                       return json.load(f_text, object_pairs_hook=OrderedDict)
                except json.JSONDecodeError as json_err:
                    print(f"Error: File {filepath} is not valid TOML or JSON: {json_err}", file=sys.stderr)
                    return None
                except Exception as e:
                    print(f"Error reading {filepath} as JSON after TOML failure: {e}", file=sys.stderr)
                    return None
            except Exception as e:
                print(f"Unexpected error reading {filepath} as TOML: {e}", file=sys.stderr)
                return None

    except FileNotFoundError:
        return OrderedDict()
    except Exception as e:
        print(f"Unexpected error opening/reading {filepath}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None


def dump_config(data, filepath, original_format='json'):
    """Writes data as JSON or TOML, guessing format if needed."""
    format_to_write = original_format
    if format_to_write not in ['json', 'toml']:
        format_to_write = 'toml' if filepath.lower().endswith('.toml') else 'json'

    try:
        if format_to_write == 'toml':
            with open(filepath, 'wb') as f:
                tomli_w.dump(data, f)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n')
        return True
    except Exception as e:
        print(f"Error writing merged file {filepath} as {format_to_write}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False


def merge_dependency_section(ancestor_deps, ours_deps, theirs_deps):
    """ Merges dependency sections (dictionaries/tables). """
    def ensure_dict(d):
        return d if isinstance(d, dict) else OrderedDict()

    ancestor_deps = ensure_dict(ancestor_deps)
    ours_deps = ensure_dict(ours_deps)
    theirs_deps = ensure_dict(theirs_deps)

    merged = OrderedDict({**ancestor_deps, **theirs_deps})

    for key, value in ours_deps.items():
        if key not in merged:
            merged[key] = value

    return merged

# --- Main Script Logic ---
if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: merge_config.py <ancestor_file> <current_file> <other_file> <pathname>", file=sys.stderr)
        sys.exit(1)

    ancestor_filepath = sys.argv[1]
    current_filepath = sys.argv[2]
    other_filepath = sys.argv[3]
    pathname = sys.argv[4]          # This is '%P', the original filename

    print(f"Attempting custom merge for: {pathname}", file=sys.stderr)

    original_format = 'toml' if pathname.lower().endswith('.toml') else 'json'

    ancestor_conf = load_config(ancestor_filepath)
    ours_conf = load_config(current_filepath)
    theirs_conf = load_config(other_filepath)

    if ancestor_conf is None or ours_conf is None or theirs_conf is None:
       print(f"Error: Failed to load one or more config files for '{pathname}'. Aborting merge.", file=sys.stderr)
       sys.exit(1)

    merged_conf = OrderedDict()
    merged_conf.update(ancestor_conf)
    merged_conf.update(ours_conf)
    merged_conf.update(theirs_conf)

    for dep_key in DEPENDENCY_KEYS:
        ancestor_deps = ancestor_conf.get(dep_key, OrderedDict())
        ours_deps = ours_conf.get(dep_key, OrderedDict())
        theirs_deps = theirs_conf.get(dep_key, OrderedDict())

        if ancestor_deps or ours_deps or theirs_deps:
             merged_deps_section = merge_dependency_section(ancestor_deps, ours_deps, theirs_deps)
             if merged_deps_section:
                 merged_conf[dep_key] = merged_deps_section
             elif dep_key in merged_conf:
                 del merged_conf[dep_key]


    if dump_config(merged_conf, current_filepath, original_format):
        print(f"Successfully merged '{pathname}' using Python driver.", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"Merge failed for '{pathname}'. Falling back to standard merge.", file=sys.stderr)
        sys.exit(1)