import os
import uuid
import threading
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from scraper import run_scraper
from config import OUTPUT_DIR, FETCH_DETAILS

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for scraper tasks
jobs = {}

class ScrapeRequest(BaseModel):
    location: str
    keyword: Optional[str] = ""
    min_size: Optional[int] = 0
    listing_type: str = "for-lease"
    max_pages: Optional[int] = 1

def run_scraper_task(job_id: str, req: ScrapeRequest):
    try:
        jobs[job_id]["status"] = "running"
        results = run_scraper(
            location=req.location,
            keyword=req.keyword,
            min_size=req.min_size,
            listing_type=req.listing_type,
            max_pages=req.max_pages,
            fetch_details=FETCH_DETAILS,
            output_dir=OUTPUT_DIR,
            manual_warmup=False
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["results"] = results
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        print(f"Scraper error: {e}")

@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "starting", "results": None, "error": None}
    
    # Run in a separate thread so it doesn't block the event loop
    thread = threading.Thread(target=run_scraper_task, args=(job_id, req))
    thread.start()
    
    return {"job_id": job_id, "status": "started"}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

# Create frontend dir if it doesn't exist
os.makedirs("frontend", exist_ok=True)

# Mount frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("frontend/index.html")
