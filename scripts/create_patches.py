#!/usr/bin/env python3
"""
Generates patches for all entries in checksums.csv, then verifies each
patch by applying it and comparing the result against the dataset_file.

Steps:
  1. Verify cipi_file checksums               (metadata/checksums.csv)
  2. Verify dataset_file checksums            (metadata/checksums.csv)
  3. Create patches
  4. Verify patches (apply + compare)

Run from anywhere; all paths are resolved relative to the repository root.
"""
import contextlib
import csv
import datetime
import difflib
import filecmp
import hashlib
import os
import re
import sys
import tempfile

SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_DIR      = os.path.dirname(SCRIPTS_DIR)
CIPI_DIR      = os.path.join(REPO_DIR, "CIPI")
CHECKSUMS_CSV = os.path.join(REPO_DIR, "metadata", "checksums.csv")
PATCHES_DIR   = os.path.join(REPO_DIR, "patches")
DATASET_DIR   = os.path.join(REPO_DIR, "difficulty_dataset")
LOGS_DIR      = os.path.join(REPO_DIR, "logs")

# ── helpers ───────────────────────────────────────────────────────────────────

def create_forward_patch(original_file: str, modified_file: str, output_file: str) -> None:
    with open(original_file, "r", encoding="utf-8") as f:
        original_lines = f.readlines()
    with open(modified_file, "r", encoding="utf-8") as f:
        modified_lines = f.readlines()

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=original_file,
        tofile=modified_file,
        lineterm="",
        n=0,
    )

    with open(output_file, "w", encoding="utf-8") as out:
        out.write(f"--- {original_file}\n")
        out.write(f"+++ {modified_file}\n")
        for line in diff:
            if line.startswith("---") or line.startswith("+++"):
                continue
            elif line.startswith("@@"):
                out.write(line + "\n")
            elif line.startswith("-"):
                pass
            elif line.startswith("+"):
                stripped = line[1:].strip()
                if stripped:
                    out.write(line)
            elif line.startswith(" "):
                if line.strip():
                    out.write(line + "\n")


def apply_forward_patch(original_file: str, patch_file: str, output_file: str) -> None:
    with open(original_file, "r", encoding="utf-8") as f:
        original_lines = f.readlines()
    with open(patch_file, "r", encoding="utf-8") as f:
        patch_content = f.read()

    result_lines: list[str] = []
    orig_line_num = 0
    patch_lines = patch_content.split("\n")
    i = 0

    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_count = int(match.group(4)) if match.group(4) else 1
                if old_count == 0:
                    while orig_line_num < old_start:
                        result_lines.append(original_lines[orig_line_num])
                        orig_line_num += 1
                else:
                    while orig_line_num < old_start - 1:
                        result_lines.append(original_lines[orig_line_num])
                        orig_line_num += 1
                    orig_line_num += old_count
                i += 1
                lines_added = 0
                while i < len(patch_lines) and lines_added < new_count:
                    if patch_lines[i].startswith("@@"):
                        break
                    elif patch_lines[i].startswith("+"):
                        result_lines.append(patch_lines[i][1:] + "\n")
                        lines_added += 1
                        i += 1
                    else:
                        i += 1
                continue
        i += 1

    while orig_line_num < len(original_lines):
        result_lines.append(original_lines[orig_line_num])
        orig_line_num += 1

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(result_lines)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_name_for(dataset_file: str) -> str:
    stem = os.path.splitext(os.path.basename(dataset_file))[0]
    return stem + ".patch"


_BAR_WIDTH = 40


def _bar(current: int, total: int) -> str:
    pct = current / total if total else 1.0
    filled = int(_BAR_WIDTH * pct)
    return f"[{'█' * filled}{'░' * (_BAR_WIDTH - filled)}] {current}/{total}"


def print_progress(current: int, total: int, label: str = "") -> None:
    end = "\n" if current >= total else "\r"
    line = f"  {_bar(current, total)}  {label:<50}"
    print(f"{line:<100}", end=end, flush=True)


