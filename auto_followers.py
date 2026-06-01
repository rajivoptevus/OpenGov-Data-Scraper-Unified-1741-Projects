#pip install requests-html
# Test on one project first
#python auto_followers.py 268826

# If that works, run on all projects
#python auto_followers.py --all

# save as auto_followers.py
import json
import requests
import re
import time
from pathlib import Path
from typing import List, Dict

OUTPUT_DIR = Path("downloads-Firsttime")

# Your working cookies (these work for the API)
COOKIES_STR = "ajs_anonymous_id=51714eb5-8de2-45ba-84e1-6fa3931c2f0d; koa.sid=2DA1L376LWf0yyWr2eFSX0TEGm1f6cFs; koa.sid.sig=4z1QA72WmN6DbFNfOQEHi8bzOz4; ajs_user_id=rajiv.patnaik@optevus.com; ajs_group_id=vend-95298276"

def cookies_to_dict(cookies_str: str) -> Dict:
    """Convert cookie string to dictionary"""
    cookies = {}
    for item in cookies_str.split('; '):
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key] = value
    return cookies

COOKIES = cookies_to_dict(COOKIES_STR)

def get_government_code(project_id: int) -> str:
    """Extract government code from project.json"""
    project_file = OUTPUT_DIR / str(project_id) / "project.json"
    if not project_file.exists():
        return None
    
    with open(project_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Try multiple sources for govcode
    if 'raw' in data and 'government' in data['raw']:
        return data['raw']['government'].get('code')
    
    if 'project_link' in data and data['project_link']:
        match = re.search(r'portal/([^/]+)/projects', data['project_link'])
        if match:
            return match.group(1)
    
    return None

def fetch_followers_via_api(project_id: int, govcode: str) -> List[Dict]:
    """Fetch followers using the correct API endpoint"""
    
    # The API endpoint used by the OpenGov web app
    # Based on network requests from your browser
    endpoints_to_try = [
        # Most likely endpoints
        f"https://api.procurement.opengov.com/api/v1/project/{project_id}/planholders",
        f"https://api.procurement.opengov.com/api/v1/project/{project_id}/followers",
        f"https://api.procurement.opengov.com/api/v1/projects/{project_id}/planholders",
        f"https://procurement.opengov.com/api/projects/{project_id}/planholders",
        f"https://api.procurement.opengov.com/api/v1/vendor/projects/{project_id}/followers",
        
        # Vendor-specific endpoints (your vendor ID is 514488)
        f"https://api.procurement.opengov.com/api/v1/vendors/514488/projects/{project_id}/planholders",
        f"https://api.procurement.opengov.com/api/v1/vendor/514488/projects/{project_id}/followers",
        
        # GraphQL endpoint (many modern apps use this)
        "https://api.procurement.opengov.com/api/v1/graphql",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://procurement.opengov.com/portal/{govcode}/projects/{project_id}",
    }
    
    # Try each endpoint
    for url in endpoints_to_try:
        try:
            if url.endswith("/graphql"):
                # GraphQL query for followers
                query = {
                    "query": f"""
                    {{
                        project(id: {project_id}) {{
                            planholders {{
                                vendorName
                                contactName
                                email
                                designation
                            }}
                            followers {{
                                vendorName
                                contactName
                                email
                                designation
                            }}
                        }}
                    }}
                    """
                }
                response = requests.post(url, json=query, headers=headers, cookies=COOKIES, timeout=15)
            else:
                response = requests.get(url, headers=headers, cookies=COOKIES, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse different response formats
                followers = []
                
                if isinstance(data, list):
                    for item in data:
                        follower = parse_follower_item(item)
                        if follower:
                            followers.append(follower)
                elif isinstance(data, dict):
                    # Try to find followers in nested structure
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
                    print(f"  ✓ Found {len(followers)} followers via {url.split('/')[-1]}")
                    return followers
                    
        except Exception as e:
            continue
    
    return []

def parse_follower_item(item: Dict) -> Dict:
    """Parse a follower item from various possible formats"""
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
        item.get('certification')
    )
    
    if not vendor and not contact:
        return None
    
    return {
        "vendor": vendor or "",
        "contact": contact or "",
        "designation": designation or ""
    }

def fetch_followers_via_browser_automation(project_id: int, govcode: str) -> List[Dict]:
    """Last resort: Use requests-html which can execute JavaScript"""
    try:
        from requests_html import HTMLSession
        
        session = HTMLSession()
        url = f"https://procurement.opengov.com/portal/{govcode}/projects/{project_id}/followers"
        
        response = session.get(url, cookies=COOKIES)
        response.html.render(timeout=20, wait=3)  # Execute JavaScript
        
        # Find the table after JS execution
        table = response.html.find('table')
        if table:
            rows = table[0].find('tr')
            followers = []
            for row in rows[1:]:  # Skip header
                cells = row.find('td')
                if len(cells) >= 2:
                    followers.append({
                        "vendor": cells[0].text,
                        "contact": cells[1].text,
                        "designation": cells[2].text if len(cells) > 2 else ""
                    })
            return followers
        
        return []
    except ImportError:
        print("  requests-html not installed. Install with: pip install requests-html")
        return []
    except Exception as e:
        print(f"  Browser automation error: {e}")
        return []

def update_project_followers(project_id: int) -> bool:
    """Update a single project with followers"""
    
    project_dir = OUTPUT_DIR / str(project_id)
    project_json = project_dir / "project.json"
    
    if not project_json.exists():
        return False
    
    # Load current data
    with open(project_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Skip if already has followers
    if data.get('followers') and len(data.get('followers', [])) > 0:
        return True
    
    # Get government code
    govcode = get_government_code(project_id)
    if not govcode:
        return False
    
    print(f"\nProject {project_id} (govcode: {govcode})")
    
    # Try API first
    followers = fetch_followers_via_api(project_id, govcode)
    
    # If API fails, try browser automation
    if not followers:
        print("  Trying browser automation...")
        followers = fetch_followers_via_browser_automation(project_id, govcode)
    
    if followers:
        data['followers'] = followers
        with open(project_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"  ✓ Added {len(followers)} followers")
        return True
    else:
        print(f"  ✗ No followers found")
        return False

def scan_and_fix_all():
    """Scan all projects and fix missing followers"""
    print("=" * 60)
    print("SCANNING ALL PROJECTS FOR MISSING FOLLOWERS")
    print("=" * 60)
    
    project_dirs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    print(f"Found {len(project_dirs)} project directories")
    
    fixed = 0
    skipped = 0
    
    for i, project_dir in enumerate(project_dirs, 1):
        project_id = int(project_dir.name)
        print(f"\n[{i}/{len(project_dirs)}] ", end="")
        
        if update_project_followers(project_id):
            fixed += 1
        else:
            skipped += 1
        
        # Rate limiting
        time.sleep(0.5)
    
    print("\n" + "=" * 60)
    print(f"COMPLETE: Fixed {fixed} projects, Skipped {skipped}")
    print("=" * 60)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        scan_and_fix_all()
    elif len(sys.argv) > 1 and sys.argv[1].isdigit():
        update_project_followers(int(sys.argv[1]))
    else:
        print("Usage:")
        print("  python auto_followers.py 268826     # Fix one project")
        print("  python auto_followers.py --all      # Fix all projects")