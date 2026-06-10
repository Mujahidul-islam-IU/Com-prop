import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid
import threading
from fastapi import FastAPI, BackgroundTasks, Request, Response, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from scraper import run_scraper
import email_monitor
from config import OUTPUT_DIR, FETCH_DETAILS
import auth
import enquiry_settings_manager

app = FastAPI(title="LBKN CRE Automator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise auth database on startup
auth.init_db()

# In-memory store for scraper tasks
jobs = {}

class ScrapeRequest(BaseModel):
    location: str
    keyword: Optional[str] = ""
    min_size: Optional[int] = 0
    max_size: Optional[int] = 0
    listing_type: str = "for-lease"
    max_pages: Optional[int] = 1

class AuthRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

class EnquirySettingsRequest(BaseModel):
    name: str
    email: str
    phone: str
    template: str


# ============================================================
#  Auth Dependency — protects API routes
# ============================================================

def require_auth(request: Request):
    """
    FastAPI dependency: validates the auth_token cookie.
    Returns the decoded JWT payload or raises a 401.
    """
    token = request.cookies.get("auth_token")
    if not token:
        return None
    payload = auth.decode_jwt(token)
    return payload


def require_auth_strict(request: Request):
    """
    Strict auth dependency — returns 401 JSON if not authenticated.
    Use for API data endpoints.
    """
    payload = require_auth(request)
    if not payload:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


# ============================================================
#  Auth API Endpoints (public — no auth required)
# ============================================================

@app.post("/api/auth/register")
def auth_register(req: AuthRequest):
    result = auth.register_user(req.email, req.password)
    if result["success"]:
        return {"success": True, "message": result["message"]}
    return JSONResponse(status_code=400, content=result)


@app.post("/api/auth/login")
def auth_login(req: AuthRequest, response: Response):
    result = auth.login_user(req.email, req.password)
    if result["success"]:
        response.set_cookie(
            key="auth_token",
            value=result["token"],
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
            path="/",
        )
        return {"success": True, "email": result["email"]}
    return JSONResponse(status_code=401, content=result)


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(key="auth_token", path="/")
    return {"success": True, "message": "Logged out."}


@app.get("/api/auth/me")
def auth_me(request: Request):
    payload = require_auth(request)
    if not payload:
        return JSONResponse(status_code=401, content={"authenticated": False})
    return {"authenticated": True, "email": payload.get("email")}


@app.post("/api/auth/forgot-password")
def auth_forgot_password(req: ForgotPasswordRequest, request: Request):
    result = auth.generate_reset_token(req.email)
    if result["success"] and result.get("token"):
        # Build the reset link from the current request
        host = request.headers.get("host", "localhost:8000")
        scheme = request.headers.get("x-forwarded-proto", "http")
        reset_link = f"{scheme}://{host}/reset-password?token={result['token']}"
        auth.send_reset_email(req.email, reset_link)
    # Always return the same message to prevent email enumeration
    return {"success": True, "message": "If an account with that email exists, a reset link has been sent."}


@app.post("/api/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest):
    result = auth.reset_password(req.token, req.password)
    if result["success"]:
        return result
    return JSONResponse(status_code=400, content=result)


# ============================================================
#  Phase 1+2: Property Scraping & Enquiry Endpoints (PROTECTED)
# ============================================================

def run_scraper_task(job_id: str, req: ScrapeRequest):
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = None
        
        def progress_callback(current, total, title, est_time_mins):
            jobs[job_id]["progress"] = {
                "current": current,
                "total": total,
                "title": title,
                "est_time_mins": est_time_mins
            }

        results = run_scraper(
            location=req.location,
            keyword=req.keyword,
            min_size=req.min_size,
            max_size=req.max_size,
            listing_type=req.listing_type,
            max_pages=req.max_pages,
            fetch_details=FETCH_DETAILS,
            output_dir=OUTPUT_DIR,
            manual_warmup=False,
            progress_callback=progress_callback
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["results"] = results
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        print(f"Scraper error: {e}")

@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks, user=Depends(require_auth_strict)):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "starting", "results": None, "error": None}

    # Run in a separate thread so it doesn't block the event loop
    thread = threading.Thread(target=run_scraper_task, args=(job_id, req))
    thread.start()

    return {"job_id": job_id, "status": "started"}

@app.get("/api/status/{job_id}")
def get_status(job_id: str, user=Depends(require_auth_strict)):
    return jobs.get(job_id, {"status": "not_found"})

# ============================================================
#  Phase 3: Email Reply Monitor Endpoints (PROTECTED)
# ============================================================

# ============================================================
#  Enquiry Settings Endpoints (PROTECTED)
# ============================================================

@app.get("/api/settings/enquiry")
def get_enquiry_settings(user=Depends(require_auth_strict)):
    return enquiry_settings_manager.get_enquiry_settings()

@app.post("/api/settings/enquiry")
def save_enquiry_settings(req: EnquirySettingsRequest, user=Depends(require_auth_strict)):
    enquiry_settings_manager.save_enquiry_settings(req.name, req.email, req.phone, req.template)
    return {"status": "ok", "message": "Enquiry settings saved."}


@app.post("/api/check-replies")
def check_replies(user=Depends(require_auth_strict)):
    """Trigger the email monitor to scan inbox for agent replies."""
    try:
        result = email_monitor.run_monitor()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/recent-emails")
def recent_emails(user=Depends(require_auth_strict)):
    """Fetch last 5 emails for display in frontend (no Claude needed)."""
    try:
        token = email_monitor.get_graph_token()
        if not token:
            return {"status": "error", "emails": []}
        emails = email_monitor.fetch_unread_emails(token)
        summary = []
        for msg in emails[:5]:
            summary.append({
                "subject": msg.get("subject", ""),
                "from": msg.get("sender", {}).get("emailAddress", {}).get("address", ""),
                "date": msg.get("receivedDateTime", "").split("T")[0],
                "preview": msg.get("bodyPreview", "")[:120]
            })
        return {"status": "ok", "count": len(emails), "emails": summary}
    except Exception as e:
        return {"status": "error", "message": str(e), "emails": []}

# ============================================================
#  Admin User Management Endpoints (PROTECTED)
# ============================================================

def require_admin(user=Depends(require_auth_strict)):
    """Dependency to check if the current user is the admin."""
    from fastapi import HTTPException
    if user.get("email") != "admin@lbkncapital.com":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user

@app.get("/api/admin/users")
def get_admin_users(admin=Depends(require_admin)):
    return {"status": "ok", "users": auth.get_all_users()}

@app.post("/api/admin/users/{user_id}/approve")
def approve_admin_user(user_id: str, admin=Depends(require_admin)):
    success = auth.approve_user(user_id)
    if success:
        return {"status": "ok", "message": "User approved."}
    return JSONResponse(status_code=404, content={"status": "error", "message": "User not found."})

@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: str, admin=Depends(require_admin)):
    success = auth.delete_user(user_id)
    if success:
        return {"status": "ok", "message": "User deleted."}
    return JSONResponse(status_code=404, content={"status": "error", "message": "User not found."})

# ============================================================
#  Frontend Serving — Auth Pages + Protected Dashboard
# ============================================================

os.makedirs("frontend", exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- Auth pages (public) ---

@app.get("/login")
def serve_login():
    return FileResponse("frontend/login.html")

@app.get("/register")
def serve_register():
    return FileResponse("frontend/register.html")

@app.get("/forgot-password")
def serve_forgot_password():
    return FileResponse("frontend/forgot_password.html")

@app.get("/reset-password")
def serve_reset_password():
    return FileResponse("frontend/reset_password.html")

# --- Dashboard (protected) ---

@app.get("/")
def serve_index(request: Request):
    token = request.cookies.get("auth_token")
    if not token or not auth.decode_jwt(token):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse("frontend/index.html")