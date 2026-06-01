## OpenGov Data Scraper

Unified script that combines three original tools:

`download_opengov_files.py` - Download project documents and metadata 
`script.py` - Fix JSON files, add sections and followers 
`auto_followers.py` - Extract planholders/followers via API & scraping 

### How They Work in Sequence

1. Project Discovery -> Reads existing project IDs from source directory
2. API Fetch -> Calls OpenGov API for project details (from download script)
3. File Download -> Downloads all attachments to project folders
4. Followers Extraction -> Multi-method (API response → API endpoints → HTML scraping) from 
                           auto_followers.py
5. Sections Extraction -> Parses criteria and project sections (from script.py)
6. JSON Output -> Saves complete project.json with all data combined
7. Post-Processing -> Optional `--fix-followers` mode to update existing projects

### Key Improvements

- Single command instead of running three separate scripts
- Persistent checkpoints to resume interrupted downloads
- Multi-method follower extraction (highest success rate)
- Consolidated output (`all_projects.json` plus individual `project.json` files)

### Usage

```bash
# First run: Download all projects with followers
python Unified_OpenGov_Data_Scraper.py --only-missing

# Fix followers on existing projects (from script.py + auto_followers.py)
python Unified_OpenGov_Data_Scraper.py --fix-followers

# Process specific project only
python Unified_OpenGov_Data_Scraper.py --project-id 123456