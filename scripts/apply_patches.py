#!/usr/bin/env python3
"""
Reconstructs all difficulty_dataset files from the originals (cipi_file) and
the pre-generated patches in patches/.

Steps:
  1. Verify CIPI/scores.zip integrity
  2. Extract CIPI/scores.zip into CIPI/
  3. Verify cipi_file checksums               (metadata/checksums.csv)
  4. Apply patches to reconstruct dataset files
  5. Verify dataset_file checksums            (metadata/checksums.csv)

Run from anywhere; all paths are resolved relative to the repository root.
"""
import contextlib
import csv
import datetime
import hashlib
import os
import re
import sys
import zipfile

SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_DIR      = os.path.dirname(SCRIPTS_DIR)
CIPI_DIR      = os.path.join(REPO_DIR, "CIPI")
SCORES_ZIP    = os.path.join(CIPI_DIR, "scores.zip")
SCORES_ZIP_CS = os.path.join(CIPI_DIR, "scores.zip.sha256")
CHECKSUMS_CSV = os.path.join(REPO_DIR, "metadata", "checksums.csv")
PATCHES_DIR   = os.path.join(REPO_DIR, "patches")
LOGS_DIR      = os.path.join(REPO_DIR, "logs")

# ── helpers ───────────────────────────────────────────────────────────────────

def apply_forward_patch(original_file: str, patch_file: str, output_file: str) -> None:
    with open(original_file, "r", encoding="utf-8") as f:
        original_lines = f.readlines()
    with open(patch_file, "r", encoding="utf-8") as f:
        patch_content = f.read()

    result_lines = []
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


def step_header(n: int, title: str) -> None:
    print(f"\nStep {n}/5 — {title}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"apply_patches_{ts}.log")

    all_errors: list[tuple[str, str]] = []

    with open(log_path, "w", encoding="utf-8") as log:

        def L(msg: str = "") -> None:
            log.write(msg + "\n")
            log.flush()

        @contextlib.contextmanager
        def capture_stdout():
            """Redirect sys.stdout to the log file temporarily."""
            old = sys.stdout
            sys.stdout = log
            try:
                yield
            finally:
                sys.stdout = old

        def abort_step(ctx: str, errors: list[str]) -> None:
            """Record errors, write final summary to log, and exit."""
            all_errors.extend((ctx, e) for e in errors)
            L(f"\nAborted with {len(all_errors)} error(s):")
            for c, m in all_errors:
                L(f"  [{c}] {m}")
            print(f"\n{'='*60}")
            print(f"Aborted with {len(all_errors)} error(s). Check log for details.")
            print(f"Log: {log_path}")
            sys.exit(1)

        L(f"apply_patches.py — {ts}")
        L("=" * 60)

        # ── Step 1: verify scores.zip checksum ───────────────────────────
        step_header(1, "Verifying CIPI/scores.zip checksum")
        L("\n[Step 1] Verify CIPI/scores.zip checksum")
        L("-" * 40)

        step_errors: list[str] = []
        if not os.path.isfile(SCORES_ZIP):
            msg = f"File not found: {SCORES_ZIP}"
            L(f"  ERROR: {msg}")
            step_errors.append(msg)
            print_progress(1, 1, "ERROR — file not found")
            print(f"\n  scores.zip not found. Download it from:\n"
                  f"  https://doi.org/10.5281/zenodo.8037327\n"
                  f"  and place it at: {SCORES_ZIP}")
        elif not os.path.isfile(SCORES_ZIP_CS):
            msg = f"Checksum file not found: {SCORES_ZIP_CS}"
            L(f"  ERROR: {msg}")
            step_errors.append(msg)
            print_progress(1, 1, "ERROR — .sha256 not found")
        else:
            print_progress(0, 1, "Computing SHA-256…")
            actual = sha256_file(SCORES_ZIP)
            with open(SCORES_ZIP_CS, encoding="utf-8") as f:
                expected = f.read().split()[0]
            L(f"  expected : {expected}")
            L(f"  actual   : {actual}")
            if actual == expected:
                L("  ✓ OK")
                print_progress(1, 1, "OK")
            else:
                msg = (f"Hash mismatch — "
                       f"expected {expected[:16]}…  got {actual[:16]}…")
                L(f"  ERROR: {msg}")
                step_errors.append(msg)
                print_progress(1, 1, "HASH MISMATCH")

        if step_errors:
            abort_step("scores.zip", step_errors)

        # ── Step 2: extract scores.zip ────────────────────────────────────
        step_header(2, "Extracting CIPI/scores.zip")
        L("\n[Step 2] Extract CIPI/scores.zip")
        L("-" * 40)

        try:
            with zipfile.ZipFile(SCORES_ZIP, "r") as zf:
                members = zf.namelist()
                for j, member in enumerate(members):
                    zf.extract(member, CIPI_DIR)
                    print_progress(j + 1, len(members))
            L(f"  ✓ Extracted {len(members)} entries to {CIPI_DIR}")
        except Exception as exc:
            msg = f"Extraction failed: {exc}"
            L(f"  ERROR: {msg}")
            abort_step("scores.zip", [msg])

        # ── load catalogue ────────────────────────────────────────────────
        with open(CHECKSUMS_CSV, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        total = len(rows)

        # ── Step 3: verify cipi checksums ─────────────────────────────────
        step_header(3, "Verifying cipi_file checksums")
        L("\n[Step 3] Verify cipi_file checksums")
        L("-" * 40)

        step_errors = []
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

        # ── Step 4: apply patches ─────────────────────────────────────────
        step_header(4, "Applying patches to reconstruct dataset files")
        L("\n[Step 4] Apply patches")
        L("-" * 40)

        step_errors = []
        for i, row in enumerate(rows):
            cipi_rel    = row["cipi_file"].strip()
            dataset_rel = row["dataset_file"].strip()
            cipi_abs    = os.path.join(CIPI_DIR, cipi_rel)
            dataset_abs = os.path.join(REPO_DIR, dataset_rel)
            patch_abs   = os.path.join(PATCHES_DIR, patch_name_for(dataset_rel))

            print_progress(i, total)

            missing = []
            if not os.path.isfile(cipi_abs):
                missing.append(f"cipi: {cipi_rel}")
            if not os.path.isfile(patch_abs):
                missing.append(f"patch: {os.path.basename(patch_abs)}")
            if missing:
                L(f"  [SKIP] {dataset_rel} — {'; '.join(missing)}")
                step_errors.append(dataset_rel)
                continue

            os.makedirs(os.path.dirname(dataset_abs), exist_ok=True)
            try:
                with capture_stdout():
                    apply_forward_patch(cipi_abs, patch_abs, dataset_abs)
                L(f"  [OK]   {dataset_rel}")
            except Exception as exc:
                L(f"  ERROR: {dataset_rel}: {exc}")
                step_errors.append(dataset_rel)

        print_progress(total, total,
                       f"{len(step_errors)} error(s)" if step_errors else "All OK")
        L(f"\n  Summary: {total - len(step_errors)}/{total} files reconstructed")
        if step_errors:
            abort_step("apply_patch", step_errors)

        # ── Step 5: verify dataset checksums ──────────────────────────────
        step_header(5, "Verifying dataset_file checksums")
        L("\n[Step 5] Verify dataset_file checksums")
        L("-" * 40)

        step_errors = []
        for i, row in enumerate(rows):
            dataset_rel   = row["dataset_file"].strip()
            expected_hash = row["dataset_sha256"].strip()
            dataset_abs   = os.path.join(REPO_DIR, dataset_rel)

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
        L(f"\n  Summary: {total - len(step_errors)}/{total} dataset files verified")
        if step_errors:
            abort_step("dataset_file", step_errors)

        # ── log final summary ─────────────────────────────────────────────
        L("\n" + "=" * 60)
        L("\nAll steps completed successfully.")

    # ── stdout final summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("All steps completed successfully.")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
