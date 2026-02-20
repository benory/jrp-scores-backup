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
# WORKS.JSON FETCH + CACHE
# ==============================

def load_works():

    old_works = {}

    if os.path.exists(WORKS_CACHE):
        with open(WORKS_CACHE, "r") as f:
            old_list = json.load(f)
            old_works = {w["WORK_ID"]: w for w in old_list}

    print("Fetching works.json from GitHub...")

    r = requests.get(WORKS_URL, timeout=30)
    r.raise_for_status()
    new_list = r.json()

    new_works = {w["WORK_ID"]: w for w in new_list}

    return old_works, new_works, new_list


# ==============================
# PATH HELPERS
# ==============================

def composer_folder(work_id):
    composer_code = work_id[:3]
    path = os.path.join(SCORES_ROOT, composer_code)
    os.makedirs(path, exist_ok=True)
    return path


def pdf_path(work_id, version):
    return os.path.join(
        composer_folder(work_id),
        f"{work_id}-{version}.pdf"
    )


def merged_pdf_path(work_base, version):
    return os.path.join(
        composer_folder(work_base),
        f"{work_base}-{version}.pdf"
    )


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

def download_pdf(work_id, version, force=False):

    if version == "no_edit":
        url = f"{BASE_URL}?a=notationNoEditText&f={work_id}"
    else:
        url = f"{BASE_URL}?a=notationEditText&f={work_id}"

    output_path = pdf_path(work_id, version)

    if (
        not force
        and os.path.exists(output_path)
        and is_valid_pdf(output_path)
    ):
        print(f"✓ Skipping existing: {output_path}")
        return output_path

    if os.path.exists(output_path):
        print(f"⚠ Removing old/invalid file: {output_path}")
        os.remove(output_path)

    print(f"Downloading {output_path}")

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)

        if os.path.getsize(output_path) < MIN_VALID_SIZE:
            raise RuntimeError("PDF too small")

        if not is_valid_pdf(output_path):
            raise RuntimeError("PDF validation failed")

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
        if is_valid_pdf(path):
            valid_files.append(path)

    if len(valid_files) < 2:
        return

    output_path = merged_pdf_path(work_base, version)

    if os.path.exists(output_path) and is_valid_pdf(output_path):
        return

    print(f"Merging {output_path}")

    try:
        subprocess.run(
            ["pdfunite"] + valid_files + [output_path],
            check=True
        )

        if not is_valid_pdf(output_path):
            raise RuntimeError("Merged PDF invalid")

    except Exception as e:
        logging.error(f"Merge failed {work_base}-{version}: {e}")
        missing_or_failed.append(output_path)
        if os.path.exists(output_path):
            os.remove(output_path)


# ==============================
# METADATA DIFF REPORT
# ==============================

def report_metadata_differences(old_works, new_works):

    old_ids = set(old_works.keys())
    new_ids = set(new_works.keys())

    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)

    updated = []
    unchanged = []

    for work_id in sorted(old_ids & new_ids):
        old_date = old_works[work_id].get("DATE_CHANGED", "")
        new_date = new_works[work_id].get("DATE_CHANGED", "")

        if old_date != new_date:
            updated.append((work_id, old_date, new_date))
        else:
            unchanged.append(work_id)

    print("\n========== METADATA DIFF ==========")

    print(f"Added works:   {len(added)}")
    print(f"Removed works: {len(removed)}")
    print(f"Updated works: {len(updated)}")
    print(f"Unchanged:     {len(unchanged)}")

    if added:
        print("\nNEW WORKS:")
        for w in added:
            print(f"  + {w}")

    if removed:
        print("\nREMOVED WORKS:")
        for w in removed:
            print(f"  - {w}")

    if updated:
        print("\nUPDATED WORKS:")
        for w, old_d, new_d in updated:
            print(f"  * {w}: {old_d} → {new_d}")

    print("===================================\n")

    return added, removed, updated

# ==============================
# MAIN
# ==============================

def main():

    old_works, new_works, new_list = load_works()

    
    added, removed, updated = report_metadata_differences(
        old_works, new_works
    )

    work_groups = defaultdict(list)

    for work_id, work in new_works.items():

        base = work_id[:7]
        work_groups[base].append(work_id)

        force_download = False

        if work_id not in old_works:
            print(f"NEW work: {work_id}")
            force_download = True
        else:
            old_date = old_works[work_id].get("DATE_CHANGED", "")
            new_date = work.get("DATE_CHANGED", "")

            if old_date != new_date:
                force_download = True

        download_pdf(work_id, "no_edit", force=force_download)
        download_pdf(work_id, "edit", force=force_download)

    # Merge multi-section works
    for base, sections in work_groups.items():

        if len(sections) < 2:
            continue

        sections.sort()

        merge_work(sections, base, "no_edit")
        merge_work(sections, base, "edit")

    # Update cache
    with open(WORKS_CACHE, "w") as f:
        json.dump(new_list, f, indent=2)

    if missing_or_failed:
        with open("missing_or_failed.txt", "w") as f:
            for item in missing_or_failed:
                f.write(item + "\n")
        print("\n⚠ Some files failed. See missing_or_failed.txt")
    else:
        print("\n✓ All files processed successfully.")


if __name__ == "__main__":
    main()