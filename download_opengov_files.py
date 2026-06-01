# import json
# import os
# import re
# import argparse
# from http import cookiejar
# from urllib.parse import urljoin
# try:
#     from bs4 import BeautifulSoup
# except Exception:
#     BeautifulSoup = None
# try:
#     import requests
# except Exception:
#     requests = None
# from pathlib import Path
# from urllib.error import HTTPError, URLError
# from urllib.parse import quote
# from urllib.request import Request, urlopen

# COOKIES = "ajs_anonymous_id=51714eb5-8de2-45ba-84e1-6fa3931c2f0d; koa.sid=2DA1L376LWf0yyWr2eFSX0TEGm1f6cFs; koa.sid.sig=4z1QA72WmN6DbFNfOQEHi8bzOz4; ajs_user_id=rajiv.patnaik@optevus.com; ajs_group_id=vend-95298276; _hp2_ses_props.4125011721=%7B%22ts%22%3A1779816217033%2C%22d%22%3A%22procurement.opengov.com%22%2C%22h%22%3A%22%2Fvendors%2F514488%2Fopen-bids%22%7D; _hp2_id.4125011721=%7B%22userId%22%3A%226891294443654347%22%2C%22pageviewId%22%3A%223385255789588565%22%2C%22sessionId%22%3A%224503500612297599%22%2C%22identity%22%3A%22rajiv.patnaik%40optevus.com%22%2C%22trackerVersion%22%3A%224.0%22%2C%22identityField%22%3Anull%2C%22isIdentified%22%3A1%7D"
# BASE_URL = "https://api.procurement.opengov.com/api/v1"
# # Default output directory (user asked to use downloads-Firsttime)
# OUTPUT_DIR = Path("downloads-Firsttime")
# USER_AGENT = "Mozilla/5.0"
# # Allow overriding cookies via environment variable `OPENGOV_COOKIES`.
# COOKIES = os.environ.get("OPENGOV_COOKIES", COOKIES)
# OPENGOV_USER = os.environ.get("OPENGOV_USER")
# OPENGOV_PASS = os.environ.get("OPENGOV_PASS")

# DEFAULT_HEADERS = {
#     "Cookie": COOKIES,
#     "User-Agent": USER_AGENT,
#     "Accept": "application/json",
# }
# PARTIAL_SUFFIX = ".part"
# STATE_PATH = OUTPUT_DIR / "download_state.json"
# MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


# def load_state():
#     if STATE_PATH.exists():
#         try:
#             state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
#             state.setdefault("downloaded", 0)
#             state.setdefault("skipped", 0)
#             state.setdefault("errors", [])
#             state.setdefault("completed_files", [])
#             return state
#         except Exception:
#             pass

#     return {
#         "downloaded": 0,
#         "skipped": 0,
#         "errors": [],
#         "completed_files": [],
#     }


# def save_state(state):
#     STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
#     STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# def make_request(url, method="GET", payload=None):
#     data = None
#     headers = dict(DEFAULT_HEADERS)
#     if payload is not None:
#         data = json.dumps(payload).encode("utf-8")
#         headers["Content-Type"] = "application/json"

#     req = Request(url, data=data, headers=headers, method=method)
#     try:
#         with urlopen(req, timeout=60) as response:
#             body = response.read().decode("utf-8")
#     except HTTPError as exc:
#         body = exc.read().decode("utf-8", errors="replace")
#         raise RuntimeError(f"HTTP error {exc.code} for {url}: {body[:500]}") from exc
#     except URLError as exc:
#         raise RuntimeError(f"URL error for {url}: {exc}") from exc

#     if not body:
#         return None
#     return json.loads(body)


# def safe_get(dct, keys, default=""):
#     for k in keys:
#         if not k:
#             continue
#         if isinstance(dct, dict) and k in dct and dct[k] is not None:
#             return dct[k]
#     return default


# def summarize_project(project, project_detail, attachments, output_dir):
#     project_id = int(project.get("id")) if project and project.get("id") else None
#     title = safe_get(project_detail, ["title", "projectTitle", "name"]) or safe_get(project, ["title", "name"]) or ""
#     organization = safe_get(project_detail, ["organization", "organizationName", "ownerName"]) or safe_get(project, ["organization"]) or ""
#     state = safe_get(project_detail, ["state"]) or safe_get(project, ["state"]) or ""
#     status = safe_get(project_detail, ["status"]) or safe_get(project, ["projectStatus"]) or ""
#     release_date = safe_get(project_detail, ["releaseDate", "release_date"]) or safe_get(project, ["releasedAt"]) or ""
#     due_date = safe_get(project_detail, ["dueDate", "due_date"]) or safe_get(project, ["closingAt"]) or ""

