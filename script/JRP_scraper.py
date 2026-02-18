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

WORKS_URL = (
    "https://raw.githubusercontent.com/"
    "josquin-research-project/jrp-website/"
    "refs/heads/main/_includes/metadata/works.json"
)

WORKS_CACHE = "works_cache.json"

SCORES_ROOT = "../scores"

MIN_VALID_SIZE = 15000  # reject blank Ghostscript PDFs

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
# WORKS.JSON FETCH
# ==============================

def load_works():
    """
    Fetch works.json from GitHub.
    Cache locally to avoid repeated downloads.
    """

    print("Fetching works.json from GitHub...")

    try:
        r = requests.get(WORKS_URL, timeout=30)
        r.raise_for_status()
        works = r.json()

        # Cache locally
        with open(WORKS_CACHE, "w") as f:
            json.dump(works, f)

        return works

    except Exception as e:
        print("⚠ Failed to fetch remote works.json. Trying cache...")
        logging.error(f"Failed to fetch works.json: {e}")

        if os.path.exists(WORKS_CACHE):
            with open(WORKS_CACHE, "r") as f:
                return json.load(f)

        raise RuntimeError("No works.json available (remote or cached).")


# ==============================
# HELPERS
# ==============================

def composer_folder(work_id):
    composer_code = work_id[:3]
    path = os.path.join(SCORES_ROOT, composer_code)
    os.makedirs(path, exist_ok=True)
    return path


def pdf_path(work_id, version):
    folder = composer_folder(work_id)
    return os.path.join(folder, f"{work_id}-{version}.pdf")


def merged_pdf_path(work_base, version):
    folder = composer_folder(work_base)
    return os.path.join(folder, f"{work_base}-{version}.pdf")


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

def download_pdf(work_id, version):

    if version == "no_edit":
        url = f"{BASE_URL}?a=notationNoEditText&f={work_id}"
    else:
        url = f"{BASE_URL}?a=notationEditText&f={work_id}"

    output_path = pdf_path(work_id, version)

    if os.path.exists(output_path) and is_valid_pdf(output_path):
        print(f"✓ Skipping existing: {output_path}")
        return output_path

    if os.path.exists(output_path):
        print(f"⚠ Removing invalid file: {output_path}")
        os.remove(output_path)

    print(f"Downloading {output_path}")

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)

        if os.path.getsize(output_path) < MIN_VALID_SIZE:
            print(f"❌ Blank/tiny PDF: {output_path}")
            logging.error(f"Tiny PDF: {output_path}")
            missing_or_failed.append(output_path)
            os.remove(output_path)
            return None

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

def merge_work(section_ids, work_base, version):

    valid_files = []

    for sec in section_ids:
        path = pdf_path(sec, version)
        if path and is_valid_pdf(path):
            valid_files.append(path)
        else:
            logging.warning(f"Skipping corrupt section: {path}")

    if len(valid_files) < 2:
        return

    output_path = merged_pdf_path(work_base, version)

    if os.path.exists(output_path) and is_valid_pdf(output_path):
        print(f"✓ Merged already exists: {output_path}")
        return

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

    works = load_works()

    work_groups = defaultdict(list)

    for work in works:
        work_id = work["WORK_ID"]

        download_pdf(work_id, "no_edit")
        download_pdf(work_id, "edit")

        base = work_id[:7]
        work_groups[base].append(work_id)

    for base, sections in work_groups.items():

        if len(sections) < 2:
            continue

        print(f"\nProcessing multi-section work {base}")

        sections.sort()

        merge_work(sections, base, "no_edit")
        merge_work(sections, base, "edit")

    if missing_or_failed:
        with open("missing_or_failed.txt", "w") as f:
            for item in missing_or_failed:
                f.write(item + "\n")

        print("\n⚠ Some files failed. See missing_or_failed.txt")
    else:
        print("\n✓ All files processed successfully.")


if __name__ == "__main__":
    main()