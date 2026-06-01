#python script.py --fix-json

import json
import os
import re
import argparse
from http import cookiejar
from urllib.parse import urljoin, urlparse
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
try:
    import requests
except Exception:
    requests = None
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import time

COOKIES = "ajs_anonymous_id=51714eb5-8de2-45ba-84e1-6fa3931c2f0d; koa.sid=2DA1L376LWf0yyWr2eFSX0TEGm1f6cFs; koa.sid.sig=4z1QA72WmN6DbFNfOQEHi8bzOz4; ajs_user_id=rajiv.patnaik@optevus.com; ajs_group_id=vend-95298276; _hp2_ses_props.4125011721=%7B%22ts%22%3A1779816217033%2C%22d%22%3A%22procurement.opengov.com%22%2C%22h%22%3A%22%2Fvendors%2F514488%2Fopen-bids%22%7D; _hp2_id.4125011721=%7B%22userId%22%3A%226891294443654347%22%2C%22pageviewId%22%3A%223385255789588565%22%2C%22sessionId%22%3A%224503500612297599%22%2C%22identity%22%3A%22rajiv.patnaik%40optevus.com%22%2C%22trackerVersion%22%3A%224.0%22%2C%22identityField%22%3Anull%2C%22isIdentified%22%3A1%7D"
BASE_URL = "https://api.procurement.opengov.com/api/v1"
OUTPUT_DIR = Path("downloads-Firsttime")
USER_AGENT = "Mozilla/5.0"
COOKIES = os.environ.get("OPENGOV_COOKIES", COOKIES)
OPENGOV_USER = os.environ.get("OPENGOV_USER")
OPENGOV_PASS = os.environ.get("OPENGOV_PASS")

DEFAULT_HEADERS = {
    "Cookie": COOKIES,
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}
PARTIAL_SUFFIX = ".part"
STATE_PATH = OUTPUT_DIR / "download_state.json"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


def load_state():
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state.setdefault("downloaded", 0)
            state.setdefault("skipped", 0)
            state.setdefault("errors", [])
            state.setdefault("completed_files", [])
            return state
        except Exception:
            pass
    return {"downloaded": 0, "skipped": 0, "errors": [], "completed_files": []}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def make_request(url, method="GET", payload=None):
    data = None
    headers = dict(DEFAULT_HEADERS)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP error {exc.code} for {url}: {body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error for {url}: {exc}") from exc

    if not body:
        return None
    return json.loads(body)


def safe_get(dct, keys, default=""):
    for k in keys:
        if not k:
            continue
        if isinstance(dct, dict) and k in dct and dct[k] is not None:
            return dct[k]
    return default


def fetch_followers_from_web(project_id, govcode):
    """Scrape followers from the project's followers page"""
    if not govcode or requests is None or BeautifulSoup is None:
        return []
    
    url = f"https://procurement.opengov.com/portal/{quote(str(govcode))}/projects/{project_id}/followers"
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = USER_AGENT
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.text, "html.parser")
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
        
        return followers
    except Exception as e:
        print(f"  Error scraping followers: {e}")
        return []


def scrape_project_details_from_web(project_id, project_link):
    """Scrape additional details from the project's main page"""
    if not project_link or BeautifulSoup is None:
        return {}
    
    try:
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = USER_AGENT
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        
        req = Request(project_link, headers=headers)
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        
        soup = BeautifulSoup(html, "html.parser")
        scraped_data = {}
        
        # Extract timeline dates
        timeline_elements = soup.find_all(class_=re.compile(r"(timeline|date|deadline)", re.I))
        for elem in timeline_elements:
            text = elem.get_text(" ", strip=True)
            if "Release Date" in text or "Posted" in text:
                scraped_data["release_date_text"] = text
            if "Due Date" in text or "Closing" in text or "Deadline" in text:
                scraped_data["due_date_text"] = text
        
        # Extract project ID
        project_id_elem = soup.find(string=re.compile(r"Project ID:", re.I))
        if project_id_elem:
            parent = project_id_elem.parent
            if parent:
                id_text = parent.get_text(" ", strip=True)
                match = re.search(r"Project ID:\s*([A-Z0-9\-]+)", id_text, re.I)
                if match:
                    scraped_data["financial_id"] = match.group(1)
        
        # Extract page text for search
        scraped_data["page_text"] = soup.get_text(" ", strip=True)[:10000]  # Limit length
        
        return scraped_data
    except Exception as e:
        print(f"  Error scraping project page: {e}")
        return {}


