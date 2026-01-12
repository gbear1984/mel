                               #!/usr/bin/env python3
"""
path_info.py
Scan a directory tree and output a CSV of folders containing files with given extensions.
Counts files per extension per folder.

Example:
  python3 path_info.py -r /show/seq01 -e exr tx mb hip -o ~/Desktop/Path_info.csv
"""

import argparse
import csv
import os
from collections import defaultdict, OrderedDict

def normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    if ext.startswith("."):
        ext = ext[1:]
    return ext

def scan(root: str, exts: list[str], absolute: bool, follow_symlinks: bool, exclude_dirs: set[str]):
    # counts[(folder, ext)] = int
    counts = defaultdict(int)
    seen_folders = set()

    root = os.path.abspath(root) if absolute else os.path.normpath(root)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # prune excluded dirs in-place (prevents walking them)
        if exclude_dirs:
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for fn in filenames:
            # fast extension check
            dot = fn.rfind(".")
            if dot == -1:
                continue
            ext = fn[dot + 1 :].lower()
            if ext not in exts:
                continue

            folder = dirpath if absolute else os.path.relpath(dirpath, start=root)
            if folder == ".":
                folder = "./"  # nicer root label for relative mode

            counts[(folder, ext)] += 1
            seen_folders.add(folder)

    return counts, seen_folders

def main():
    ap = argparse.ArgumentParser(description="Map folders containing certain file types and output CSV counts.")
    ap.add_argument("-r", "--root", required=True, help="Root folder to scan")
    ap.add_argument("-e", "--ext", nargs="+", required=True,
                    help="Extensions to match (e.g. exr tx mb ma abc hip). Dot optional.")
    ap.add_argument("-o", "--out", required=True, help="Output CSV path")
    ap.add_argument("--absolute", action="store_true", help="Write absolute folder paths")
    ap.add_argument("--follow-symlinks", action="store_true", help="Follow symlinks during walk")
    ap.add_argument("--exclude-dir", action="append", default=[],
                    help="Directory name to exclude (repeatable). Example: --exclude-dir .git --exclude-dir renders")
    ap.add_argument("--sort", choices=["path", "total", "none"], default="path",
                    help="Sort output rows by path, total matches, or not at all")

    args = ap.parse_args()

    exts = [normalize_ext(x) for x in args.ext]
    # keep unique extensions while preserving order
    exts = list(OrderedDict.fromkeys(exts))
    exclude_dirs = set(args.exclude_dir or [])

    counts, seen = scan(
        root=args.root,
        exts=set(exts),
        absolute=args.absolute,
        follow_symlinks=args.follow_symlinks,
        exclude_dirs=exclude_dirs
    )

    # build rows
    rows = []
    for folder in seen:
        row = {"path": folder}
        total = 0
        for ext in exts:
            c = counts.get((folder, ext), 0)
            row[ext] = c
            total += c
        row["_total"] = total
        rows.append(row)

    # sort
    if args.sort == "path":
        rows.sort(key=lambda r: r["path"])
    elif args.sort == "total":
        rows.sort(key=lambda r: r["_total"], reverse=True)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    # write CSV
    fieldnames = ["path"] + exts
    with open(os.path.expanduser(args.out), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, 0) for k in fieldnames})

if __name__ == "__main__":
    main()
