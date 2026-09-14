from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import json
import shlex

app = FastAPI(title="Last30Days Skill Bridge API")

REPO_URL = "https://github.com/mvanhorn/last30days-skill.git"
SKILL_DIR = "/data/skills/last30days-skill"
SKILL_PATH = f"{SKILL_DIR}/skills/last30days/scripts/last30days.py"
SAVE_DIR = "/data/last30days"

def setup_environment():
    """Chuẩn bị thư mục và clone repository nếu chưa có."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    if not os.path.exists(SKILL_PATH):
        os.makedirs(os.path.dirname(SKILL_DIR), exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, SKILL_DIR], check=True)

# --- REQUEST MODELS ---
class ResearchRequest(BaseModel):
    topic: str
    queryPlanJson: str | None = None
    optionsJson: str | None = None

class DiscoveryRequest(BaseModel):
    action: str  # nominate, research, finalize
    topic: str | None = ""
    judgmentsJson: str | None = None
    anglesJson: str | None = None

class LibraryRequest(BaseModel):
    operation: str  # search, feed, queue-list, queue-cover
    topic: str | None = ""
    query: str | None = ""

# --- ENDPOINTS ---

# 1. Match chuẩn logic của last30days_research
@app.post("/research")
def run_research(req: ResearchRequest):
    setup_environment()
    
    # Kiểm tra Python version >= 3.12
    import sys
    if sys.version_info < (3, 12):
        raise HTTPException(status_code=500, detail="Python >= 3.12 required on server")

    base_cmd = f"python3 {SKILL_PATH} {shlex.quote(req.topic)} --emit=compact --save-dir={SAVE_DIR} --save-suffix=v3 --auto-resolve"
    
    if req.queryPlanJson and req.queryPlanJson not in ["null", '""', ""]:
        plan_file = "/tmp/last30days_query_plan.json"
        with open(plan_file, "w") as f:
            f.write(req.queryPlanJson)
        base_cmd += f" --plan {plan_file}"

    # Parse optionsJson
    opts = {}
    if req.optionsJson:
        try:
            opts = json.loads(req.optionsJson)
        except Exception:
            opts = {}

    args = []
    mapping = {
        'xHandle': '--x-handle', 'xRelated': '--x-related', 'subreddits': '--subreddits',
        'dedicatedSubreddits': '--dedicated-subreddits', 'tiktokHashtags': '--tiktok-hashtags',
        'tiktokCreators': '--tiktok-creators', 'igCreators': '--ig-creators',
        'githubUser': '--github-user', 'githubRepo': '--github-repo', 'trustpilotDomain': '--trustpilot-domain'
    }
    for k, flag in mapping.items():
        v = opts.get(k)
        if v is not None and v != '':
            args.extend([flag, str(v)])
            
    if opts.get('quick'): args.append('--quick')
    if opts.get('deep'): args.append('--deep')

    extra = ' ' + ' '.join(shlex.quote(x) for x in args) if args else ''
    full_cmd = base_cmd + extra

    try:
        p = subprocess.run(full_cmd, shell=True, text=True, capture_output=True)
        if p.returncode != 0:
            raise HTTPException(status_code=500, detail=p.stderr)
        return {"stdout": p.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Match chuẩn logic case $ACTION trong last30days_discovery
@app.post("/discovery")
def run_discovery(req: DiscoveryRequest):
    setup_environment()
    topic_str = shlex.quote(req.topic or "")
    
    if req.action == "nominate":
        cmd = f'python3 "{SKILL_PATH}" --discover --nominate-only {topic_str} --save-dir={SAVE_DIR}'
    elif req.action == "research":
        j_file = "/tmp/last30days_judgments.json"
        with open(j_file, "w") as f:
            f.write(req.judgmentsJson or "")
        cmd = f'python3 "{SKILL_PATH}" --discover --judgments {j_file} {topic_str} --save-dir={SAVE_DIR}'
    elif req.action == "finalize":
        a_file = "/tmp/last30days_angles.json"
        with open(a_file, "w") as f:
            f.write(req.anglesJson or "")
        cmd = f'python3 "{SKILL_PATH}" --discover --finalize --angles {a_file} {topic_str} --save-dir={SAVE_DIR}'
    else:
        raise HTTPException(status_code=400, detail="action must be nominate, research, or finalize")

    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)
    return {"stdout": p.stdout}

# 3. Match chuẩn logic case $OP trong last30days_library
@app.post("/library")
def run_library(req: LibraryRequest):
    setup_environment()
    topic_str = shlex.quote(req.topic or "")
    query_str = shlex.quote(req.query or "")

    if req.operation == "search":
        cmd = f'python3 "{SKILL_PATH}" library search {query_str} --save-dir={SAVE_DIR}'
    elif req.operation == "feed":
        cmd = f'python3 "{SKILL_PATH}" library feed --save-dir={SAVE_DIR}'
    elif req.operation == "queue-list":
        cmd = f'python3 "{SKILL_PATH}" queue list --save-dir={SAVE_DIR}'
    elif req.operation == "queue-cover":
        cmd = f'python3 "{SKILL_PATH}" queue cover {topic_str} --save-dir={SAVE_DIR}'
    else:
        raise HTTPException(status_code=400, detail="operation must be search, feed, queue-list, or queue-cover")

    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)
    return {"stdout": p.stdout}