#     # Followers / plan holders
#     followers = []
#     for f in project_detail.get("followers", []) or []:
#         try:
#             followers.append({
#                 "vendor": safe_get(f, ["vendorName", "name"]) or safe_get(f, ["company"]),
#                 "contact": safe_get(f, ["contactName", "contact"]) or safe_get(f, ["email"]) or safe_get(f, ["contactEmail"]),
#                 "designation": safe_get(f, ["designation"]) or "",
#             })
#         except Exception:
#             continue

#     # Sections / documents: keep raw project_detail for full fidelity
#     metadata = {
#         "project_id": project_id,
#         "project_title": title,
#         "project_link": project_detail.get("projectUrl") or project_detail.get("link") or "",
#         "organization": organization,
#         "state": state,
#         "status": status,
#         "release_date": release_date,
#         "due_date": due_date,
#         "posted_at": safe_get(project_detail, ["postedAt", "posted_at"]) or "",
#         "followers": followers,
#         "attachments": [],
#         "raw": project_detail,
#     }

#     # Try to fetch the public project page and extract visible text
#     page_url = metadata.get("project_link")
#     page_text = ""
#     if page_url and BeautifulSoup is not None:
#         try:
#             headers = dict(DEFAULT_HEADERS)
#             headers["User-Agent"] = USER_AGENT
#             req = Request(page_url, headers=headers)
#             with urlopen(req, timeout=30) as resp:
#                 html = resp.read().decode("utf-8", errors="replace")
#             soup = BeautifulSoup(html, "html.parser")
#             page_text = soup.get_text(" ", strip=True)
#         except Exception:
#             page_text = ""

#     metadata["page_text"] = page_text

#     for att in attachments:
#         entry = {
#             "title": att.get("title") or att.get("filename") or att.get("name") or "",
#             "url": att.get("url"),
#             "file_path": None,
#         }
#         # Determine expected file path
#         filename = attachment_to_filename(project_id, att)
#         dest = output_dir / str(project_id) / filename
#         entry["file_path"] = str(dest)
#         metadata["attachments"].append(entry)

#     return metadata


# def sanitize_filename(value, fallback="download"):
#     text = value or fallback
#     text = text.strip()
#     text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
#     text = re.sub(r"\s+", "_", text)
#     text = text.strip("._")
#     if not text:
#         text = fallback
#     return text[:180]


# def attachment_to_filename(project_id, attachment, fallback="file"):
#     if isinstance(attachment, dict):
#         filename = attachment.get("filename") or attachment.get("name") or attachment.get("path")
#         if filename:
#             name = Path(filename).name
#             if name:
#                 return f"{project_id}__{sanitize_filename(name, fallback)}"
#         if attachment.get("title"):
#             return f"{project_id}__{sanitize_filename(attachment['title'], fallback)}"
#     return f"{project_id}__{sanitize_filename(fallback)}"


# def extract_urls(project_detail):
#     urls = []
#     seen = set()

#     doc = project_detail.get("documentAttachment")
#     if isinstance(doc, dict) and doc.get("url"):
#         urls.append(doc)

#     for attachment in project_detail.get("attachments", []) or []:
#         if isinstance(attachment, dict) and attachment.get("url"):
#             urls.append(attachment)

#     result = []
#     for item in urls:
#         url = item.get("url")
#         if url and url not in seen:
#             seen.add(url)
#             result.append(item)
#     return result


# def download_url(url, destination):
#     destination.parent.mkdir(parents=True, exist_ok=True)

#     if destination.exists():
#         return "exists"

#     temp_destination = destination.parent / (destination.name + PARTIAL_SUFFIX)
#     if temp_destination.exists():
#         temp_destination.unlink(missing_ok=True)

#     # include default headers (may include Cookie)
#     headers = dict(DEFAULT_HEADERS)
#     headers["User-Agent"] = USER_AGENT
#     req = Request(url, headers=headers)
#     with urlopen(req, timeout=60) as response:
#         data = response.read()

#     temp_destination.write_bytes(data)
#     temp_destination.replace(destination)
#     return "downloaded"


