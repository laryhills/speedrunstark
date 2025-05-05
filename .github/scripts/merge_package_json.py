#!/usr/bin/env python3

import json
import sys
import os
from collections import OrderedDict # Use OrderedDict to preserve key order somewhat

# --- Configuration ---
# List of keys known to contain dependency objects
DEPENDENCY_KEYS = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]

# --- Helper Functions ---
def load_json_safe(filepath):
    """Loads JSON from a file, returns empty dict if file not found or invalid JSON."""
    if not os.path.exists(filepath):
        # Treat missing file (e.g., ancestor before package.json existed) as empty
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Use OrderedDict to better preserve original key order during load/dump
            return json.load(f, object_pairs_hook=OrderedDict)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading JSON from {filepath}: {e}", file=sys.stderr)
        # Return None to signal critical error during load
        return None
    except Exception as e:
        print(f"Unexpected error loading {filepath}: {e}", file=sys.stderr)
        return None


def merge_dependency_section(ancestor_deps, ours_deps, theirs_deps):
    """
    Merges dependency sections based on the rules:
    - Theirs wins version conflicts.
    - Keeps deps unique to ours.
    - Keeps deps unique to theirs.
    """
    if not isinstance(ancestor_deps, dict): ancestor_deps = {}
    if not isinstance(ours_deps, dict): ours_deps = {}
    if not isinstance(theirs_deps, dict): theirs_deps = {}

    # Start with ancestor, overwrite with theirs (theirs wins version conflicts)
    merged = OrderedDict({**ancestor_deps, **theirs_deps})

    # Add dependencies that are ONLY in ours (not in ancestor or theirs)
    for key, value in ours_deps.items():
        if key not in merged:
            merged[key] = value

    # Sort alphabetically for consistency, though OrderedDict preserves insertion mostly
    # return OrderedDict(sorted(merged.items())) # Optional: uncomment for strict alpha sort
    return merged


# --- Main Script Logic ---
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: merge_package_json.py <ancestor_file> <current_file> <other_file> [pathname]", file=sys.stderr)
        sys.exit(1)

    ancestor_filepath = sys.argv[1]
    current_filepath = sys.argv[2]  # This is '%A', the file Git expects us to modify
    other_filepath = sys.argv[3]
    pathname = sys.argv[4] if len(sys.argv) > 4 else "" # Optional %P

    # Load the three file versions
    ancestor_json = load_json_safe(ancestor_filepath)
    ours_json = load_json_safe(current_filepath)
    theirs_json = load_json_safe(other_filepath)

    # Check for critical load errors
    if ancestor_json is None or ours_json is None or theirs_json is None:
       print(f"Error: Failed to load one or more JSON files for '{pathname}'. Aborting merge.", file=sys.stderr)
       sys.exit(1) # Signal failure to Git

    # --- Perform the Merge ---

    # 1. Merge top-level keys: Start with ancestor, apply ours, then apply theirs.
    #    This makes 'theirs' win simple top-level key conflicts.
    merged_json = OrderedDict({**ancestor_json, **ours_json, **theirs_json})

    # 2. Merge specific dependency sections using our custom logic
    for dep_key in DEPENDENCY_KEYS:
        ancestor_deps = ancestor_json.get(dep_key, {})
        ours_deps = ours_json.get(dep_key, {})
        theirs_deps = theirs_json.get(dep_key, {})

        merged_deps_section = merge_dependency_section(ancestor_deps, ours_deps, theirs_deps)

        # Update the merged result, removing the section if it's empty
        if merged_deps_section:
            merged_json[dep_key] = merged_deps_section
        elif dep_key in merged_json:
            # Explicitly remove if merge resulted in empty and key exists from top-level merge
             del merged_json[dep_key]

    # --- Write Result ---
    try:
        with open(current_filepath, 'w', encoding='utf-8') as f:
            # Dump merged JSON back to the target file ('%A')
            # Use indent=2 for standard package.json formatting
            json.dump(merged_json, f, indent=2, ensure_ascii=False)
            f.write('\n') # Add trailing newline, common practice

        print(f"Successfully merged '{pathname}' using Python driver.", file=sys.stderr)
        sys.exit(0) # Signal SUCCESS to Git
    except Exception as e:
        print(f"Error writing merged file {current_filepath}: {e}", file=sys.stderr)
        sys.exit(1) # Signal FAILURE to Git