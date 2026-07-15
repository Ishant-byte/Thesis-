from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from server.api.deps import get_current_user, require_admin
from server.db.mongo import get_db
from server.services.validation import validate_username, validate_password, validate_name, validate_department, validate_phone, DEPARTMENTS, STATUSES, validate_status
from server.services.auth_service import hash_password
from server.services.crypto_pki import issue_user_certificate, revoke_serial
from server.services.crypto_encrypt import encrypt_fields, decrypt_fields
from server.services.audit_service import log_event

router = APIRouter(prefix="/admin", tags=["admin"])

def _now():
    return datetime.now(timezone.utc)


@router.get("/users")
def list_users(user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    users = []
    for u in db.users.find({}, {"password_hash": 0, "public_key_pem": 0}):
        u["_id"] = str(u["_id"])
        users.append(u)
    return {"users": users}

class AdminCreateUser(BaseModel):
    username: str
    password: str
    first_name: str
    last_name: str
    department: str
    phone: str | None = None
    role: str = "employee"  # allow admin creation but not from public

@router.post("/users/create")
def admin_create_user(body: AdminCreateUser, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    try:
        validate_username(body.username)
        validate_password(body.password)
        validate_name(body.first_name, "First name")
        validate_name(body.last_name, "Last name")
        validate_department(body.department)
        validate_phone(body.phone or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=400, detail="User already exists.")
    role = body.role if body.role in ("employee", "admin") else "employee"
    cert_info = issue_user_certificate(body.username, body.password, actor_admin=user["sub"])
    db.users.insert_one({
        "username": body.username,
        "role": role,
        "department": body.department,
        "password_hash": hash_password(body.password),
        "created_at": _now(),
        "cert_pem": cert_info["cert_pem"],
        "cert_serial": str(cert_info["serial"]),
        "public_key_pem": cert_info["public_key_pem"],
        "pkcs12_path": cert_info["pkcs12_path"],
        "failed_attempts": 0,
        "locked_until": None,
        "presence_state": "offline",
        "last_seen": _now(),
        "active": True,
    })
    profile_doc = encrypt_fields({
        "username": body.username,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "department": body.department,
        "phone": body.phone or "",
        "address": "",
        "updated_at": _now(),
    }, fields=["phone","address"])
    db.profiles.insert_one(profile_doc)
    log_event("USER_CREATED", user["sub"], body.username, "User created via admin", {"role": role})
    return {"ok": True}

class UpdateUser(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    phone: str | None = None
    address: str | None = None
    active: bool | None = None
    presence_state: str | None = None

@router.put("/users/{username}")
def update_user(username: str, body: UpdateUser, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    target = db.users.find_one({"username": username})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    upd_user = {}
    if body.active is not None:
        upd_user["active"] = bool(body.active)
    if body.presence_state is not None:
        try:
            validate_status(body.presence_state)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        upd_user["presence_state"] = body.presence_state

    if upd_user:
        db.users.update_one({"username": username}, {"$set": upd_user})

    prof = db.profiles.find_one({"username": username})
    if not prof:
        prof = {"username": username, "first_name":"", "last_name":"", "department":"HR", "phone":"", "address":"", "updated_at": _now()}
        db.profiles.insert_one(encrypt_fields(prof, fields=["phone","address"]))
    prof_dec = decrypt_fields(prof, fields=["phone","address"])
    if body.first_name is not None:
        validate_name(body.first_name, "First name")
        prof_dec["first_name"] = body.first_name
    if body.last_name is not None:
        validate_name(body.last_name, "Last name")
        prof_dec["last_name"] = body.last_name
    if body.department is not None:
        validate_department(body.department)
        prof_dec["department"] = body.department
        # Keep users.department in sync for presence display.
        db.users.update_one({"username": username}, {"$set": {"department": body.department}})
    if body.phone is not None:
        validate_phone(body.phone)
        prof_dec["phone"] = body.phone
    if body.address is not None:
        prof_dec["address"] = body.address
    prof_dec["updated_at"] = _now()
    prof_enc = encrypt_fields(prof_dec, fields=["phone","address"])
    db.profiles.update_one({"username": username}, {"$set": prof_enc})
    log_event("USER_UPDATED", user["sub"], username, "User/profile updated", {})
    return {"ok": True}

@router.delete("/users/{username}")
def delete_user(username: str, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    if username == user["sub"]:
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")
    res = db.users.delete_one({"username": username})
    db.profiles.delete_one({"username": username})
    log_event("USER_DELETED", user["sub"], username, "User deleted", {})
    return {"ok": res.deleted_count == 1}

class RevokeBody(BaseModel):
    reason: str = "unspecified"

@router.post("/users/{username}/revoke-cert")
def revoke_cert(username: str, body: RevokeBody, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    target = db.users.find_one({"username": username})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    serial = target.get("cert_serial")
    if not serial:
        raise HTTPException(status_code=400, detail="User has no certificate.")
    revoke_serial(str(serial), actor_admin=user["sub"], target_username=username, reason=body.reason)
    return {"ok": True}

class RotateBody(BaseModel):
    new_password: str

@router.post("/users/{username}/rotate-cert")
def rotate_cert(username: str, body: RotateBody, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    target = db.users.find_one({"username": username})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        validate_password(body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cert_info = issue_user_certificate(username, body.new_password, actor_admin=user["sub"])
    db.users.update_one({"username": username}, {"$set": {
        "cert_pem": cert_info["cert_pem"],
        "cert_serial": str(cert_info["serial"]),
        "public_key_pem": cert_info["public_key_pem"],
        "pkcs12_path": cert_info["pkcs12_path"],
    }})
    log_event("CERT_ROTATED", user["sub"], username, "Certificate rotated", {"serial": cert_info["serial"]})
    return {"ok": True, "pkcs12_path": cert_info["pkcs12_path"]}

class NoticeCreate(BaseModel):
    title: str
    body: str

@router.post("/notices")
def post_notice(n: NoticeCreate, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    db.notices.insert_one({"title": n.title, "body": n.body, "created_by": user["sub"], "created_at": _now()})
    log_event("NOTICE_POSTED", user["sub"], None, "Notice posted", {"title": n.title})
    return {"ok": True}

@router.get("/logs")
def get_logs(
    actor: str | None = None,
    target: str | None = None,
    event_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
    user=Depends(get_current_user),
):
    require_admin(user)
    db = get_db()
    q = {}
    if actor:
        q["actor_username"] = actor
    if target:
        q["target_username"] = target
    if event_type:
        q["event_type"] = event_type
    def parse_dt(s):
        return datetime.fromisoformat(s.replace("Z","+00:00"))
    if start:
        q.setdefault("timestamp", {})
        q["timestamp"]["$gte"] = parse_dt(start)
    if end:
        q.setdefault("timestamp", {})
        q["timestamp"]["$lte"] = parse_dt(end)
    logs = []
    for d in db.audit_logs.find(q).sort("timestamp", -1).limit(1000):
        d["_id"] = str(d["_id"])
        d["timestamp"] = d["timestamp"].isoformat()
        logs.append(d)
    return {"logs": logs}

@router.get("/logs/export")
def export_logs(
    actor: str | None = None,
    target: str | None = None,
    event_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
    user=Depends(get_current_user),
):
    require_admin(user)
    data = get_logs(actor=actor, target=target, event_type=event_type, start=start, end=end, user=user)["logs"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp","severity","event_type","actor","target","message"])
    for r in data:
        w.writerow([r["timestamp"], r["severity"], r["event_type"], r.get("actor_username",""), r.get("target_username",""), r.get("message","")])
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=audit_logs.csv"})


from pydantic import BaseModel as _BaseModel

class LeaveDecision(_BaseModel):
    decision: str  # approve or reject

@router.get("/leave")
def list_leave(user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    out = []
    for r in db.leave_requests.find({}).sort("created_at",-1).limit(500):
        r["_id"] = str(r["_id"])
        r["created_at"] = r["created_at"].isoformat()
        r["updated_at"] = r["updated_at"].isoformat()
        out.append(r)
    return {"requests": out}

@router.post("/leave/{leave_id}")
def decide_leave(leave_id: str, body: LeaveDecision, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    from bson import ObjectId
    try:
        oid = ObjectId(leave_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid leave id")
    rec = db.leave_requests.find_one({"_id": oid})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    if body.decision not in ("approve","reject"):
        raise HTTPException(status_code=400, detail="Decision must be approve or reject")
    status = "approved" if body.decision=="approve" else "rejected"
    db.leave_requests.update_one({"_id": oid}, {"$set": {"status": status, "approver": user["sub"], "updated_at": _now()}})
    log_event("LEAVE_DECIDED", user["sub"], rec["username"], f"Leave {status}", {"leave_id": leave_id})
    return {"ok": True, "status": status}

class AttendanceOverride(_BaseModel):
    date: str
    clock_in: str | None = None
    clock_out: str | None = None

@router.post("/attendance/{username}/override")
def override_attendance(username: str, body: AttendanceOverride, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    # store ISO timestamps as strings for simplicity in override
    doc = db.attendance.find_one({"username": username, "date": body.date})
    if not doc:
        db.attendance.insert_one({"username": username, "date": body.date, "clock_in": body.clock_in, "clock_out": body.clock_out, "updated_at": _now(), "overridden_by": user["sub"]})
    else:
        db.attendance.update_one({"username": username, "date": body.date}, {"$set": {"clock_in": body.clock_in, "clock_out": body.clock_out, "updated_at": _now(), "overridden_by": user["sub"]}})
    log_event("ATTENDANCE_OVERRIDDEN", user["sub"], username, "Attendance overridden", {"date": body.date})
    return {"ok": True}


class SalarySet(_BaseModel):
    month: str  # YYYY-MM
    amount: float
    note: str | None = None

@router.post("/salary/{username}")
def set_salary(username: str, body: SalarySet, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    if not db.users.find_one({"username": username}):
        raise HTTPException(status_code=404, detail="User not found")
    from server.services.crypto_encrypt import encrypt_fields
    doc = encrypt_fields({
        "username": username,
        "month": body.month,
        "amount": body.amount,
        "note": body.note or "",
        "created_at": _now(),
        "created_by": user["sub"],
    }, fields=["amount","note"])
    db.payroll.insert_one(doc)
    log_event("SALARY_SET", user["sub"], username, "Salary record added", {"month": body.month})
    return {"ok": True}

@router.get("/salary/{username}")
def get_salary_admin(username: str, user=Depends(get_current_user)):
    require_admin(user)
    db = get_db()
    from server.services.crypto_encrypt import decrypt_fields
    out = []
    for r in db.payroll.find({"username": username}).sort("created_at",-1).limit(60):
        r = decrypt_fields(r, fields=["amount","note"])
        r["_id"] = str(r["_id"])
        r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return {"records": out}
