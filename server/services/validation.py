from __future__ import annotations
import re

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z\s.'-]{1,49}$")
PHONE_RE = re.compile(r"^[0-9+\-\s]{7,20}$")

DEPARTMENTS = ["HR", "IT", "Finance", "Operations", "Sales", "Marketing", "Security"]
STATUSES = ["online", "offline", "away", "home"]

# Professional role titles for registration dropdowns.
ADMIN_ROLES = [
    "System Administrator",
    "Security Administrator",
    "HR Administrator",
    "Compliance Administrator",
]

EMPLOYEE_ROLES = [
    "HR Officer",
    "Recruitment Coordinator",
    "Payroll Specialist",
    "Finance Assistant",
    "IT Support Analyst",
    "Operations Coordinator",
]

def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username or ""):
        raise ValueError("Username must be a valid email address.")

def validate_password(pw: str) -> None:
    if pw is None or len(pw) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", pw):
        raise ValueError("Password must include an uppercase letter.")
    if not re.search(r"[a-z]", pw):
        raise ValueError("Password must include a lowercase letter.")
    if not re.search(r"[0-9]", pw):
        raise ValueError("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", pw):
        raise ValueError("Password must include a special character.")

def validate_name(name: str, field: str="Name") -> None:
    if not NAME_RE.match(name or ""):
        raise ValueError(f"{field} must contain only valid characters and be 2-50 chars.")

def validate_phone(phone: str) -> None:
    if phone and not PHONE_RE.match(phone):
        raise ValueError("Phone number format is invalid.")

def validate_department(dept: str) -> None:
    if dept not in DEPARTMENTS:
        raise ValueError(f"Department must be one of: {', '.join(DEPARTMENTS)}")

def validate_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Status must be one of: {', '.join(STATUSES)}")

def validate_job_role(job_role: str, account_role: str) -> None:
    job_role = (job_role or "").strip()
    if not job_role:
        raise ValueError("Role is required.")
    if account_role == "admin":
        allowed = ADMIN_ROLES
    else:
        allowed = EMPLOYEE_ROLES
    if job_role not in allowed:
        raise ValueError(f"Role must be one of: {', '.join(allowed)}")
