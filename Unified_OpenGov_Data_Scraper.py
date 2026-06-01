#!/usr/bin/env python3
"""
Unified OpenGov Data Scraper - Complete Version with Followers
===============================================================
Downloads all project documents, extracts complete metadata, and fetches followers.
Uses existing project IDs from downloads-Firsttime directory.
"""

import json
import os
import re
import argparse
import time
import signal
import sys
import logging
from datetime import datetime
from urllib.parse import urljoin
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import List, Dict, Optional, Any, Tuple, Set

# Optional imports
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    print("Warning: BeautifulSoup not installed. Install with: pip install beautifulsoup4")

try:
    import requests
except ImportError:
    requests = None
    print("Warning: requests not installed. Install with: pip install requests")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Your working cookies from the original script
DEFAULT_COOKIES = "ajs_anonymous_id=51714eb5-8de2-45ba-84e1-6fa3931c2f0d; koa.sid=2DA1L376LWf0yyWr2eFSX0TEGm1f6cFs; koa.sid.sig=4z1QA72WmN6DbFNfOQEHi8bzOz4; ajs_user_id=rajiv.patnaik@optevus.com; ajs_group_id=vend-95298276"

BASE_URL = "https://api.procurement.opengov.com/api/v1"

# Source directory with existing project IDs
SOURCE_DIR = Path("D:/Scraping_28_05_2026/OpenGov/downloads-Firsttime")
OUTPUT_DIR = Path("downloads-Opengov")
LOG_DIR = OUTPUT_DIR / "logs"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

COOKIES = os.environ.get("OPENGOV_COOKIES", DEFAULT_COOKIES)
OPENGOV_USER = os.environ.get("OPENGOV_USER")
OPENGOV_PASS = os.environ.get("OPENGOV_PASS")