# def main():
#     # parse simple args for user/pass override
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--user", help="OpenGov username (overrides OPENGOV_USER env)")
#     parser.add_argument("--pass", dest="passwd", help="OpenGov password (overrides OPENGOV_PASS env)")
#     parser.add_argument("--start-id", type=int, help="Only process projects with id >= START_ID")
#     parser.add_argument("--end-id", type=int, help="Only process projects with id <= END_ID")
#     parser.add_argument("--ids-file", help="File with project ids to process (one per line)")
#     parser.add_argument("--only-missing", action="store_true", help="Process only projects missing project.json in output dir")
#     parser.add_argument("--dry-run", action="store_true", help="Show which projects would be processed without downloading or writing files")
#     parser.add_argument("--verbose", action="store_true", help="Print detailed output including each selected project ID")
#     args, _ = parser.parse_known_args()
#     user = args.user or OPENGOV_USER
#     passwd = args.passwd or OPENGOV_PASS
#     dry_run = args.dry_run
#     verbose = args.verbose

#     # Build allowed IDs set based on CLI args (safe: an empty set means no restriction)
#     allowed_ids = None
#     if args.ids_file:
#         try:
#             txt = Path(args.ids_file).read_text(encoding="utf-8")
#             ids = {int(x.strip()) for x in txt.splitlines() if x.strip()}
#             allowed_ids = ids
#         except Exception:
#             allowed_ids = set()

#     if args.only_missing:
#         # scan OUTPUT_DIR for numeric directories missing project.json
#         missing = set()
#         if OUTPUT_DIR.exists():
#             for d in OUTPUT_DIR.iterdir():
#                 if d.is_dir():
#                     try:
#                         pid = int(d.name)
#                     except Exception:
#                         continue
#                     if not (d / "project.json").exists():
#                         missing.add(pid)
#         allowed_ids = missing if allowed_ids is None else (allowed_ids & missing)

#     if args.start_id or args.end_id:
#         s = args.start_id or 0
#         e = args.end_id or 10**12
#         range_ids = range(s, e + 1)
#         if allowed_ids is None:
#             allowed_ids = set(range_ids)
#         else:
#             allowed_ids = {i for i in allowed_ids if i in range_ids}

#     # If credentials provided, attempt a simple login to obtain cookies
#     if user and passwd and requests is not None and BeautifulSoup is not None:
#         try:
#             sess = requests.Session()
#             login_page = sess.get("https://procurement.opengov.com/login", timeout=30)
#             soup = BeautifulSoup(login_page.text, "html.parser")
#             form = soup.find("form")
#             action = form.get("action") if form else "/login"
#             post_url = urljoin(login_page.url, action)
#             payload = {}
#             # copy hidden inputs
#             if form:
#                 for inp in form.find_all("input"):
#                     name = inp.get("name")
#                     if not name:
#                         continue
#                     value = inp.get("value") or ""
#                     payload[name] = value

#             # try common username/password field names
#             for ufield in ("email", "username", "user", "login"):
#                 for pfield in ("password", "pass", "passwd"):
#                     if ufield in payload:
#                         payload[ufield] = user
#                         payload[pfield] = passwd
#                         break
#                 if any(k in payload for k in ("email", "username", "user", "login")):
#                     break

#             # fallback names
#             if "email" not in payload and "username" not in payload:
#                 payload["email"] = user
#                 payload["password"] = passwd

#             resp = sess.post(post_url, data=payload, timeout=30)
#             # if login successful, extract cookies into DEFAULT_HEADERS
#             if resp.status_code in (200, 302):
#                 ck = "; ".join([f"{k}={v}" for k, v in sess.cookies.get_dict().items()])
#                 if ck:
#                     DEFAULT_HEADERS["Cookie"] = ck
#         except Exception:
#             pass

#     state = load_state()
#     completed_files = set(state.get("completed_files", []))

#     first_page = make_request(
#         f"{BASE_URL}/project/search?page=1&limit=20&sort=id&direction=DESC",
#         method="POST",
#         payload={"categories": [], "states": []},
#     )

#     if not first_page or not isinstance(first_page, dict):
#         raise RuntimeError("Unexpected response structure from project search")

#     total_count = int(first_page.get("count", 0))
#     pages = (total_count + 19) // 20

#     if dry_run:
#         candidate_ids = []
#         for page in range(1, pages + 1):
#             search_payload = make_request(
#                 f"{BASE_URL}/project/search?page={page}&limit=20&sort=id&direction=DESC",
#                 method="POST",
#                 payload={"categories": [], "states": []},
#             )
#             projects = search_payload.get("projects", []) if search_payload else []
#             for project in projects:
#                 try:
#                     project_id = int(project.get("id"))
#                 except Exception:
#                     continue
#                 if allowed_ids is not None and project_id not in allowed_ids:
#                     continue
#                 candidate_ids.append(project_id)

#         print("Dry run mode enabled. The following project IDs would be processed:")
#         print(f"Total candidate projects: {len(candidate_ids)}")
#         if candidate_ids:
#                 if verbose:
#                     for pid in candidate_ids:
#                         print(pid)
#                 else:
#                     print("Sample IDs:", candidate_ids[:50])
#                 project_id = int(project.get("id"))
#             # If allowed_ids is set, skip projects not in the set (safe filter)
#             if allowed_ids is not None and project_id not in allowed_ids:
#                 continue
#             project_detail = make_request(f"{BASE_URL}/project/{project_id}")
#             if not project_detail:
#                 errors.append((project_id, "missing project detail"))
#                 save_state(state)
#                 continue

#             attachments = extract_urls(project_detail)

#             for attachment in attachments:
#                 filename = attachment_to_filename(project_id, attachment)
#                 destination = OUTPUT_DIR / str(project_id) / filename
#                 try:
#                     status = download_url(attachment["url"], destination)
#                     destination_key = str(destination.resolve())
#                     if status == "downloaded":
#                         downloaded += 1
#                         if destination_key not in completed_files:
#                             completed_files.add(destination_key)
#                             state["downloaded"] += 1
#                     else:
#                         if destination_key not in completed_files:
#                             skipped += 1
#                             state["skipped"] += 1
#                             completed_files.add(destination_key)

#                     state["completed_files"] = sorted(completed_files)
#                     save_state(state)
#                 except Exception as exc:
#                     errors.append((project_id, str(exc)))
#                     state["errors"] = errors
#                     save_state(state)

#             # Build and save per-project metadata JSON
#             try:
#                 meta = summarize_project(project, project_detail, attachments, OUTPUT_DIR)
#                 project_dir = OUTPUT_DIR / str(project_id)
#                 project_dir.mkdir(parents=True, exist_ok=True)
#                 (project_dir / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
#                 projects_meta.append(meta)
#             except Exception as exc:
#                 errors.append((project_id, f"metadata_error: {exc}"))
#                 state["errors"] = errors
#                 save_state(state)

#     # Save aggregated projects metadata
#     try:
#         projects_path = OUTPUT_DIR / "projects.json"
#         projects_path.write_text(json.dumps(projects_meta, indent=2), encoding="utf-8")
#     except Exception:
#         # ignore write errors but record
#         errors.append(("projects_write", "failed to write projects.json"))

#     manifest = {
#         "total_count": total_count,
#         "pages": pages,
#         "downloaded": state.get("downloaded", downloaded),
#         "skipped": state.get("skipped", skipped),
#         "errors": errors[:20],
#         "output_dir": str(OUTPUT_DIR.resolve()),
#     }

#     MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
#     save_state(state)

#     print(json.dumps(manifest, indent=2))


# if __name__ == "__main__":
#     main()


import json
import os
import re
import argparse
from http import cookiejar
from urllib.parse import urljoin
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

COOKIES = "ajs_anonymous_id=51714eb5-8de2-45ba-84e1-6fa3931c2f0d; koa.sid=2DA1L376LWf0yyWr2eFSX0TEGm1f6cFs; koa.sid.sig=4z1QA72WmN6DbFNfOQEHi8bzOz4; ajs_user_id=rajiv.patnaik@optevus.com; ajs_group_id=vend-95298276; _hp2_ses_props.4125011721=%7B%22ts%22%3A1779816217033%2C%22d%22%3A%22procurement.opengov.com%22%2C%22h%22%3A%22%2Fvendors%2F514488%2Fopen-bids%22%7D; _hp2_id.4125011721=%7B%22userId%22%3A%226891294443654347%22%2C%22pageviewId%22%3A%223385255789588565%22%2C%22sessionId%22%3A%224503500612297599%22%2C%22identity%22%3A%22rajiv.patnaik%40optevus.com%22%2C%22trackerVersion%22%3A%224.0%22%2C%22identityField%22%3Anull%2C%22isIdentified%22%3A1%7D"
BASE_URL = "https://api.procurement.opengov.com/api/v1"
# Default output directory (user asked to use downloads-Firsttime)
OUTPUT_DIR = Path("downloads-Firsttime")
USER_AGENT = "Mozilla/5.0"
# Allow overriding cookies via environment variable `OPENGOV_COOKIES`.
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

    return {
        "downloaded": 0,
        "skipped": 0,
        "errors": [],
        "completed_files": [],
    }


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


