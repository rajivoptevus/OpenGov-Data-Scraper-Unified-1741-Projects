import os
import re
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
#ROOT_DIR = r"D:\Scraping_28_05_2026\OpenGov\downloads-Firsttime"

ROOT_DIR = r"D:\Scraping_28_05_2026\Opengov-DOWNLOADS_1741\downloads-Opengov"

#REPORT_DIR = r"D:\Scraping_28_05_2026\OpenGov\directory_report"

REPORT_DIR = r"D:\Scraping_28_05_2026\Opengov-DOWNLOADS_1741\reports"

os.makedirs(REPORT_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

LOG_FILE = os.path.join(
    REPORT_DIR,
    f"project_directory_report_{timestamp}.txt"
)

# =========================================================
# FIND PROJECT DIRECTORIES
# =========================================================

project_dirs = []

for item in os.listdir(ROOT_DIR):

    full_path = os.path.join(ROOT_DIR, item)

    if (
        os.path.isdir(full_path)
        and re.match(r"^\d+", item)   # starts with digits
    ):
        project_dirs.append(full_path)

project_dirs.sort()

# =========================================================
# PROCESS
# =========================================================

total_projects = 0
total_documents = 0
zero_file_projects = []

with open(LOG_FILE, "w", encoding="utf-8") as log:

    log.write("=" * 120 + "\n")
    log.write("PROJECT DIRECTORY REPORT\n")
    log.write("=" * 120 + "\n")
    log.write(f"Root Directory : {ROOT_DIR}\n")
    log.write(f"Generated At   : {datetime.now()}\n")
    log.write("=" * 120 + "\n\n")

    for project_path in project_dirs:

        project_id = os.path.basename(project_path)

        file_count = 0

        # Recursively count files
        for root, dirs, files in os.walk(project_path):

            for file in files:

                # Ignore JSON files
                if file.lower().endswith(".json"):
                    continue

                file_count += 1

        total_projects += 1
        total_documents += file_count

        if file_count == 0:
            zero_file_projects.append(project_id)

        log.write(
            f"{project_id:<15} --> {file_count} document(s)\n"
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    log.write("\n")
    log.write("=" * 120 + "\n")
    log.write("SUMMARY\n")
    log.write("=" * 120 + "\n")

    log.write(f"TOTAL PROJECT DIRECTORIES : {total_projects}\n")
    log.write(f"TOTAL DOCUMENTS           : {total_documents}\n")
    log.write(f"PROJECTS WITH 0 DOCUMENTS : {len(zero_file_projects)}\n")

    if zero_file_projects:

        log.write("\n")
        log.write("PROJECT IDS WITH NO DOCUMENTS\n")
        log.write("-" * 120 + "\n")

        for pid in zero_file_projects:
            log.write(f"{pid}\n")

print("\n" + "=" * 80)
print(f"Total Project Directories : {total_projects}")
print(f"Total Documents           : {total_documents}")
print(f"Report Saved To           : {LOG_FILE}")
print("=" * 80)