def step_header(n: int, total_steps: int, title: str) -> None:
    print(f"\nStep {n}/{total_steps} — {title}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(PATCHES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"create_patches_{ts}.log")

    all_errors: list[tuple[str, str]] = []

    with open(log_path, "w", encoding="utf-8") as log:

        def L(msg: str = "") -> None:
            log.write(msg + "\n")
            log.flush()

        def abort_step(ctx: str, errors: list[str]) -> None:
            all_errors.extend((ctx, e) for e in errors)
            L(f"\nAborted with {len(all_errors)} error(s):")
            for c, m in all_errors:
                L(f"  [{c}] {m}")
            print(f"\n{'='*60}")
            print(f"Aborted with {len(all_errors)} error(s). Check log for details.")
            print(f"Log: {log_path}")
            sys.exit(1)

        L(f"create_patches.py — {ts}")
        L("=" * 60)

        # ── load catalogue ────────────────────────────────────────────────
        with open(CHECKSUMS_CSV, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        total = len(rows)

        # ── Step 1: verify cipi_file checksums ────────────────────────────
        step_header(1, 4, "Verifying cipi_file checksums")
        L("\n[Step 1] Verify cipi_file checksums")
        L("-" * 40)

        step_errors: list[str] = []
        seen: dict[str, bool] = {}
        for i, row in enumerate(rows):
            cipi_rel      = row["cipi_file"].strip()
            expected_hash = row["cipi_sha256"].strip()
            cipi_abs      = os.path.join(CIPI_DIR, cipi_rel)
            print_progress(i, total)

            if cipi_rel in seen:
                L(f"  [DUP]  {cipi_rel} (already verified)")
                continue

            if not os.path.isfile(cipi_abs):
                msg = f"Not found: {cipi_rel}"
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
                seen[cipi_rel] = False
                continue

            actual_hash = sha256_file(cipi_abs)
            if expected_hash and actual_hash != expected_hash:
                msg = (f"Hash mismatch: {cipi_rel}  "
                       f"expected {expected_hash[:16]}…  got {actual_hash[:16]}…")
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
                seen[cipi_rel] = False
            else:
                L(f"  ✓  {cipi_rel}")
                seen[cipi_rel] = True

        print_progress(total, total,
                       f"{len(step_errors)} error(s)" if step_errors else "All OK")
        L(f"\n  Summary: {total - len(step_errors)}/{total} cipi files OK")
        if step_errors:
            abort_step("cipi_file", step_errors)

        # ── Step 2: verify dataset_file checksums ─────────────────────────
        step_header(2, 4, "Verifying dataset_file checksums")
        L("\n[Step 2] Verify dataset_file checksums")
        L("-" * 40)

        step_errors = []
        for i, row in enumerate(rows):
            dataset_rel   = row["dataset_file"].strip()
            expected_hash = row["dataset_sha256"].strip()
            dataset_abs   = os.path.join(DATASET_DIR, dataset_rel)
            print_progress(i, total)

            if not os.path.isfile(dataset_abs):
                msg = f"Not found: {dataset_rel}"
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
                continue

            actual_hash = sha256_file(dataset_abs)
            if expected_hash and actual_hash != expected_hash:
                msg = (f"Hash mismatch: {dataset_rel}  "
                       f"expected {expected_hash[:16]}…  got {actual_hash[:16]}…")
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
            else:
                L(f"  ✓  {dataset_rel}")

        print_progress(total, total,
                       f"{len(step_errors)} error(s)" if step_errors else "All OK")
        L(f"\n  Summary: {total - len(step_errors)}/{total} dataset files OK")
        if step_errors:
            abort_step("dataset_file", step_errors)

        # ── Step 3: create patches ────────────────────────────────────────
        step_header(3, 4, "Creating patches")
        L("\n[Step 3] Create patches")
        L("-" * 40)

        step_errors = []
        for i, row in enumerate(rows):
            cipi_rel    = row["cipi_file"].strip()
            dataset_rel = row["dataset_file"].strip()
            cipi_abs    = os.path.join(CIPI_DIR, cipi_rel)
            dataset_abs = os.path.join(DATASET_DIR, dataset_rel)
            patch_abs   = os.path.join(PATCHES_DIR, patch_name_for(dataset_rel))

            print_progress(i, total)

            try:
                create_forward_patch(cipi_abs, dataset_abs, patch_abs)
                L(f"  [OK]   {dataset_rel}")
            except Exception as exc:
                msg = f"{dataset_rel}: {exc}"
                L(f"  ERROR: {msg}")
                step_errors.append(msg)

        print_progress(total, total,
                       f"{len(step_errors)} error(s)" if step_errors else "All OK")
        L(f"\n  Summary: {total - len(step_errors)}/{total} patches created")
        if step_errors:
            abort_step("create_patch", step_errors)

        # ── Step 4: verify patches (apply + compare) ─────────────────────
        step_header(4, 4, "Verifying patches (apply + compare)")
        L("\n[Step 4] Verify patches")
        L("-" * 40)

        step_errors = []
        for i, row in enumerate(rows):
            cipi_rel    = row["cipi_file"].strip()
            dataset_rel = row["dataset_file"].strip()
            cipi_abs    = os.path.join(CIPI_DIR, cipi_rel)
            dataset_abs = os.path.join(DATASET_DIR, dataset_rel)
            patch_abs   = os.path.join(PATCHES_DIR, patch_name_for(dataset_rel))

            print_progress(i, total)

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".xml", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp_path = tmp.name

                apply_forward_patch(cipi_abs, patch_abs, tmp_path)
                if filecmp.cmp(tmp_path, dataset_abs, shallow=False):
                    L(f"  ✓  {dataset_rel}")
                else:
                    msg = f"Reconstructed file differs: {dataset_rel}"
                    L(f"  ERROR: {msg}")
                    step_errors.append(msg)
            except Exception as exc:
                msg = f"{dataset_rel}: {exc}"
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        print_progress(total, total,
                       f"{len(step_errors)} error(s)" if step_errors else "All OK")
        L(f"\n  Summary: {total - len(step_errors)}/{total} patches verified")
        if step_errors:
            abort_step("verify_patch", step_errors)

        # ── log final summary ─────────────────────────────────────────────
        L("\n" + "=" * 60)
        L("\nAll steps completed successfully.")

    # ── stdout final summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("All patches created and verified successfully.")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
