"""FastAPI application entry point.  Run:  uvicorn app.main:app --reload"""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import Forbidden, LoginRequired
from .db import init_db
from .routes import admin, core, help as help_routes, review
from .web import redirect, render

SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)



@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="AI KSC Self-Assessment", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="strict",
                   https_only=os.environ.get("HTTPS_ONLY", "0") == "1", max_age=8 * 3600)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.mount("/help/img", StaticFiles(directory=str(help_routes.GUIDE_DIR / "img")), name="help-img")
app.include_router(core.router)
app.include_router(review.router)
app.include_router(admin.router)
app.include_router(help_routes.router)


@app.exception_handler(LoginRequired)
def _login_required(request: Request, exc: LoginRequired):
    return redirect("/password" if str(exc) == "password" else "/login")


@app.exception_handler(Forbidden)
def _forbidden(request: Request, exc: Forbidden):
    return render(request, "error.html", status_code=403,
                  message="You do not have access to this page.")


@app.get("/healthz")
def healthz():
    return {"ok": True}
