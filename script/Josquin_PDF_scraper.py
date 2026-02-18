import os
import json
import requests
import subprocess
import logging
from collections import defaultdict

# ==============================
# CONFIG
# ==============================

BASE_URL = "https://josquin.stanford.edu/cgi-bin/jrp"
WORKS_JSON = "works.json"

SECTION_DIR = "jrp_section_pdfs"
MERGED_DIR = "jrp_merged_works"

MIN_VALID_SIZE = 15000  # 15 KB threshold to reject blank PDFs

os.makedirs(SECTION_DIR, exist_ok=True)
os.makedirs(MERGED_DIR, exist_ok=True)

# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    filename="pdf_scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

missing_or_failed = []

# ==============================
# PDF VALIDATION
# ==============================

def is_valid_pdf(path):
    if not os.path.exists(path):
        return False

    if os.path.getsize(path) < MIN_VALID_SIZE:
        return False

    try:
        subprocess.run(
            ["pdfinfo", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


# ==============================
# DOWNLOAD FUNCTION
# ==============================

def download_pdf(section_id, version):

    if version == "no_edit":
        url = f"{BASE_URL}?a=notationNoEditText&f={section_id}"
    else:
        url = f"{BASE_URL}?a=notationEditText&f={section_id}"

    output_path = os.path.join(
        SECTION_DIR,
        f"{section_id}-{version}.pdf"
    )

    # Skip valid existing file
    if os.path.exists(output_path) and is_valid_pdf(output_path):
        print(f"✓ Skipping existing: {output_path}")
        return output_path

    # Remove invalid existing file
    if os.path.exists(output_path):
        print(f"⚠ Removing invalid file: {output_path}")
        os.remove(output_path)

    print(f"Downloading {output_path}")

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)

        # Size check
        if os.path.getsize(output_path) < MIN_VALID_SIZE:
            print(f"❌ Blank/tiny PDF: {output_path}")
            logging.error(f"Tiny PDF: {output_path}")
            missing_or_failed.append(output_path)
            os.remove(output_path)
            return None

        # Structural validation
        if not is_valid_pdf(output_path):
            print(f"❌ Corrupt PDF: {output_path}")
            logging.error(f"Corrupt PDF: {output_path}")
            missing_or_failed.append(output_path)
            os.remove(output_path)
            return None

        return output_path

    except Exception as e:
        print(f"❌ Download failed: {output_path}")
        logging.error(f"Download failed {output_path}: {e}")
        missing_or_failed.append(output_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


# ==============================
# MERGE FUNCTION
# ==============================

def merge_work(section_files, work_base, version):

    valid_files = []

    for path in section_files:
        if path and is_valid_pdf(path):
            valid_files.append(path)
        else:
            logging.warning(f"Skipping corrupt section: {path}")

    if len(valid_files) < 2:
        return  # nothing to merge

    output_path = os.path.join(
        MERGED_DIR,
        f"{work_base}-{version}.pdf"
    )

    print(f"Merging {output_path}")

    try:
        subprocess.run(
            ["pdfunite"] + valid_files + [output_path],
            check=True
        )

        if not is_valid_pdf(output_path):
            logging.error(f"Merged PDF corrupt: {output_path}")
            os.remove(output_path)
            missing_or_failed.append(output_path)

    except subprocess.CalledProcessError:
        logging.error(f"Merge failed: {work_base}-{version}")
        missing_or_failed.append(output_path)


# ==============================
# MAIN
# ==============================

def main():

    with open(WORKS_JSON, "r") as f:
        works = json.load(f)

    # Group ALL works by base ID (first 7 chars)
    work_groups = defaultdict(list)

    for work in works:
        work_id = work["WORK_ID"]

        # Download both versions
        download_pdf(work_id, "no_edit")
        download_pdf(work_id, "edit")

        # Group by base work ID (Gas0301, Jos0402, etc.)
        base = work_id[:7]
        work_groups[base].append(work_id)

    # ==========================
    # Merge multi-section works
    # ==========================

    for base, sections in work_groups.items():

        # Only merge if multiple sections exist
        if len(sections) < 2:
            continue

        print(f"\nProcessing multi-section work {base}")

        sections.sort()

        # no_edit merge
        no_edit_paths = [
            os.path.join(SECTION_DIR, f"{sec}-no_edit.pdf")
            for sec in sections
        ]
        merge_work(no_edit_paths, base, "no_edit")

        # edit merge
        edit_paths = [
            os.path.join(SECTION_DIR, f"{sec}-edit.pdf")
            for sec in sections
        ]
        merge_work(edit_paths, base, "edit")

    # ==========================
    # Write missing report
    # ==========================

    if missing_or_failed:
        with open("missing_or_failed.txt", "w") as f:
            for item in missing_or_failed:
                f.write(item + "\n")

        print("\n⚠ Some files failed. See missing_or_failed.txt")
    else:
        print("\n✓ All files processed successfully.")


if __name__ == "__main__":
    main()