DEFAULT_HEADERS = {
    "Cookie": COOKIES,
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html, */*",
}

PARTIAL_SUFFIX = ".part"
STATE_PATH = OUTPUT_DIR / "download_state.json"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
CONSOLIDATED_PATH = OUTPUT_DIR / "all_projects.json"

REQUEST_DELAY = 0.5
CHECKPOINT_INTERVAL = 5
SHUTDOWN_REQUESTED = False

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('OpenGovScraper')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"scraper_{timestamp}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger

logger = None

def signal_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    if not SHUTDOWN_REQUESTED:
        SHUTDOWN_REQUESTED = True
        logger.warning("\n⚠️  Shutdown signal received. Saving checkpoint...")

def register_signal_handlers():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def cookies_to_dict(cookies_str: str) -> Dict[str, str]:
    """Convert cookie string to dictionary"""
    cookies = {}
    for item in cookies_str.split('; '):
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key] = value
    return cookies

def load_state() -> Dict:
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state.setdefault("downloaded", 0)
            state.setdefault("skipped", 0)
            state.setdefault("errors", [])
            state.setdefault("completed_files", [])
            state.setdefault("processed_projects", [])
            return state
        except Exception:
            pass
    return {"downloaded": 0, "skipped": 0, "errors": [], "completed_files": [], "processed_projects": []}

def save_state(state: Dict) -> None:
    state["last_updated"] = datetime.now().isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

def sanitize_filename(value: str, fallback: str = "download") -> str:
    text = value or fallback
    text = text.strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._")
    if not text:
        text = fallback
    return text[:180]

def attachment_to_filename(project_id: int, attachment: Dict, fallback: str = "file") -> str:
    if isinstance(attachment, dict):
        filename = attachment.get("filename") or attachment.get("name") or attachment.get("path")
        if filename:
            name = Path(filename).name
            if name:
                return f"{project_id}__{sanitize_filename(name, fallback)}"
        if attachment.get("title"):
            return f"{project_id}__{sanitize_filename(attachment['title'], fallback)}"
    return f"{project_id}__{sanitize_filename(fallback)}"

def safe_get(dct: Dict, keys: List[str], default: str = "") -> Any:
    for k in keys:
        if not k:
            continue
        if isinstance(dct, dict) and k in dct and dct[k] is not None:
            return dct[k]
    return default

def make_request(url: str, method: str = "GET", payload: Dict = None) -> Optional[Dict]:
    data = None
    headers = dict(DEFAULT_HEADERS)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = Request(url, data=data, headers=headers, method=method)
    
    for attempt in range(3):
        try:
            with urlopen(req, timeout=60) as response:
                body = response.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)
        except HTTPError as exc:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
        except URLError as exc:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    return None

def download_url(url: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return "exists"
    
    temp_destination = destination.parent / (destination.name + PARTIAL_SUFFIX)
    if temp_destination.exists():
        temp_destination.unlink(missing_ok=True)
    
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = USER_AGENT
    req = Request(url, headers=headers)
    
    with urlopen(req, timeout=120) as response:
        data = response.read()
    
    temp_destination.write_bytes(data)
    temp_destination.replace(destination)
    return "downloaded"

def extract_attachments(project_detail: Dict) -> List[Dict]:
    urls = []
    seen = set()
    
    doc = project_detail.get("documentAttachment")
    if isinstance(doc, dict) and doc.get("url"):
        urls.append(doc)
    
    for attachment in project_detail.get("attachments", []) or []:
        if isinstance(attachment, dict) and attachment.get("url"):
            urls.append(attachment)
    
    for addendum in project_detail.get("addendums", []) or []:
        for attachment in addendum.get("attachments", []) or []:
            if isinstance(attachment, dict) and attachment.get("url"):
                urls.append(attachment)
    
    result = []
    for item in urls:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            result.append(item)
    return result

def extract_sections(project_detail: Dict) -> Dict:
    sections = {}
    if "projectSections" in project_detail:
        for section in project_detail.get("projectSections", []):
            section_title = section.get("title", "Untitled Section")
            section_content = []
            for criterion in project_detail.get("criteria", []):
                if criterion.get("project_section_id") == section.get("id"):
                    content = {
                        "title": criterion.get("title", ""),
                        "description": criterion.get("description", ""),
                    }
                    if content["title"] or content["description"]:
                        section_content.append(content)
            if section_content:
                sections[section_title] = section_content
    return sections

# ============================================================================
# ENHANCED FOLLOWER EXTRACTION (from auto_followers.py)
# ============================================================================

def get_government_code(project_detail: Dict, project_link: str = "") -> Optional[str]:
    """Extract government code from project data"""
    # Try from API response
    government = project_detail.get("government") or {}
    if isinstance(government, dict):
        govcode = government.get("code") or government.get("slug")
        if govcode:
            return govcode
    
    # Try from project link
    if project_link:
        match = re.search(r'portal/([^/]+)/projects', project_link)
        if match:
            return match.group(1)
    
    # Try from raw data
    if "raw" in project_detail:
        gov_raw = project_detail["raw"].get("government", {})
        if isinstance(gov_raw, dict):
            return gov_raw.get("code")
    
    return None

def fetch_followers_via_api(project_id: int, govcode: str) -> List[Dict]:
    """Fetch followers using API endpoints (from auto_followers.py)"""
    if requests is None:
        return []
    
    endpoints_to_try = [
        f"https://api.procurement.opengov.com/api/v1/project/{project_id}/planholders",
        f"https://api.procurement.opengov.com/api/v1/project/{project_id}/followers",
        f"https://api.procurement.opengov.com/api/v1/projects/{project_id}/planholders",
        f"https://procurement.opengov.com/api/projects/{project_id}/planholders",
        f"https://api.procurement.opengov.com/api/v1/vendor/projects/{project_id}/followers",
    ]
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": f"https://procurement.opengov.com/portal/{govcode}/projects/{project_id}",
    }
    
    cookies_dict = cookies_to_dict(COOKIES)
    
    for url in endpoints_to_try:
        try:
            response = requests.get(url, headers=headers, cookies=cookies_dict, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                followers = []
                
                # Parse different response formats
                if isinstance(data, list):
                    for item in data:
                        follower = parse_follower_item(item)
                        if follower:
                            followers.append(follower)
                elif isinstance(data, dict):
                    # Try common keys
                    for key in ['planholders', 'followers', 'data', 'results', 'items']:
                        if key in data:
                            items = data[key] if isinstance(data[key], list) else [data[key]]
                            for item in items:
                                follower = parse_follower_item(item)
                                if follower:
                                    followers.append(follower)
                            if followers:
                                break
                
                if followers:
                    logger.debug(f"  Found {len(followers)} followers via API: {url.split('/')[-1]}")
                    return followers
                    
        except Exception as e:
            logger.debug(f"  API endpoint failed: {url} - {e}")
            continue
    
    return []

def fetch_followers_via_scraping(project_id: int, govcode: str) -> List[Dict]:
    """Scrape followers from HTML page (from auto_followers.py)"""
    if BeautifulSoup is None or requests is None:
        return []
    
    url = f"https://procurement.opengov.com/portal/{quote(str(govcode))}/projects/{project_id}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        followers = []
        
        # Method 1: Look for planholders table
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 1:
                # Check if this looks like a followers table
                header_row = rows[0] if rows else None
                if header_row:
                    headers_text = [th.get_text(" ", strip=True).lower() for th in header_row.find_all(["th", "td"])]
                    if any(word in ' '.join(headers_text) for word in ['vendor', 'company', 'planholder', 'follower']):
                        for row in rows[1:]:
                            cells = row.find_all(["td", "th"])
                            if len(cells) >= 2:
                                follower = {
                                    "vendor": cells[0].get_text(" ", strip=True) if len(cells) > 0 else "",
                                    "contact": cells[1].get_text(" ", strip=True) if len(cells) > 1 else "",
                                    "designation": cells[2].get_text(" ", strip=True) if len(cells) > 2 else "",
                                }
                                if follower["vendor"] or follower["contact"]:
                                    followers.append(follower)
        
        # Method 2: Look for div-based planholder lists
        if not followers:
            planholder_sections = soup.find_all(["div", "section"], class_=re.compile(r"(planholder|follower|vendor-list|plan-holder)", re.I))
            for section in planholder_sections:
                items = section.find_all(["div", "li"], class_=re.compile(r"(item|entry|vendor|company)", re.I))
                for item in items:
                    vendor_elem = item.find(class_=re.compile(r"(vendor|company|name|business)", re.I))
                    contact_elem = item.find(class_=re.compile(r"(contact|email|person)", re.I))
                    if vendor_elem:
                        follower = {
                            "vendor": vendor_elem.get_text(" ", strip=True),
                            "contact": contact_elem.get_text(" ", strip=True) if contact_elem else "",
                            "designation": "",
                        }
                        followers.append(follower)
        
        if followers:
            logger.debug(f"  Found {len(followers)} followers via scraping")
        
        return followers
        
    except Exception as e:
        logger.debug(f"  Scraping error: {e}")
        return []

def parse_follower_item(item: Dict) -> Optional[Dict]:
    """Parse follower item from various formats"""
    if not isinstance(item, dict):
        return None
    
    # Try different field names
    vendor = (
        item.get('vendorName') or 
        item.get('name') or 
        item.get('company') or 
        item.get('vendor') or 
        item.get('organization')
    )
    
    contact = (
        item.get('contactName') or 
        item.get('contact') or 
        item.get('email') or 
        item.get('contactEmail')
    )
    
    designation = (
        item.get('designation') or 
        item.get('type') or 
        item.get('title') or 
        item.get('role') or
        item.get('certification')
    )
    
    # If vendor is a nested dict, extract name
    if isinstance(vendor, dict):
        vendor = vendor.get('name') or vendor.get('doingBusinessAs') or vendor.get('businessName') or str(vendor)
    
    # If contact is a nested dict, extract email
    if isinstance(contact, dict):
        contact = contact.get('email') or contact.get('contact') or str(contact)
    
    if not vendor and not contact:
        return None
    
    return {
        "vendor": str(vendor) if vendor else "",
        "contact": str(contact) if contact else "",
        "designation": str(designation) if designation else ""
    }

def get_followers_for_project(project_id: int, project_detail: Dict, project_link: str = "") -> List[Dict]:
    """Get followers using multiple methods (enhanced version)"""
    followers = []
    
    # Method 1: Check if followers already in API response
    if "followers" in project_detail and project_detail["followers"]:
        for f in project_detail["followers"]:
            if isinstance(f, dict):
                follower = parse_follower_item(f)
                if follower and (follower["vendor"] or follower["contact"]):
                    followers.append(follower)
        if followers:
            logger.debug(f"  Found {len(followers)} followers from API response")
            return followers
    
    # Method 2: Check planholders in API response
    if "planholders" in project_detail and project_detail["planholders"]:
        for f in project_detail["planholders"]:
            if isinstance(f, dict):
                follower = parse_follower_item(f)
                if follower and (follower["vendor"] or follower["contact"]):
                    followers.append(follower)
        if followers:
            logger.debug(f"  Found {len(followers)} planholders from API response")
            return followers
    
    # Method 3: Try API endpoints
    govcode = get_government_code(project_detail, project_link)
    if govcode:
        logger.debug(f"  Govcode: {govcode}")
        followers = fetch_followers_via_api(project_id, govcode)
        if followers:
            return followers
        time.sleep(REQUEST_DELAY)
    
    # Method 4: Try HTML scraping
    if govcode:
        followers = fetch_followers_via_scraping(project_id, govcode)
        if followers:
            return followers
    
    return followers

# ============================================================================
# PROJECT ID MANAGEMENT
# ============================================================================

def get_project_ids_from_existing_directory() -> List[int]:
    """Read project IDs from the existing downloads-Firsttime directory"""
    project_ids = []
    
    if not SOURCE_DIR.exists():
        logger.error(f"Source directory not found: {SOURCE_DIR}")
        logger.info("Please update SOURCE_DIR path in the script or use --source-dir")
        return []
    
    logger.info(f"Scanning directory: {SOURCE_DIR}")
    
    for item in SOURCE_DIR.iterdir():
        if item.is_dir():
            try:
                project_id = int(item.name)
                project_ids.append(project_id)
            except ValueError:
                continue
    
    project_ids.sort()
    logger.info(f"Found {len(project_ids)} project IDs in {SOURCE_DIR}")
    return project_ids

def get_existing_projects_from_output_directory() -> Tuple[Set[int], Set[int]]:
    """Scan output directory for existing projects"""
    completed = set()
    partial = set()
    
    if not OUTPUT_DIR.exists():
        return completed, partial
    
    for d in OUTPUT_DIR.iterdir():
        if d.is_dir() and d.name.isdigit():
            try:
                project_id = int(d.name)
            except ValueError:
                continue
            
            if (d / "project.json").exists():
                completed.add(project_id)
            elif any(d.iterdir()):
                partial.add(project_id)
    
    return completed, partial

# ============================================================================
# PROJECT PROCESSING
# ============================================================================

def process_single_project(project_id: int, output_dir: Path, state: Dict, 
                          skip_download: bool = False, force_refresh: bool = False) -> Tuple[bool, Dict]:
    """Process a single project with enhanced followers extraction"""
    logger.debug(f"Processing project {project_id}...")
    
    # Check if already processed (unless force refresh)
    if not force_refresh and project_id in state.get("processed_projects", []):
        logger.debug(f"Project {project_id} already processed, skipping...")
        return True, {"project_id": project_id, "status": "already_processed"}
    
    # Fetch project details
    try:
        project_detail = make_request(f"{BASE_URL}/project/{project_id}")
        if not project_detail:
            error_msg = f"Failed to fetch project {project_id}"
            logger.error(error_msg)
            state["errors"].append((project_id, error_msg))
            save_state(state)
            return False, {}
    except Exception as e:
        error_msg = f"Error fetching project {project_id}: {e}"
        logger.error(error_msg)
        state["errors"].append((project_id, error_msg))
        save_state(state)
        return False, {}
    
    # Extract attachments
    attachments = extract_attachments(project_detail)
    
    # Build project link
    project_link = project_detail.get("projectUrl") or project_detail.get("link") or ""
    if not project_link:
        govcode = get_government_code(project_detail)
        if govcode:
            project_link = f"https://procurement.opengov.com/portal/{quote(str(govcode))}/projects/{project_id}"
    
    # Download attachments
    downloaded_files = []
    if not skip_download:
        for attachment in attachments:
            filename = attachment_to_filename(project_id, attachment)
            destination = output_dir / str(project_id) / filename
            
            try:
                status = download_url(attachment["url"], destination)
                if status == "downloaded":
                    state["downloaded"] += 1
                    state["completed_files"].append(str(destination.resolve()))
                downloaded_files.append({
                    "title": attachment.get("title") or attachment.get("filename") or "",
                    "file_path": str(destination),
                    "status": status,
                })
                save_state(state)
                time.sleep(0.2)  # Small delay between downloads
            except Exception as exc:
                logger.error(f"  Error downloading {filename}: {exc}")
                state["errors"].append((project_id, str(exc)))
                save_state(state)
    
    # Extract followers (ENHANCED)
    logger.debug(f"  Extracting followers for project {project_id}...")
    followers = get_followers_for_project(project_id, project_detail, project_link)
    
    # Extract metadata
    metadata = {
        "project_id": project_id,
        "project_title": safe_get(project_detail, ["title", "projectTitle"]) or "",
        "project_link": project_link,
        "organization": safe_get(project_detail, ["organization", "organizationName"]) or "",
        "state": safe_get(project_detail, ["state", "contactState"]) or "",
        "status": safe_get(project_detail, ["status", "projectStatus"]) or "",
        "release_date": safe_get(project_detail, ["releaseDate", "releaseProjectDate", "postedAt"]) or "",
        "due_date": safe_get(project_detail, ["dueDate", "proposalDeadline"]) or "",
        "posted_at": safe_get(project_detail, ["postedAt"]) or "",
        "financial_id": safe_get(project_detail, ["financialId"]) or "",
        "summary": safe_get(project_detail, ["summary"]) or "",
        "background": safe_get(project_detail, ["background"]) or "",
        "followers": followers,
        "sections": extract_sections(project_detail),
        "downloaded_files": downloaded_files,
        "total_attachments": len(attachments),
        "processed_at": datetime.now().isoformat(),
        "raw": project_detail,  # Keep raw for reference
    }
    
    # Save project metadata
    project_dir = output_dir / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_json_path = project_dir / "project.json"
    project_json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    
    # Update state
    if project_id not in state["processed_projects"]:
        state["processed_projects"].append(project_id)
    save_state(state)
    
    follower_count = len(followers) if followers else 0
    logger.info(f"✓ Project {project_id}: {len(downloaded_files)} files, {follower_count} followers")
    
    return True, metadata

# ============================================================================
# FIX EXISTING PROJECTS (Add missing followers)
# ============================================================================

def fix_existing_projects(verbose: bool = False) -> None:
    """Scan existing projects and add missing followers"""
    logger.info("="*60)
    logger.info("FIXING EXISTING PROJECTS - ADDING MISSING FOLLOWERS")
    logger.info("="*60)
    
    if not OUTPUT_DIR.exists():
        logger.error(f"Output directory {OUTPUT_DIR} does not exist.")
        return
    
    project_dirs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    logger.info(f"Found {len(project_dirs)} project directories")
    
    fixed_count = 0
    followers_added = 0
    
    for i, project_dir in enumerate(project_dirs, 1):
        project_id = int(project_dir.name)
        project_json_path = project_dir / "project.json"
        
        if verbose:
            logger.info(f"\n[{i}/{len(project_dirs)}] Checking project {project_id}...")
        
        try:
            with open(project_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if followers are missing or empty
            existing_followers = data.get('followers', [])
            if existing_followers and len(existing_followers) > 0:
                if verbose:
                    logger.info(f"  ✓ Already has {len(existing_followers)} followers")
                continue
            
            logger.info(f"  Fetching followers for project {project_id}...")
            
            # Get project detail from raw or fetch new
            if 'raw' in data and data['raw']:
                project_detail = data['raw']
            else:
                project_detail = make_request(f"{BASE_URL}/project/{project_id}")
                if project_detail:
                    data['raw'] = project_detail
            
            if project_detail:
                project_link = data.get('project_link', '')
                followers = get_followers_for_project(project_id, project_detail, project_link)
                
                if followers:
                    data['followers'] = followers
                    with open(project_json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    fixed_count += 1
                    followers_added += len(followers)
                    logger.info(f"  ✓ Added {len(followers)} followers to project {project_id}")
                else:
                    logger.info(f"  No followers found for project {project_id}")
            
            time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            logger.error(f"  ✗ Error processing project {project_id}: {e}")
    
    logger.info("="*60)
    logger.info(f"FIX COMPLETE:")
    logger.info(f"  - Projects updated: {fixed_count}")
    logger.info(f"  - Total followers added: {followers_added}")
    logger.info("="*60)

# ============================================================================
# MAIN
# ============================================================================

def main():
    global logger, REQUEST_DELAY, SHUTDOWN_REQUESTED, SOURCE_DIR
    
    parser = argparse.ArgumentParser(description="Unified OpenGov Data Scraper - Complete with Followers")
    parser.add_argument("--project-id", type=int, help="Process a specific project ID")
    parser.add_argument("--start-id", type=int, help="Only process projects with id >= START_ID")
    parser.add_argument("--end-id", type=int, help="Only process projects with id <= END_ID")
    parser.add_argument("--only-missing", action="store_true", help="Process only projects missing project.json")
    parser.add_argument("--dry-run", action="store_true", help="Show which projects would be processed")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed output")
    parser.add_argument("--skip-download", action="store_true", help="Skip downloading files")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API requests")
    parser.add_argument("--reset", action="store_true", help="Reset checkpoint and start fresh")
    parser.add_argument("--source-dir", type=str, help="Source directory with existing project IDs")
    parser.add_argument("--fix-followers", action="store_true", help="Fix existing projects by adding missing followers")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh of already processed projects")
    
    args = parser.parse_args()
    
    # Update source directory if provided
    if args.source_dir:
        SOURCE_DIR = Path(args.source_dir)
    
    # Setup logging
    logger = setup_logging()
    REQUEST_DELAY = args.delay
    register_signal_handlers()
    
    # Handle fix-followers mode
    if args.fix_followers:
        fix_existing_projects(args.verbose)
        return
    
    logger.info("="*60)
    logger.info("Unified OpenGov Data Scraper Started")
    logger.info("="*60)
    logger.info(f"Source directory (project IDs): {SOURCE_DIR}")
    logger.info(f"Output directory: {OUTPUT_DIR.resolve()}")
    
    # Get project IDs
    if args.project_id:
        project_ids = [args.project_id]
        logger.info(f"Using single project ID: {args.project_id}")
    else:
        project_ids = get_project_ids_from_existing_directory()
        if not project_ids:
            logger.error("No project IDs found! Please check the source directory path.")
            logger.info(f"Current source directory: {SOURCE_DIR}")
            logger.info("Use --source-dir to specify a different directory")
            return
    
    # Apply filters
    if args.start_id or args.end_id:
        start = args.start_id or 0
        end = args.end_id or 10**12
        original_count = len(project_ids)
        project_ids = [pid for pid in project_ids if start <= pid <= end]
        logger.info(f"Filtered by ID range [{start}, {end}]: {len(project_ids)}/{original_count} projects")
    
    # Check existing projects
    completed_projects, partial_projects = get_existing_projects_from_output_directory()
    logger.info(f"Existing projects in output:")
    logger.info(f"  - Completed: {len(completed_projects)}")
    logger.info(f"  - Partial: {len(partial_projects)}")
    
    if args.only_missing:
        project_ids = [pid for pid in project_ids if pid not in completed_projects]
        logger.info(f"Only missing mode: {len(project_ids)} projects to process")
    
    # Load state
    state = load_state()
    processed_from_state = set(state.get("processed_projects", []))
    all_completed = completed_projects | processed_from_state
    
    if args.force_refresh:
        remaining = project_ids
        logger.info("Force refresh mode: Will reprocess all projects")
    elif not args.reset:
        remaining = [pid for pid in project_ids if pid not in all_completed]
        # Add partial projects for retry
        for pid in partial_projects:
            if pid not in all_completed and pid not in remaining:
                remaining.append(pid)
    else:
        remaining = project_ids
        logger.info("Reset mode: Starting fresh")
    
    remaining = sorted(set(remaining))
    logger.info(f"Projects to process: {len(remaining)}/{len(project_ids)}")
    
    if args.dry_run:
        logger.info("="*60)
        logger.info("DRY RUN MODE")
        logger.info("="*60)
        logger.info(f"Would process {len(remaining)} projects:")
        for pid in remaining[:50]:
            logger.info(f"  - Project {pid}")
        if len(remaining) > 50:
            logger.info(f"  ... and {len(remaining) - 50} more")
        return
    
    if not remaining:
        logger.info("All projects already processed!")
        return
    
    # Process projects
    logger.info("="*60)
    logger.info(f"PROCESSING {len(remaining)} PROJECTS")
    logger.info("="*60)
    
    all_metadata = []
    successful = 0
    failed = 0
    
    for i, project_id in enumerate(remaining, 1):
        if SHUTDOWN_REQUESTED:
            logger.warning(f"\n⚠️  Shutdown at project {i-1}/{len(remaining)}. Exiting...")
            break
        
        logger.info(f"\n[{i}/{len(remaining)}] Processing project {project_id}...")
        
        try:
            success, metadata = process_single_project(
                project_id, OUTPUT_DIR, state, 
                skip_download=args.skip_download,
                force_refresh=args.force_refresh
            )
            
            if success:
                successful += 1
                if metadata and metadata.get("project_id"):
                    # Update or append metadata
                    existing_idx = None
                    for idx, m in enumerate(all_metadata):
                        if m.get("project_id") == project_id:
                            existing_idx = idx
                            break
                    if existing_idx is not None:
                        all_metadata[existing_idx] = metadata
                    else:
                        all_metadata.append(metadata)
            else:
                failed += 1
            
            if i % CHECKPOINT_INTERVAL == 0:
                logger.info(f"  ✓ Progress: {i}/{len(remaining)} projects, {successful} successful, {failed} failed")
                # Save consolidated metadata
                if all_metadata:
                    CONSOLIDATED_PATH.write_text(json.dumps(all_metadata, indent=2), encoding="utf-8")
            
            time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            logger.error(f"✗ Error processing project {project_id}: {e}")
            failed += 1
            state["errors"].append((project_id, str(e)))
            save_state(state)
    
    # Final save
    if all_metadata:
        CONSOLIDATED_PATH.write_text(json.dumps(all_metadata, indent=2), encoding="utf-8")
        logger.info(f"\n✓ Saved consolidated metadata to {CONSOLIDATED_PATH}")
    
    # Create manifest
    manifest = {
        "total_projects": len(project_ids),
        "successful": successful,
        "failed": failed,
        "downloaded_files": state.get("downloaded", 0),
        "skipped_files": state.get("skipped", 0),
        "output_dir": str(OUTPUT_DIR.resolve()),
        "source_dir": str(SOURCE_DIR),
        "timestamp": datetime.now().isoformat(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    save_state(state)
    
    logger.info("="*60)
    logger.info("PROCESSING COMPLETE")
    logger.info("="*60)
    logger.info(f"  - Successful: {successful}")
    logger.info(f"  - Failed: {failed}")
    logger.info(f"  - Files downloaded: {state.get('downloaded', 0)}")
    logger.info(f"  - Output directory: {OUTPUT_DIR.resolve()}")
    logger.info("="*60)

if __name__ == "__main__":
    main()