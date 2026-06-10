"""
Authentication module for LBKN Automator.
Handles user registration, login, JWT sessions, and password reset.
Fully isolated from all scraper / enquiry / email-monitor logic.
"""

import os
import re
import sqlite3
import uuid
import datetime
import bcrypt
import jwt
import requests

from config import (
    AUTH_SECRET_KEY,
    AUTH_TOKEN_EXPIRY_DAYS,
    AUTH_DB_PATH,
    AZURE_TENANT_ID,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    MONITOR_EMAIL,
)

# ============================================================
#  Database Initialisation
# ============================================================

def _get_db():
    """Return a new SQLite connection (thread-safe with check_same_thread=False)."""
    conn = sqlite3.connect(AUTH_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the users and password_reset_tokens tables if they don't exist."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # Migration: add is_approved if it doesn't exist
    try:
        cursor.execute("SELECT is_approved FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN is_approved INTEGER DEFAULT 0")
        # Auto-approve admin if exists
        cursor.execute("UPDATE users SET is_approved = 1 WHERE email = 'admin@lbkncapital.com'")
        
    conn.commit()
    conn.close()
    print("[OK] Auth DB initialised:", AUTH_DB_PATH)


# ============================================================
#  Password Hashing
# ============================================================

def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ============================================================
#  JWT Token Management
# ============================================================

def create_jwt(user_id: str, email: str) -> str:
    """Generate a JWT with configurable expiry."""
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=AUTH_TOKEN_EXPIRY_DAYS),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm="HS256")


def decode_jwt(token: str) -> dict | None:
    """Decode and validate a JWT. Returns payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, AUTH_SECRET_KEY, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ============================================================
#  User Registration & Login
# ============================================================

def register_user(email: str, password: str) -> dict:
    """
    Register a new user.
    Returns {"success": True, "message": "..."} or {"success": False, "message": "..."}.
    """
    # Validate email format
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return {"success": False, "message": "Invalid email format."}

    # Validate password length
    if len(password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters."}

    conn = _get_db()
    cursor = conn.cursor()

    # Check for duplicate email
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "message": "An account with this email already exists."}

    # Insert new user
    user_id = str(uuid.uuid4())
    is_approved = 1 if email.lower().strip() == "admin@lbkncapital.com" else 0
    cursor.execute(
        "INSERT INTO users (id, email, password_hash, created_at, is_approved) VALUES (?, ?, ?, ?, ?)",
        (user_id, email.lower().strip(), hash_password(password), datetime.datetime.utcnow().isoformat(), is_approved),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Account created successfully."}


def login_user(email: str, password: str) -> dict:
    """
    Verify credentials and return a JWT on success.
    Returns {"success": True, "token": "..."} or {"success": False, "message": "..."}.
    """
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, password_hash, is_approved FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"success": False, "message": "Invalid email or password."}

    if not verify_password(password, user["password_hash"]):
        return {"success": False, "message": "Invalid email or password."}

    # Check approval status
    # To handle legacy rows if migration somehow failed, we use dict(user).get
    if not dict(user).get("is_approved", 0):
        return {"success": False, "message": "Your account is pending admin approval."}

    token = create_jwt(user["id"], user["email"])
    return {"success": True, "token": token, "email": user["email"]}


# ============================================================
#  Password Reset
# ============================================================

def generate_reset_token(email: str) -> dict:
    """
    Generate a password-reset token for the given email.
    Returns {"success": True, "token": "..."} if user exists,
    or {"success": True} silently if not (to prevent email enumeration).
    """
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()

    if not user:
        conn.close()
        # Return success silently to prevent email enumeration
        return {"success": True, "token": None}

    token = str(uuid.uuid4())
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat()

    cursor.execute(
        "INSERT INTO password_reset_tokens (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user["id"], token, expires_at),
    )
    conn.commit()
    conn.close()
    return {"success": True, "token": token}


def reset_password(token: str, new_password: str) -> dict:
    """
    Reset a user's password using a valid reset token.
    """
    if len(new_password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters."}

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token = ?",
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "message": "Invalid or expired reset link."}

    if row["used"]:
        conn.close()
        return {"success": False, "message": "This reset link has already been used."}

    expires_at = datetime.datetime.fromisoformat(row["expires_at"])
    if datetime.datetime.utcnow() > expires_at:
        conn.close()
        return {"success": False, "message": "This reset link has expired. Please request a new one."}

    # Update password
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), row["user_id"]),
    )
    # Mark token as used
    cursor.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token = ?",
        (token,),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Password has been reset successfully."}


# ============================================================
#  Password Reset Email (via Microsoft Graph API)
# ============================================================

def _get_graph_token() -> str | None:
    """Get an OAuth2 token for Microsoft Graph API using client credentials."""
    try:
        url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        }
        resp = requests.post(url, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"[ERROR] Failed to get Graph token for password reset email: {e}")
        return None


def send_reset_email(to_email: str, reset_link: str) -> bool:
    """
    Send a password reset email via Microsoft Graph API.
    Uses the same Azure credentials already configured for email_monitor.
    """
    token = _get_graph_token()
    if not token:
        print("[WARNING] Could not send reset email — Graph token unavailable.")
        return False

    url = f"https://graph.microsoft.com/v1.0/users/{MONITOR_EMAIL}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "message": {
            "subject": "LBKN Automator — Password Reset",
            "body": {
                "contentType": "HTML",
                "content": f"""
                <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px;">
                    <h2 style="color: #3B82F6;">Password Reset Request</h2>
                    <p>You requested a password reset for your LBKN Automator account.</p>
                    <p>Click the button below to set a new password. This link expires in 1 hour.</p>
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" 
                           style="background: #3B82F6; color: white; padding: 12px 30px; 
                                  text-decoration: none; border-radius: 6px; font-weight: bold;">
                            Reset Password
                        </a>
                    </p>
                    <p style="font-size: 12px; color: #888;">
                        If you didn't request this, you can safely ignore this email.
                    </p>
                </div>
                """,
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ],
        },
        "saveToSentItems": "false",
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 202:
            print(f"[OK] Password reset email sent to {to_email}")
            return True
        else:
            print(f"[ERROR] Graph sendMail failed: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send reset email: {e}")
        return False

# ============================================================
#  Admin User Management
# ============================================================

def get_all_users() -> list:
    """Return a list of all users."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, created_at, is_approved FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def approve_user(user_id: str) -> bool:
    """Approve a pending user."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_approved = 1 WHERE id = ?", (user_id,))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed

def delete_user(user_id: str) -> bool:
    """Delete a user."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed
