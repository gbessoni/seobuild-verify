#!/usr/bin/env python3
"""
SEOBUILD-VERIFY tag parser.

Usage:
    python3 verify.py parse <file_or_glob>    Extract all verification tags as JSON
    python3 verify.py summary <file_or_glob>  Print a quick count summary
    python3 verify.py replace <file> <json>   Apply replacements from a JSON file

Tag formats recognized (any uppercase tag label):
    {{VERIFY: claim | suggested source}}
    {{RESEARCH NEEDED: claim | suggested source}}
    {{SOURCE NEEDED: claim | suggested source}}
    {{MANUAL CHECK: claim | tried: ...}}
    {{FACT CHECK: ...}}, {{CITE: ...}}, {{CITATION NEEDED: ...}}, etc.

Any tag matching {{<UPPERCASE LABEL>: ...}} is treated as a verification tag,
excluding a small allowlist of non-verification template tags (e.g. TOC).
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

# Match any {{LABEL: claim | source}} where LABEL is uppercase words (A-Z, spaces, -, _).
TAG_PATTERN = re.compile(
    r"\{\{([A-Z][A-Z0-9 _\-]*?):\s*(.+?)\s*(?:\|\s*(.+?)\s*)?\}\}"
)

# Labels to ignore -- these are not verification tags.
IGNORED_LABELS = {"TOC", "TABLE OF CONTENTS", "INCLUDE", "TEMPLATE"}


def parse_file(filepath: str) -> list[dict]:
    """Extract all verification tags from a single file."""
    tags = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, IOError) as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return tags

    in_code_block = False
    in_pre = False

    for line_num, line in enumerate(lines, start=1):
        # Skip code blocks
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if "<pre" in line.lower():
            in_pre = True
        if "</pre>" in line.lower():
            in_pre = False
            continue
        if in_code_block or in_pre:
            continue

        for match in TAG_PATTERN.finditer(line):
            tag_type = match.group(1).strip()
            if tag_type in IGNORED_LABELS:
                continue
            claim = match.group(2).strip()
            suggested_source = (match.group(3) or "").strip()

            # Detect if tag is inside an HTML attribute
            before = line[: match.start()]
            in_attr = bool(
                re.search(r'(?:href|src|alt|title|content|value)\s*=\s*["\'][^"\']*$', before)
            )

            tags.append(
                {
                    "file": str(filepath),
                    "line": line_num,
                    "tag_type": tag_type,
                    "claim": claim,
                    "suggested_source": suggested_source,
                    "raw": match.group(0),
                    "in_attribute": in_attr,
                }
            )

    return tags


def parse_targets(target: str) -> list[dict]:
    """Parse tags from a file path or glob pattern."""
    all_tags = []

    # Expand user home dir
    target = os.path.expanduser(target)

    # Check if it's a glob pattern
    if any(c in target for c in ["*", "?", "["]):
        files = sorted(glob.glob(target, recursive=True))
    elif os.path.isdir(target):
        files = sorted(
            glob.glob(os.path.join(target, "**", "*.html"), recursive=True)
            + glob.glob(os.path.join(target, "**", "*.md"), recursive=True)
        )
    elif os.path.isfile(target):
        files = [target]
    else:
        print(f"Error: {target} is not a file, directory, or valid glob", file=sys.stderr)
        return all_tags

    for f in files:
        all_tags.extend(parse_file(f))

    return all_tags


def apply_replacements(filepath: str, replacements_json: str):
    """Apply tag replacements from a JSON array.

    Each replacement object:
    {
        "raw": "{{VERIFY: ...}}",
        "replacement": "new text<!-- source: URL -->",
        "line": 42
    }
    """
    with open(replacements_json, "r") as f:
        replacements = json.load(f)

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    for rep in replacements:
        raw = rep["raw"]
        replacement = rep["replacement"]
        content = content.replace(raw, replacement, 1)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Applied {len(replacements)} replacements to {filepath}")


def summary(tags: list[dict]):
    """Print a summary of tags found."""
    if not tags:
        print("No verification tags found.")
        return

    files = set(t["file"] for t in tags)
    by_type = {}
    for t in tags:
        by_type.setdefault(t["tag_type"], []).append(t)

    print(f"Files scanned: {len(files)}")
    print(f"Total tags: {len(tags)}")
    for tag_type in sorted(by_type.keys()):
        print(f"  {tag_type}: {len(by_type[tag_type])}")


def main():
    parser = argparse.ArgumentParser(description="SEO-AGI verification tag parser")
    sub = parser.add_subparsers(dest="command")

    p_parse = sub.add_parser("parse", help="Extract tags as JSON")
    p_parse.add_argument("target", help="File path, directory, or glob pattern")

    p_summary = sub.add_parser("summary", help="Print tag count summary")
    p_summary.add_argument("target", help="File path, directory, or glob pattern")

    p_replace = sub.add_parser("replace", help="Apply replacements from JSON")
    p_replace.add_argument("file", help="File to modify")
    p_replace.add_argument("json_file", help="JSON file with replacements")

    args = parser.parse_args()

    if args.command == "parse":
        tags = parse_targets(args.target)
        print(json.dumps(tags, indent=2))
    elif args.command == "summary":
        tags = parse_targets(args.target)
        summary(tags)
    elif args.command == "replace":
        apply_replacements(args.file, args.json_file)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
