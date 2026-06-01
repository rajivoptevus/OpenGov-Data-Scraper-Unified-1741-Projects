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

#TREE

```text
OpenGov-Data-Scraper-Unified-1741-Projects
│
├── .gitignore
├── README.md
├── Unified_OpenGov_Data_Scraper.py
├── download_opengov_files.py
├── auto_followers.py
├── count_of_docs.py
├── script.py
│
├── downloads-Opengov
│   ├── all_projects.json
│   ├── download_state.json
│   ├── manifest.json
│   │
│   ├── 100427
│   │   └── file.pdf
│   │   └── project.json
│   │
│   ├── 101968
│   │   └── file.pdf
│   │   └── project.json
│   │
│   ├── 270404
│   │   └── file.pdf
│   │   └── project.json
│   │
│   ├── 270414
│   │   └── file.pdf
│   │   └── project.json
│   │
│   ├── 270416
│   │   ├── 270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_01_-_Project_Solicitation_& 
            _Instructions_for_Bidders.pdf
│   │   ├── 270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_02_-_Bidding_Documents.pdf
│   │   ├── 270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_03_-_Contract_Forms.pdf
│   │   ├──  
         270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_04_-_General_and_Supplementary_Conditions.pdf
│   │   ├── 270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_05_-_General_Requirements.
            pdf
│   │   ├── 
            270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_06_-_Technical_Specifications.pdf
│   │   ├── 270416__Bid_26-6988_RYY_South_Apron_Drainage_Repairs_Division_07_-_Construction_Plans.pdf
│   │   └── project.json
│   │
│   └── ... (1,700+ project directories)
│
├── logs
│   ├── scraper_20260530_183648.log
│   └── scraper_20260531_112742.log
│
└── reports
    ├── project_directory_report_20260531_015642.txt
    ├── project_directory_report_20260531_023848.txt
    └── ...
```
