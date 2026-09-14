from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import shutil

app = FastAPI()

REPO_URL = "https://github.com/mvanhorn/last30days-skill.git"
SKILL_DIR = "/tmp/last30days-skill"
SKILL_PATH = f"{SKILL_DIR}/skills/last30days/scripts/last30days.py"
SAVE_DIR = "/tmp/last30days_data"

# Tải repo về nếu chưa có
def setup_repo():
    if not os.path.exists(SKILL_DIR):
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, SKILL_DIR], check=True)
    os.makedirs(SAVE_DIR, exist_ok=True)

class ResearchRequest(BaseModel):
    topic: str
    queryPlanJson: str | None = None
    optionsJson: str | None = None

@app.post("/research")
def run_research(req: ResearchRequest):
    setup_repo()
    
    cmd = [
        "python3", SKILL_PATH, req.topic,
        "--emit=compact",
        f"--save-dir={SAVE_DIR}",
        "--save-suffix=v3",
        "--auto-resolve"
    ]
    
    # Xử lý queryPlanJson
    if req.queryPlanJson and req.queryPlanJson not in ["null", '""', ""]:
        plan_file = "/tmp/last30days_query_plan.json"
        with open(plan_file, "w") as f:
            f.write(req.queryPlanJson)
        cmd.extend(["--plan", plan_file])

    # Chạy script Python
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "output": result.stdout}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr)