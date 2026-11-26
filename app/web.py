"""Template rendering helpers and flash messages."""
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import logic

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(
    status_css=logic.STATUS_CSS,
    status_of=logic.status,
    self_gap=logic.self_gap,
    dev_gap=logic.development_gap,
    surplus=logic.surplus,
)


def _pct(v):
    return "—" if v is None else f"{round(v * 100)}%"


def _num(v, digits=1):
    return "—" if v is None else f"{v:.{digits}f}"


def _dt(v):
    return "—" if not v else v.strftime("%d %b %Y")


templates.env.filters.update(pct=_pct, num=_num, dt=_dt)


def flash(request: Request, message: str, kind: str = "info"):
    request.session.setdefault("flash", []).append([kind, message])


def render(request: Request, name: str, status_code: int = 200, **ctx):
    from .db import SessionLocal
    from .models import User

    user = None
    uid = request.session.get("uid")
    if uid:
        with SessionLocal() as db:
            user = db.get(User, uid)
            is_mgr = bool(user) and db.query(User.id).filter(User.manager_id == uid).first() is not None
    ctx.setdefault("me", user)
    ctx.setdefault("me_is_manager", is_mgr if uid else False)
    ctx["flashes"] = request.session.pop("flash", [])
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
