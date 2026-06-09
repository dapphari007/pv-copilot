"""FastAPI backend for the rebuilt multi-patient PV Copilot — endpoints only.

Business logic lives in ``src/`` (pv_pipeline / pv_storage / pv_report). Run:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

import config
from src import auth, pv_report, pv_storage, vectordb
from src.documents import read_document
from src.logging_config import get_logger
from src.pv_pipeline import process_upload
from src.settings_store import load_settings

log = get_logger("upload")

app = FastAPI(title="Pharmacovigilance AI Copilot API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    report_date: str = ""


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = ""
    role: str = "pv_associate"


class RoleRequest(BaseModel):
    email: str
    role: str


# --------------------------------------------------------------------------- #
# Authentication (JWT + roles + OAuth Google/Microsoft)
# --------------------------------------------------------------------------- #
@app.get("/auth/providers")
def auth_providers() -> dict[str, Any]:
    return {"google": auth.provider_enabled("google"),
            "microsoft": auth.provider_enabled("microsoft"),
            "auth_required": auth.AUTH_REQUIRED}


@app.post("/auth/login")
def login(req: LoginRequest) -> dict[str, Any]:
    """Credential/dev login — issues a JWT for the given email + role."""
    role = req.role if req.role in auth.ROLES else "viewer"
    user = auth.upsert_user(req.email, req.name, "local", role)
    auth.audit(user["email"], "login provider=local")
    return {"token": auth.create_token(user), "user": user}


@app.get("/auth/{provider}/login")
def oauth_login(provider: str):
    if provider not in auth.OAUTH:
        raise HTTPException(404, "Unknown provider.")
    if not auth.provider_enabled(provider):
        raise HTTPException(400, f"{provider} OAuth is not configured (set client id/secret).")
    return RedirectResponse(auth.authorize_url(provider, state=provider))


@app.get("/auth/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = ""):
    if provider not in auth.OAUTH:
        raise HTTPException(404, "Unknown provider.")
    try:
        profile = auth.exchange_code(provider, code)
    except Exception as exc:  # noqa: BLE001
        auth.audit("?", f"login_failed provider={provider} err={exc}")
        raise HTTPException(401, "OAuth exchange failed.") from exc
    user = auth.upsert_user(profile["email"], profile["name"], provider)
    auth.audit(user["email"], f"login provider={provider}")
    token = auth.create_token(user)
    return RedirectResponse(f"{auth.FRONTEND_URL}/?token={token}")


@app.get("/auth/me")
def me(user: dict[str, Any] = Depends(auth.require_user)) -> dict[str, Any]:
    return user


@app.post("/auth/logout")
def logout(user: dict[str, Any] = Depends(auth.require_user)) -> dict[str, str]:
    auth.audit(user.get("sub", "?"), "logout")
    return {"status": "ok"}


@app.get("/auth/users")
def users(_: dict[str, Any] = Depends(auth.require_role("admin"))) -> list[dict[str, Any]]:
    return auth.list_users()


@app.post("/auth/users/role")
def change_role(req: RoleRequest,
                admin: dict[str, Any] = Depends(auth.require_role("admin"))) -> dict[str, Any]:
    return auth.set_role(req.email, req.role, by=admin.get("sub", "admin"))


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    return {
        "llm_available": config.llm_available(),
        "llm_model": config.GROQ_MODEL,
        "settings": load_settings(),
        "faiss_models": vectordb.available_models("faiss"),
    }


# --------------------------------------------------------------------------- #
# Upload + analyze (multi-patient)
# --------------------------------------------------------------------------- #
@app.post("/upload")
async def upload(files: list[UploadFile] = File(...), report_date: str = "") -> dict[str, Any]:
    """Process one or more uploaded documents as a single upload batch."""
    documents: list[tuple[str, str | None]] = []
    for f in files:
        data = await f.read()
        text = read_document(data, f.filename or "upload")
        if text.strip():
            documents.append((text, f.filename))
    if not documents:
        raise HTTPException(422, "No readable text in the uploaded file(s).")
    return process_upload(documents, report_date=report_date)


@app.post("/analyze-text")
def analyze_text(req: TextRequest) -> dict[str, Any]:
    return process_upload([(req.text, None)], report_date=req.report_date)


# --------------------------------------------------------------------------- #
# Dashboard / cases / history
# --------------------------------------------------------------------------- #
@app.get("/dashboard/{upload_id}")
def dashboard(upload_id: str) -> dict[str, Any]:
    return {"upload_id": upload_id, "documents_processed": 1,
            **pv_storage.upload_stats(upload_id)}


@app.get("/cases")
def cases(upload_id: str | None = None, seriousness: str | None = None,
          search: str | None = None) -> list[dict[str, Any]]:
    return pv_storage.list_cases(upload_id=upload_id, seriousness=seriousness, search=search)


@app.get("/history")
def history(search: str | None = None) -> list[dict[str, Any]]:
    return pv_storage.list_cases(search=search)


@app.get("/cases/{row_id}")
def get_case(row_id: str) -> dict[str, Any]:
    record = pv_storage.get_case(row_id)
    if not record:
        raise HTTPException(404, "Case not found.")
    return record


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #
@app.get("/cases/{row_id}/report.{fmt}")
def download_report(row_id: str, fmt: str) -> StreamingResponse:
    record = pv_storage.get_case(row_id)
    if not record:
        raise HTTPException(404, "Case not found.")
    report = record["report"]
    table = {"pdf": (pv_report.to_pdf, "application/pdf"),
             "xlsx": (pv_report.to_excel, _XLSX),
             "json": (pv_report.to_json, "application/json")}
    if fmt not in table:
        raise HTTPException(400, "Format must be pdf, xlsx, or json.")
    func, mime = table[fmt]
    name = (record.get("case_id") or row_id).replace("/", "_")
    return StreamingResponse(io.BytesIO(func(report)), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.get("/uploads/{upload_id}/reports.zip")
def download_all(upload_id: str) -> StreamingResponse:
    rows = pv_storage.list_cases(upload_id=upload_id)
    if not rows:
        raise HTTPException(404, "No reports for this upload.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            record = pv_storage.get_case(row["id"])
            if not record:
                continue
            name = (record.get("case_id") or row["id"][:8]).replace("/", "_")
            zf.writestr(f"{name}.pdf", pv_report.to_pdf(record["report"]))
    return StreamingResponse(io.BytesIO(buffer.getvalue()), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{upload_id}_reports.zip"'})