def get_followers_for_project(project_id, project_detail):
    """Get followers from API or web scraping"""
    followers = []
    
    # Try API first
    if "followers" in project_detail and project_detail["followers"]:
        for f in project_detail["followers"]:
            if isinstance(f, dict):
                follower = {
                    "vendor": safe_get(f, ["vendorName", "name", "company", "vendor"]) or "",
                    "contact": safe_get(f, ["contactName", "contact", "email", "contactEmail"]) or "",
                    "designation": safe_get(f, ["designation", "title", "role"]) or "",
                }
                if follower["vendor"] or follower["contact"]:
                    followers.append(follower)
    
    # If no followers from API, try scraping
    if not followers:
        government = project_detail.get("government") or {}
        govcode = None
        if isinstance(government, dict):
            govcode = government.get("code") or government.get("slug")
        govcode = govcode or project_detail.get("governmentCode") or project_detail.get("government_slug")
        
        if govcode:
            print(f"  Scraping followers from web for project {project_id}...")
            followers = fetch_followers_from_web(project_id, govcode)
            time.sleep(1)  # Be respectful to the server
    
    return followers


def check_and_fix_project_json(project_dir, project_id, project_detail=None):
    """Check if project.json has all required fields and fix if missing"""
    project_json_path = project_dir / "project.json"
    
    if not project_json_path.exists():
        print(f"  project.json not found for project {project_id}")
        return False
    
    try:
        with open(project_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Error reading project.json for {project_id}: {e}")
        return False
    
    # Check what's missing
    missing_fields = []
    required_fields = ["project_id", "project_title", "organization", "state", "status", "release_date", "due_date", "followers"]
    
    for field in required_fields:
        if field not in data or (field == "followers" and not data[field]):
            missing_fields.append(field)
    
    # Also check if attachments have file_path
    attachments_missing_path = False
    if "attachments" in data:
        for att in data["attachments"]:
            if "file_path" not in att or not att["file_path"]:
                attachments_missing_path = True
                break
    
    if not missing_fields and not attachments_missing_path:
        if data.get("followers"):
            print(f"  Project {project_id}: All data complete (followers: {len(data['followers'])})")
        else:
            print(f"  Project {project_id}: Missing followers data")
            missing_fields.append("followers")
    
    if missing_fields or attachments_missing_path:
        print(f"  Project {project_id}: Missing fields: {missing_fields if missing_fields else 'attachments file_path'}")
        
        # Fetch project detail if not provided
        if project_detail is None:
            try:
                print(f"  Fetching fresh data for project {project_id}...")
                project_detail = make_request(f"{BASE_URL}/project/{project_id}")
                time.sleep(0.5)
            except Exception as e:
                print(f"  Error fetching project {project_id}: {e}")
                return False
        
        if project_detail:
            # Update missing fields
            if "followers" in missing_fields or not data.get("followers"):
                followers = get_followers_for_project(project_id, project_detail)
                if followers:
                    data["followers"] = followers
                    print(f"    Added {len(followers)} followers")
            
            # Update attachments file_path if missing
            if "attachments" in project_detail and attachments_missing_path:
                for att in data.get("attachments", []):
                    if "file_path" not in att or not att["file_path"]:
                        filename = attachment_to_filename(project_id, att)
                        dest = project_dir / filename
                        att["file_path"] = str(dest)
                print(f"    Updated attachment file paths")
            
            # Add sections if missing
            if "sections" not in data and "criteria" in project_detail:
                sections = extract_project_sections(project_detail)
                if sections:
                    data["sections"] = sections
                    print(f"    Added {len(sections)} sections")
            
            # Add summary and background if missing
            if "summary" not in data and "summary" in project_detail:
                data["summary"] = project_detail.get("summary", "")
            if "background" not in data and "background" in project_detail:
                data["background"] = project_detail.get("background", "")
            
            # Save updated data
            try:
                with open(project_json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                print(f"  Successfully updated project.json for {project_id}")
                return True
            except Exception as e:
                print(f"  Error saving updated project.json: {e}")
                return False
    
    return True


def extract_project_sections(project_detail):
    """Extract all text content from project sections"""
    sections_content = {}
    
    if "projectSections" in project_detail:
        for section in project_detail.get("projectSections", []):
            section_title = section.get("title", "")
            section_type = section.get("section_type", "")
            
            if "criteria" in project_detail:
                for criterion in project_detail.get("criteria", []):
                    if criterion.get("project_section_id") == section.get("id"):
                        section_key = f"{section_title}" if section_title else criterion.get("title", "")
                        if section_key and section_key not in sections_content:
                            sections_content[section_key] = []
                        
                        content = {
                            "title": criterion.get("title", ""),
                            "description": criterion.get("description", ""),
                            "rawDescription": criterion.get("rawDescription", ""),
                            "type": criterion.get("section_type", section_type),
                        }
                        if section_key:
                            sections_content[section_key].append(content)
                        elif content["title"]:
                            sections_content[content["title"]] = [content]
    
    return sections_content


def sanitize_filename(value, fallback="download"):
    text = value or fallback
    text = text.strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._")
    if not text:
        text = fallback
    return text[:180]


def attachment_to_filename(project_id, attachment, fallback="file"):
    if isinstance(attachment, dict):
        filename = attachment.get("filename") or attachment.get("name") or attachment.get("path")
        if filename:
            name = Path(filename).name
            if name:
                return f"{project_id}__{sanitize_filename(name, fallback)}"
        if attachment.get("title"):
            return f"{project_id}__{sanitize_filename(attachment['title'], fallback)}"
    return f"{project_id}__{sanitize_filename(fallback)}"


def extract_urls(project_detail):
    urls = []
    seen = set()

    doc = project_detail.get("documentAttachment")
    if isinstance(doc, dict) and doc.get("url"):
        urls.append(doc)

    for attachment in project_detail.get("attachments", []) or []:
        if isinstance(attachment, dict) and attachment.get("url"):
            urls.append(attachment)

    result = []
    for item in urls:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            result.append(item)
    return result


def download_url(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        return "exists"

    temp_destination = destination.parent / (destination.name + PARTIAL_SUFFIX)
    if temp_destination.exists():
        temp_destination.unlink(missing_ok=True)

    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = USER_AGENT
    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as response:
        data = response.read()

    temp_destination.write_bytes(data)
    temp_destination.replace(destination)
    return "downloaded"


def scan_and_fix_all_projects():
    """Scan all project directories and fix missing data"""
    print("\n" + "="*60)
    print("SCANNING AND FIXING ALL PROJECT JSON FILES")
    print("="*60)
    
    if not OUTPUT_DIR.exists():
        print(f"Output directory {OUTPUT_DIR} does not exist.")
        return
    
    project_dirs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    print(f"Found {len(project_dirs)} project directories")
    
    fixed_count = 0
    error_count = 0
    
    for i, project_dir in enumerate(project_dirs, 1):
        project_id = int(project_dir.name)
        print(f"\n[{i}/{len(project_dirs)}] Checking project {project_id}...")
        
        try:
            if check_and_fix_project_json(project_dir, project_id):
                fixed_count += 1
            time.sleep(0.5)  # Be respectful to the API
        except Exception as e:
            print(f"  Error processing project {project_id}: {e}")
            error_count += 1
    
    print("\n" + "="*60)
    print(f"SCAN COMPLETE: Fixed {fixed_count} projects, {error_count} errors")
    print("="*60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", help="OpenGov username (overrides OPENGOV_USER env)")
    parser.add_argument("--pass", dest="passwd", help="OpenGov password (overrides OPENGOV_PASS env)")
    parser.add_argument("--start-id", type=int, help="Only process projects with id >= START_ID")
    parser.add_argument("--end-id", type=int, help="Only process projects with id <= END_ID")
    parser.add_argument("--ids-file", help="File with project ids to process (one per line)")
    parser.add_argument("--only-missing", action="store_true", help="Process only projects missing project.json in output dir")
    parser.add_argument("--dry-run", action="store_true", help="Show which projects would be processed without downloading or writing files")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output including each selected project ID")
    parser.add_argument("--fix-json", action="store_true", help="Scan and fix all existing project.json files (add missing followers, sections, etc.)")
    parser.add_argument("--project-id", type=int, help="Fix a specific project ID only")
    args, _ = parser.parse_known_args()
    
    # If fixing JSON files, run that and exit
    if args.fix_json:
        if args.project_id:
            # Fix specific project
            project_dir = OUTPUT_DIR / str(args.project_id)
            if project_dir.exists():
                print(f"Fixing project {args.project_id}...")
                check_and_fix_project_json(project_dir, args.project_id)
            else:
                print(f"Project directory {args.project_id} not found")
        else:
            # Fix all projects
            scan_and_fix_all_projects()
        return
    
    user = args.user or OPENGOV_USER
    passwd = args.passwd or OPENGOV_PASS
    dry_run = args.dry_run
    verbose = args.verbose

    # Build allowed IDs set based on CLI args
    allowed_ids = None
    if args.ids_file:
        try:
            txt = Path(args.ids_file).read_text(encoding="utf-8")
            ids = {int(x.strip()) for x in txt.splitlines() if x.strip()}
            allowed_ids = ids
        except Exception:
            allowed_ids = set()

    if args.only_missing:
        missing = set()
        if OUTPUT_DIR.exists():
            for d in OUTPUT_DIR.iterdir():
                if d.is_dir():
                    try:
                        pid = int(d.name)
                    except Exception:
                        continue
                    if not (d / "project.json").exists():
                        missing.add(pid)
        allowed_ids = missing if allowed_ids is None else (allowed_ids & missing)

    if args.start_id or args.end_id:
        s = args.start_id or 0
        e = args.end_id or 10**12
        range_ids = range(s, e + 1)
        if allowed_ids is None:
            allowed_ids = set(range_ids)
        else:
            allowed_ids = {i for i in allowed_ids if i in range_ids}

    # Login if credentials provided
    if user and passwd and requests is not None and BeautifulSoup is not None:
        try:
            sess = requests.Session()
            login_page = sess.get("https://procurement.opengov.com/login", timeout=30)
            soup = BeautifulSoup(login_page.text, "html.parser")
            form = soup.find("form")
            action = form.get("action") if form else "/login"
            post_url = urljoin(login_page.url, action)
            payload = {}
            if form:
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if not name:
                        continue
                    value = inp.get("value") or ""
                    payload[name] = value

            for ufield in ("email", "username", "user", "login"):
                for pfield in ("password", "pass", "passwd"):
                    if ufield in payload:
                        payload[ufield] = user
                        payload[pfield] = passwd
                        break
                if any(k in payload for k in ("email", "username", "user", "login")):
                    break

            if "email" not in payload and "username" not in payload:
                payload["email"] = user
                payload["password"] = passwd

            resp = sess.post(post_url, data=payload, timeout=30)
            if resp.status_code in (200, 302):
                ck = "; ".join([f"{k}={v}" for k, v in sess.cookies.get_dict().items()])
                if ck:
                    DEFAULT_HEADERS["Cookie"] = ck
        except Exception:
            pass

    state = load_state()
    completed_files = set(state.get("completed_files", []))
    downloaded = state.get("downloaded", 0)
    skipped = state.get("skipped", 0)
    errors = state.get("errors", [])
    projects_meta = []

    first_page = make_request(
        f"{BASE_URL}/project/search?page=1&limit=20&sort=id&direction=DESC",
        method="POST",
        payload={"categories": [], "states": []},
    )

    if not first_page or not isinstance(first_page, dict):
        raise RuntimeError("Unexpected response structure from project search")

    total_count = int(first_page.get("count", 0))
    pages = (total_count + 19) // 20

    if dry_run:
        candidate_ids = []
        for page in range(1, pages + 1):
            search_payload = make_request(
                f"{BASE_URL}/project/search?page={page}&limit=20&sort=id&direction=DESC",
                method="POST",
                payload={"categories": [], "states": []},
            )
            projects = search_payload.get("projects", []) if search_payload else []
            for project in projects:
                try:
                    project_id = int(project.get("id"))
                except Exception:
                    continue
                if allowed_ids is not None and project_id not in allowed_ids:
                    continue
                candidate_ids.append(project_id)

        print("Dry run mode enabled. The following project IDs would be processed:")
        print(f"Total candidate projects: {len(candidate_ids)}")
        if candidate_ids:
            if verbose:
                for pid in candidate_ids:
                    print(pid)
            else:
                print("Sample IDs:", candidate_ids[:50])
        return

    # Process each page
    for page in range(1, pages + 1):
        search_payload = make_request(
            f"{BASE_URL}/project/search?page={page}&limit=20&sort=id&direction=DESC",
            method="POST",
            payload={"categories": [], "states": []},
        )
        projects = search_payload.get("projects", []) if search_payload else []

        for project in projects:
            try:
                project_id = int(project.get("id"))
            except Exception:
                continue

            if allowed_ids is not None and project_id not in allowed_ids:
                continue

            if verbose:
                print(f"Processing project {project_id}")

            project_detail = make_request(f"{BASE_URL}/project/{project_id}")
            if not project_detail:
                errors.append((project_id, "missing project detail"))
                save_state(state)
                continue

            attachments = extract_urls(project_detail)

            for attachment in attachments:
                filename = attachment_to_filename(project_id, attachment)
                destination = OUTPUT_DIR / str(project_id) / filename
                try:
                    status = download_url(attachment["url"], destination)
                    destination_key = str(destination.resolve())
                    if status == "downloaded":
                        downloaded += 1
                        if destination_key not in completed_files:
                            completed_files.add(destination_key)
                            state["downloaded"] = downloaded
                    else:
                        if destination_key not in completed_files:
                            skipped += 1
                            state["skipped"] = skipped
                            completed_files.add(destination_key)

                    state["completed_files"] = sorted(completed_files)
                    save_state(state)
                except Exception as exc:
                    errors.append((project_id, str(exc)))
                    state["errors"] = errors
                    save_state(state)

            # Build and save per-project metadata JSON
            try:
                meta = summarize_project(project, project_detail, attachments, OUTPUT_DIR)
                project_dir = OUTPUT_DIR / str(project_id)
                project_dir.mkdir(parents=True, exist_ok=True)
                (project_dir / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                projects_meta.append(meta)
            except Exception as exc:
                errors.append((project_id, f"metadata_error: {exc}"))
                state["errors"] = errors
                save_state(state)

    # Save aggregated projects metadata
    try:
        projects_path = OUTPUT_DIR / "projects.json"
        projects_path.write_text(json.dumps(projects_meta, indent=2), encoding="utf-8")
    except Exception:
        errors.append(("projects_write", "failed to write projects.json"))

    manifest = {
        "total_count": total_count,
        "pages": pages,
        "downloaded": state.get("downloaded", downloaded),
        "skipped": state.get("skipped", skipped),
        "errors": errors[:20],
        "output_dir": str(OUTPUT_DIR.resolve()),
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    save_state(state)

    print(json.dumps(manifest, indent=2))


def summarize_project(project, project_detail, attachments, output_dir):
    project_id = int(project.get("id")) if project and project.get("id") else None
    title = safe_get(project_detail, ["title", "projectTitle", "name"]) or safe_get(project, ["title", "name"]) or ""
    organization = safe_get(project_detail, ["organization", "organizationName", "ownerName"]) or safe_get(project, ["organization"]) or ""
    state = safe_get(project_detail, ["state"]) or safe_get(project, ["state"]) or ""
    status = safe_get(project_detail, ["status"]) or safe_get(project, ["projectStatus"]) or ""
    release_date = safe_get(project_detail, ["releaseDate", "release_date"]) or safe_get(project, ["releasedAt"]) or ""
    due_date = safe_get(project_detail, ["dueDate", "due_date"]) or safe_get(project, ["closingAt"]) or ""

    # Get followers using enhanced function
    followers = get_followers_for_project(project_id, project_detail)
    
    # Extract project sections content
    sections_content = extract_project_sections(project_detail)
    
    # Build project link
    project_link = project_detail.get("projectUrl") or project_detail.get("link") or ""
    if not project_link and project_id:
        government = project_detail.get("government") or {}
        govcode = None
        if isinstance(government, dict):
            govcode = government.get("code") or government.get("slug")
        govcode = govcode or project_detail.get("governmentCode") or project_detail.get("government_slug")
        if govcode:
            project_link = f"https://procurement.opengov.com/portal/{quote(str(govcode))}/projects/{project_id}"

    # Extract summary and background
    summary = safe_get(project_detail, ["summary", "projectSummary"]) or ""
    background = safe_get(project_detail, ["background", "projectBackground"]) or ""
    
    # Get financial ID if available
    financial_id = safe_get(project_detail, ["financialId", "financial_id"]) or ""

    metadata = {
        "project_id": project_id,
        "project_title": title,
        "project_link": project_link,
        "organization": organization,
        "state": state,
        "status": status,
        "release_date": release_date,
        "due_date": due_date,
        "posted_at": safe_get(project_detail, ["postedAt", "posted_at"]) or "",
        "financial_id": financial_id,
        "summary": summary,
        "background": background,
        "followers": followers,
        "sections": sections_content,
        "attachments": [],
        "raw": project_detail,
    }

    # Try to fetch the public project page and extract visible text
    page_url = metadata.get("project_link")
    page_text = ""
    if page_url and BeautifulSoup is not None:
        try:
            headers = dict(DEFAULT_HEADERS)
            headers["User-Agent"] = USER_AGENT
            req = Request(page_url, headers=headers)
            with urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(" ", strip=True)
        except Exception:
            page_text = ""

    metadata["page_text"] = page_text

    for att in attachments:
        entry = {
            "title": att.get("title") or att.get("filename") or att.get("name") or "",
            "url": att.get("url"),
            "file_path": None,
        }
        filename = attachment_to_filename(project_id, att)
        dest = output_dir / str(project_id) / filename
        entry["file_path"] = str(dest)
        metadata["attachments"].append(entry)

    return metadata


if __name__ == "__main__":
    main()