def summarize_project(project, project_detail, attachments, output_dir):
    project_id = int(project.get("id")) if project and project.get("id") else None
    title = safe_get(project_detail, ["title", "projectTitle", "name"]) or safe_get(project, ["title", "name"]) or ""
    organization = safe_get(project_detail, ["organization", "organizationName", "ownerName"]) or safe_get(project, ["organization"]) or ""
    state = safe_get(project_detail, ["state"]) or safe_get(project, ["state"]) or ""
    status = safe_get(project_detail, ["status"]) or safe_get(project, ["projectStatus"]) or ""
    release_date = safe_get(project_detail, ["releaseDate", "release_date"]) or safe_get(project, ["releasedAt"]) or ""
    due_date = safe_get(project_detail, ["dueDate", "due_date"]) or safe_get(project, ["closingAt"]) or ""

    # Followers / plan holders
    followers = []
    for f in project_detail.get("followers", []) or []:
        try:
            followers.append({
                "vendor": safe_get(f, ["vendorName", "name"]) or safe_get(f, ["company"]),
                "contact": safe_get(f, ["contactName", "contact"]) or safe_get(f, ["email"]) or safe_get(f, ["contactEmail"]),
                "designation": safe_get(f, ["designation"]) or "",
            })
        except Exception:
            continue

    # Sections / documents: keep raw project_detail for full fidelity
    metadata = {
        "project_id": project_id,
        "project_title": title,
        "project_link": project_detail.get("projectUrl") or project_detail.get("link") or "",
        "organization": organization,
        "state": state,
        "status": status,
        "release_date": release_date,
        "due_date": due_date,
        "posted_at": safe_get(project_detail, ["postedAt", "posted_at"]) or "",
        "followers": followers,
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
        # Determine expected file path
        filename = attachment_to_filename(project_id, att)
        dest = output_dir / str(project_id) / filename
        entry["file_path"] = str(dest)
        metadata["attachments"].append(entry)

    return metadata


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

    # include default headers (may include Cookie)
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = USER_AGENT
    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as response:
        data = response.read()

    temp_destination.write_bytes(data)
    temp_destination.replace(destination)
    return "downloaded"


def main():
    # parse simple args for user/pass override
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", help="OpenGov username (overrides OPENGOV_USER env)")
    parser.add_argument("--pass", dest="passwd", help="OpenGov password (overrides OPENGOV_PASS env)")
    parser.add_argument("--start-id", type=int, help="Only process projects with id >= START_ID")
    parser.add_argument("--end-id", type=int, help="Only process projects with id <= END_ID")
    parser.add_argument("--ids-file", help="File with project ids to process (one per line)")
    parser.add_argument("--only-missing", action="store_true", help="Process only projects missing project.json in output dir")
    parser.add_argument("--dry-run", action="store_true", help="Show which projects would be processed without downloading or writing files")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output including each selected project ID")
    args, _ = parser.parse_known_args()
    user = args.user or OPENGOV_USER
    passwd = args.passwd or OPENGOV_PASS
    dry_run = args.dry_run
    verbose = args.verbose

    # Build allowed IDs set based on CLI args (safe: an empty set means no restriction)
    allowed_ids = None
    if args.ids_file:
        try:
            txt = Path(args.ids_file).read_text(encoding="utf-8")
            ids = {int(x.strip()) for x in txt.splitlines() if x.strip()}
            allowed_ids = ids
        except Exception:
            allowed_ids = set()

    if args.only_missing:
        # scan OUTPUT_DIR for numeric directories missing project.json
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

    # If credentials provided, attempt a simple login to obtain cookies
    if user and passwd and requests is not None and BeautifulSoup is not None:
        try:
            sess = requests.Session()
            login_page = sess.get("https://procurement.opengov.com/login", timeout=30)
            soup = BeautifulSoup(login_page.text, "html.parser")
            form = soup.find("form")
            action = form.get("action") if form else "/login"
            post_url = urljoin(login_page.url, action)
            payload = {}
            # copy hidden inputs
            if form:
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if not name:
                        continue
                    value = inp.get("value") or ""
                    payload[name] = value

            # try common username/password field names
            for ufield in ("email", "username", "user", "login"):
                for pfield in ("password", "pass", "passwd"):
                    if ufield in payload:
                        payload[ufield] = user
                        payload[pfield] = passwd
                        break
                if any(k in payload for k in ("email", "username", "user", "login")):
                    break

            # fallback names
            if "email" not in payload and "username" not in payload:
                payload["email"] = user
                payload["password"] = passwd

            resp = sess.post(post_url, data=payload, timeout=30)
            # if login successful, extract cookies into DEFAULT_HEADERS
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

            # If allowed_ids is set, skip projects not in the set (safe filter)
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
        # ignore write errors but record
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


if __name__ == "__main__":
    main()