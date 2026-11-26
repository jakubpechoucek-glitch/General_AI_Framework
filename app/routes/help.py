"""In-app user guide.

The guide is written once, as Markdown in docs/guide/, and served here under /help.
The same files render on GitHub. Screenshots live in docs/guide/img and are regenerated
with `python -m scripts.screenshots` (see docs/guide/MAINTAINING.md).
"""
import re
from functools import lru_cache
from pathlib import Path

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..web import render

GUIDE_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "guide"

# slug, title, who it is for, short description
PAGES = [
    ("getting-started", "Getting started", "Everyone",
     "Signing in, your password, finding your way around, the 0–4 scale and status colours."),
    ("employee", "Employee guide", "Every employee",
     "How to complete your AI self-assessment and read your results."),
    ("manager", "Manager guide", "Line managers",
     "How to review your team's self-assessments, validate levels and use the gap reports."),
    ("calibration", "Calibration owner guide", "People & Culture / L&D calibration owners",
     "How to calibrate and finalise assessments across a team and use the reports."),
    ("admin", "Administrator guide", "Application administrators",
     "How to maintain the framework, roles and employees, run cycles and onboard new teams."),
    ("faq", "FAQ and glossary", "Everyone", "Common questions and the terms used in the app."),
]
SLUGS = {p[0] for p in PAGES}

router = APIRouter()


@lru_cache(maxsize=32)
def _render_markdown(slug: str, mtime: float) -> tuple[str, str, str]:
    text = (GUIDE_DIR / f"{slug}.md").read_text(encoding="utf-8")
    md = markdown.Markdown(extensions=["tables", "toc", "attr_list", "fenced_code", "sane_lists"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    html = md.convert(text)
    # GitHub-style links between guide pages ("employee.md#x") -> app links ("employee#x")
    html = re.sub(r'href="([a-z0-9-]+)\.md(#[^"]*)?"', r'href="\1\2"', html)
    # make screenshots open full size
    html = re.sub(r'(<img[^>]*src="(img/[^"]+)"[^>]*>)', r'<a href="\2" target="_blank">\1</a>', html)
    title = next((t for s, t, *_ in PAGES if s == slug), slug)
    return html, md.toc, title


def page_html(slug: str):
    path = GUIDE_DIR / f"{slug}.md"
    return _render_markdown(slug, path.stat().st_mtime)


def _me(request):
    from ..db import SessionLocal
    from ..models import User
    uid = request.session.get("uid")
    if not uid:
        return None, False
    with SessionLocal() as db:
        u = db.get(User, uid)
        mgr = bool(u) and db.query(User.id).filter(User.manager_id == uid).first() is not None
        return u, mgr


@router.get("/help")
def help_index(request: Request):
    me, is_mgr = _me(request)
    mine = {"getting-started", "employee", "faq"}
    if me and is_mgr:
        mine.add("manager")
    if me and me.is_calibrator:
        mine.add("calibration")
    if me and me.is_admin:
        mine |= SLUGS
    return render(request, "help_index.html", me=me, me_is_manager=is_mgr, pages=PAGES,
                  mine=mine if me else SLUGS)


@router.get("/help/{slug}")
def help_page(slug: str, request: Request):
    if slug not in SLUGS:
        return HTMLResponse("Guide page not found", status_code=404)
    me, is_mgr = _me(request)
    html, toc, title = page_html(slug)
    return render(request, "help_page.html", me=me, me_is_manager=is_mgr, pages=PAGES,
                  slug=slug, title=title, body=html, toc=toc)
