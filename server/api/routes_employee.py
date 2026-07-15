from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from server.api.deps import get_current_user
from server.db.mongo import get_db
from server.services.crypto_encrypt import decrypt_fields, encrypt_fields
from server.services.validation import validate_name, validate_phone, validate_department, validate_status
from server.services.audit_service import log_event

router = APIRouter(tags=["employee"])

def _now():
    return datetime.now(timezone.utc)

@router.get("/me")
def me(user=Depends(get_current_user)):
    db = get_db()
    u = db.users.find_one({"username": user["sub"]}, {"password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    u["_id"] = str(u["_id"])
    return u

class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    phone: str | None = None
    address: str | None = None

@router.get("/me/profile")
def get_profile(user=Depends(get_current_user)):
    db = get_db()
    prof = db.profiles.find_one({"username": user["sub"]})
    if not prof:
        prof = encrypt_fields({"username": user["sub"], "first_name":"", "last_name":"", "department":"HR", "phone":"", "address":"", "updated_at": _now()}, fields=["phone","address"])
        db.profiles.insert_one(prof)
    prof = decrypt_fields(prof, fields=["phone","address"])
    prof["_id"] = str(prof["_id"])
    if isinstance(prof.get("updated_at"), datetime):
        prof["updated_at"] = prof["updated_at"].isoformat()
    return prof

@router.put("/me/profile")
def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    db = get_db()
    prof = db.profiles.find_one({"username": user["sub"]})
    if not prof:
        prof = encrypt_fields({"username": user["sub"], "first_name":"", "last_name":"", "department":"HR", "phone":"", "address":"", "updated_at": _now()}, fields=["phone","address"])
        db.profiles.insert_one(prof)
    dec = decrypt_fields(prof, fields=["phone","address"])
    if body.first_name is not None:
        validate_name(body.first_name, "First name")
        dec["first_name"] = body.first_name
    if body.last_name is not None:
        validate_name(body.last_name, "Last name")
        dec["last_name"] = body.last_name
    if body.department is not None:
        validate_department(body.department)
        dec["department"] = body.department
        # Keep users.department in sync for presence display.
        db.users.update_one({"username": user["sub"]}, {"$set": {"department": body.department}})
    if body.phone is not None:
        validate_phone(body.phone)
        dec["phone"] = body.phone
    if body.address is not None:
        dec["address"] = body.address
    dec["updated_at"] = _now()
    enc = encrypt_fields(dec, fields=["phone","address"])
    db.profiles.update_one({"username": user["sub"]}, {"$set": enc})
    log_event("PROFILE_UPDATED", user["sub"], user["sub"], "User updated own profile", {})
    return {"ok": True}

class StatusUpdate(BaseModel):
    presence_state: str

@router.put("/me/status")
def set_status(body: StatusUpdate, user=Depends(get_current_user)):
    try:
        validate_status(body.presence_state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db = get_db()
    db.users.update_one({"username": user["sub"]}, {"$set": {"presence_state": body.presence_state, "last_seen": _now()}})
    log_event("STATUS_CHANGED", user["sub"], user["sub"], "Presence status changed", {"status": body.presence_state})
    return {"ok": True}

@router.get("/presence")
def list_presence(user=Depends(get_current_user)):
    db = get_db()
    people = []
    for u in db.users.find({}, {"password_hash": 0, "cert_pem": 0, "public_key_pem": 0, "pkcs12_path": 0}):
        people.append({
            "username": u.get("username"),
            "role": u.get("role", "employee"),
            "department": u.get("department", ""),
            "presence_state": u.get("presence_state","offline"),
            "last_seen": u.get("last_seen").isoformat() if u.get("last_seen") else None
        })
    return {"people": people}

@router.get("/notices")
def notices(user=Depends(get_current_user)):
    db = get_db()
    res = []
    for n in db.notices.find({}).sort("created_at", -1).limit(100):
        n["_id"] = str(n["_id"])
        n["created_at"] = n["created_at"].isoformat()
        res.append(n)
    return {"notices": res}

class AttendanceIn(BaseModel):
    action: str  # clock_in or clock_out

@router.post("/me/attendance")
def attendance(body: AttendanceIn, user=Depends(get_current_user)):
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    rec = db.attendance.find_one({"username": user["sub"], "date": today})
    if not rec:
        rec = {"username": user["sub"], "date": today, "clock_in": None, "clock_out": None, "updated_at": _now()}
        db.attendance.insert_one(rec)
    if body.action == "clock_in":
        db.attendance.update_one({"username": user["sub"], "date": today}, {"$set": {"clock_in": _now(), "updated_at": _now()}})
        log_event("ATTENDANCE_IN", user["sub"], user["sub"], "Clock-in", {"date": today})
    elif body.action == "clock_out":
        db.attendance.update_one({"username": user["sub"], "date": today}, {"$set": {"clock_out": _now(), "updated_at": _now()}})
        log_event("ATTENDANCE_OUT", user["sub"], user["sub"], "Clock-out", {"date": today})
    else:
        raise HTTPException(status_code=400, detail="Invalid action.")
    return {"ok": True}

@router.get("/me/attendance")
def attendance_history(user=Depends(get_current_user)):
    db = get_db()
    out = []
    for r in db.attendance.find({"username": user["sub"]}).sort("date", -1).limit(90):
        r["_id"] = str(r["_id"])
        if isinstance(r.get("clock_in"), datetime):
            r["clock_in"] = r["clock_in"].isoformat()
        if isinstance(r.get("clock_out"), datetime):
            r["clock_out"] = r["clock_out"].isoformat()
        out.append(r)
    return {"records": out}

class LeaveReq(BaseModel):
    leave_type: str
    start_date: str
    end_date: str
    reason: str

@router.post("/me/leave")
def request_leave(body: LeaveReq, user=Depends(get_current_user)):
    db = get_db()
    doc = {
        "username": user["sub"],
        "leave_type": body.leave_type,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "reason": body.reason,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "approver": None,
    }
    db.leave_requests.insert_one(doc)
    log_event("LEAVE_REQUESTED", user["sub"], user["sub"], "Leave requested", {"type": body.leave_type, "start": body.start_date, "end": body.end_date})
    return {"ok": True}

@router.get("/me/leave")
def my_leave(user=Depends(get_current_user)):
    db = get_db()
    out = []
    for r in db.leave_requests.find({"username": user["sub"]}).sort("created_at",-1).limit(100):
        r["_id"] = str(r["_id"])
        r["created_at"] = r["created_at"].isoformat()
        r["updated_at"] = r["updated_at"].isoformat()
        out.append(r)
    return {"requests": out}

@router.get("/me/logs")
def my_logs(user=Depends(get_current_user)):
    db = get_db()
    out = []
    for d in db.audit_logs.find({"$or":[{"actor_username": user["sub"]},{"target_username": user["sub"]}]}).sort("timestamp",-1).limit(500):
        d["_id"] = str(d["_id"])
        d["timestamp"] = d["timestamp"].isoformat()
        out.append(d)
    return {"logs": out}


@router.get("/me/salary")
def my_salary(user=Depends(get_current_user)):
    db = get_db()
    from server.services.crypto_encrypt import decrypt_fields
    out = []
    for r in db.payroll.find({"username": user["sub"]}).sort("created_at",-1).limit(60):
        r = decrypt_fields(r, fields=["amount","note"])
        r["_id"] = str(r["_id"])
        r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return {"records": out}


@router.get("/me/keystore")
def download_keystore(user=Depends(get_current_user)):
    """Download the user's PKCS#12 keystore (for web client login)."""
    db = get_db()
    u = db.users.find_one({"username": user["sub"]})
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    p12_path = u.get("pkcs12_path")
    if not p12_path or not Path(p12_path).is_file():
        raise HTTPException(status_code=404, detail="Keystore not found on server.")
    log_event("KEYSTORE_DOWNLOAD", user["sub"], user["sub"], "Keystore downloaded", {})
    return FileResponse(
        path=p12_path,
        media_type="application/x-pkcs12",
        filename="keystore.p12",
    )
