import os
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from bot.db import (
    list_complaints, list_users, list_blocked,
    block_user, unblock_user, set_status, stats_counts
)

app = FastAPI(title="Hotline Admin")
templates = Jinja2Templates(directory="admin/templates")

# API token (для программного доступа /api/*)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme")
bearer = HTTPBearer(auto_error=False)

# Базовая аутентификация для веб-админки
ADMIN_WEB_USER = os.getenv("ADMIN_WEB_USER", "admin")
ADMIN_WEB_PASS = os.getenv("ADMIN_WEB_PASS", "change_this")
basic = HTTPBasic()

def auth_web(creds: HTTPBasicCredentials = Depends(basic)):
    if creds.username != ADMIN_WEB_USER or creds.password != ADMIN_WEB_PASS:
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return True

def auth_api(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds or creds.credentials != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    return True

# ----- HTML pages -----
@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, _: bool = Depends(auth_web)):
    stats = stats_counts()
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})

@app.get("/admin/complaints", response_class=HTMLResponse)
def admin_complaints(request: Request, category: str | None = Query(None), page: int = 1, _: bool = Depends(auth_web)):
    page = max(1, page)
    limit = 30
    offset = (page-1)*limit
    if category not in (None, "complaint", "suggestion"):
        category = None
    rows = list_complaints(category, limit=limit, offset=offset)
    return templates.TemplateResponse("complaints.html", {"request": request, "rows": rows, "category": category, "page": page})

@app.post("/admin/complaints/status")
def admin_set_status(ticket_no: str = Form(...), status: str = Form(...), _: bool = Depends(auth_web)):
    if status not in ("new","in_progress","done"):
        raise HTTPException(400, "Bad status")
    set_status(ticket_no, status)
    return RedirectResponse(url="/admin/complaints", status_code=303)

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, page: int = 1, _: bool = Depends(auth_web)):
    page = max(1, page)
    limit = 50
    offset = (page-1)*limit
    rows = list_users(limit=limit, offset=offset)
    return templates.TemplateResponse("users.html", {"request": request, "rows": rows, "page": page})

@app.post("/admin/block")
def admin_block(user_id: int = Form(...), reason: str = Form(""), _: bool = Depends(auth_web)):
    block_user(user_id, reason or None)
    return RedirectResponse(url="/admin/blocked", status_code=303)

@app.post("/admin/unblock")
def admin_unblock(user_id: int = Form(...), _: bool = Depends(auth_web)):
    unblock_user(user_id)
    return RedirectResponse(url="/admin/blocked", status_code=303)

@app.get("/admin/blocked", response_class=HTMLResponse)
def admin_blocked(request: Request, page: int = 1, _: bool = Depends(auth_web)):
    page = max(1, page)
    limit = 50
    offset = (page-1)*limit
    rows = list_blocked(limit=limit, offset=offset)
    return templates.TemplateResponse("blocked.html", {"request": request, "rows": rows, "page": page})

# ----- JSON API (с Bearer токеном) -----
@app.get("/api/stats", dependencies=[Depends(auth_api)])
def api_stats():
    return stats_counts()

@app.get("/api/complaints", dependencies=[Depends(auth_api)])
def api_complaints(category: str | None = Query(None), limit: int = 100, offset: int = 0):
    return [
        dict(
            ticket_no=ticket, user_id=uid, username=un, full_name=fn,
            category=cat, status=status, created_at=str(created),
            message_text=textval, file_type=ftype
        )
        for _id, ticket, uid, un, fn, cat, textval, ftype, status, created
        in list_complaints(category if category in ("complaint","suggestion") else None, limit=limit, offset=offset)
    ]

@app.get("/api/users", dependencies=[Depends(auth_api)])
def api_users(limit: int = 100, offset: int = 0):
    rows = list_users(limit=limit, offset=offset)
    return [dict(user_id=uid, username=un, full_name=fn, last_activity=str(last), total_messages=total)
            for uid, un, fn, last, total in rows]
