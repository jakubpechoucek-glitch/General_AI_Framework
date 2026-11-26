"""Regenerate the user-guide screenshots in docs/guide/img.

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python -m scripts.screenshots                 # all screenshots
    python -m scripts.screenshots emp-area adm-matrix   # only some

The app is started on a temporary SQLite database filled with fictional demo data
(scripts/demo_data.py), so no real data ever appears in the screenshots. Every image
referenced by the guide must be listed in SHOTS. tests/test_help.py checks that.
Set CHROMIUM_PATH to use a specific Chromium binary.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "guide" / "img"
PORT = 8799
MARGIN = 8  # px around captured elements, so highlights are not clipped
BASE = f"http://127.0.0.1:{PORT}"

USERS = {
    "admin": "alex.admin@example.com",
    "manager": "maria.manager@example.com",
    "calibrator": "pat.partner@example.com",
    "erin": "erin.employee@example.com",
    "sam": "sam.submitted@example.com",
    "dana": "dana.done@example.com",
    "noah": "noah.new@example.com",
    "nina": "nina.newcomer@example.com",
}

# name, user (None = signed out), path ({ids} substituted), target, options
#   target: CSS selector of the element to capture, or "viewport" (top of page)
#   options: highlight (selector to outline), click (selector to click first),
#            height (viewport crop height), nth (element index)
SHOTS: list[tuple] = [
    # getting started
    ("gs-login", None, "/login", ".login", {}),
    ("gs-password", "nina", "/password", ".login", {}),
    ("gs-nav", "manager", "/", "header.top", {}),
    ("gs-home", "erin", "/", "viewport", {"height": 560}),
    ("gs-scale", "erin", "/framework", ".table-wrap", {}),
    ("gs-help", "erin", "/help", "viewport", {"height": 620}),
    # employee
    ("emp-start", "noah", "/assessment", "main .card", {"click": "input[value=no]"}),
    ("emp-form", "erin", "/assessment/{erin}", "viewport", {"height": 760}),
    ("emp-area", "erin", "/assessment/{erin}", ".area", {"highlight": ".area .levels"}),
    ("emp-submit", "erin", "/assessment/{erin}", ".sticky-actions",
     {"highlight": "button[value=submit]"}),
    ("emp-errors", "erin", "/assessment/{erin}", ".area.has-error",
     {"click": "button[value=submit]"}),
    ("emp-results-indicative", "sam", "/assessment/{sam}/results", "viewport", {"height": 620}),
    ("emp-results-official", "dana", "/assessment/{dana}/results", "viewport", {"height": 760}),
    ("emp-priorities", "dana", "/assessment/{dana}/results", ".table-wrap", {}),
    # manager
    ("mgr-home", "manager", "/", "viewport", {"height": 480}),
    ("mgr-team", "manager", "/team", "main", {}),
    ("mgr-review", "manager", "/review/{sam}", "viewport", {"height": 700}),
    ("mgr-review-actions", "manager", "/review/{sam}", "form .actions",
     {"highlight": "button[value=complete_review]"}),
    ("mgr-calibration", "manager", "/review/{chris}", "viewport", {"height": 700}),
    ("mgr-calibration-actions", "manager", "/review/{chris}", "form .actions",
     {"highlight": "button[value=finalize]"}),
    ("mgr-reopen", "manager", "/review/{dana}", "details.card", {"click": "details summary"}),
    ("mgr-reports", "manager", "/reports", "viewport", {"height": 760}),
    ("mgr-reports-areas", "manager", "/reports", ".table-wrap", {}),
    ("mgr-reports-employees", "manager", "/reports", ".table-wrap", {"nth": -1}),
    # calibration owner
    ("cal-team", "calibrator", "/team", "main", {}),
    # admin
    ("adm-overview", "admin", "/admin", "viewport", {"height": 700}),
    ("adm-areas", "admin", "/admin/areas", "viewport", {"height": 640}),
    ("adm-area-edit", "admin", "/admin/areas/{area}", "main .card", {}),
    ("adm-scale", "admin", "/admin/scale", "viewport", {"height": 640}),
    ("adm-teams", "admin", "/admin/teams", "main", {}),
    ("adm-team", "admin", "/admin/teams/{team}", ".grid", {}),
    ("adm-matrix", "admin", "/admin/teams/{team}", ".matrix", {}),
    ("adm-add-role", "admin", "/admin/teams/{team}", "main > .card", {"nth": -1}),
    ("adm-role", "admin", "/admin/roles/{role}", "main .card", {"highlight": "#vs"}),
    ("adm-users", "admin", "/admin/users", "viewport", {"height": 560}),
    ("adm-users-import", "admin", "/admin/users", "main > .card", {"nth": -1}),
    ("adm-user-edit", "admin", "/admin/users/{user}", "main .card", {}),
    ("adm-credentials", "admin", "/admin/users/{noah_user}", ".flash.warning",
     {"click": "button[value=reset]"}),
    ("adm-cycles", "admin", "/admin/cycles", "main", {}),
    ("adm-import", "admin", "/admin/import", "main .card", {}),
    ("adm-assessments", "admin", "/admin/assessments", "viewport", {"height": 520}),
    ("adm-audit", "admin", "/admin/audit", "viewport", {"height": 520}),
]


def _start_server():
    import uvicorn

    from app.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    raise RuntimeError("server did not start")


def _launch(p):
    exe = os.environ.get("CHROMIUM_PATH")
    if exe:
        return p.chromium.launch(executable_path=exe)
    try:
        return p.chromium.launch()
    except Exception:  # noqa: BLE001 - fall back to a preinstalled Chromium
        import glob
        found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
        if not found:
            raise
        return p.chromium.launch(executable_path=found[-1])


def main(only: list[str]):
    tmp = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/shots.db"
    os.environ.setdefault("SECRET_KEY", "screenshots")
    sys.path.insert(0, str(ROOT))

    from app.db import SessionLocal, init_db
    from scripts import demo_data

    init_db()
    with SessionLocal() as db:
        ids = demo_data.seed(db)
        from app.models import Assessment, User
        ids["chris"] = db.query(Assessment).join(User, Assessment.employee_id == User.id) \
            .filter(User.email == "chris.calibration@example.com").one().id
        ids["noah_user"] = db.query(User).filter_by(email=USERS["noah"]).one().id
        db.commit()
    _start_server()

    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    shots = [s for s in SHOTS if not only or s[0] in only]
    with sync_playwright() as p:
        browser = _launch(p)
        contexts = {}

        def page_for(user):
            if user not in contexts:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                          device_scale_factor=1.5)
                pg = ctx.new_page()
                if user:
                    pg.goto(BASE + "/login")
                    pg.fill("#email", USERS[user])
                    pg.fill("#password", demo_data.DEMO_PASSWORD)
                    pg.click("button[type=submit]")
                    pg.wait_for_load_state("networkidle")
                contexts[user] = pg
            return contexts[user]

        for name, user, path, target, opts in shots:
            pg = page_for(user)
            pg.goto(BASE + path.format(**ids))
            pg.wait_for_load_state("networkidle")
            if opts.get("click"):
                pg.click(opts["click"])
                pg.wait_for_load_state("networkidle")
            if opts.get("highlight"):
                pg.eval_on_selector(opts["highlight"],
                                    "e => { e.style.outline = '3px solid #e8590c';"
                                    " e.style.outlineOffset = '3px'; }")
            out = OUT / f"{name}.png"
            if target == "viewport":
                pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": 1280,
                                                   "height": opts.get("height", 800)})
            else:
                loc = pg.locator(target)
                loc = loc.last if opts.get("nth") == -1 else loc.nth(opts.get("nth", 0))
                loc.scroll_into_view_if_needed()
                box = pg.evaluate("""el => { const r = el.getBoundingClientRect();
                    return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height}; }""",
                                  loc.element_handle())
                m = MARGIN
                x, y = max(box["x"] - m, 0), max(box["y"] - m, 0)
                pg.screenshot(path=str(out), full_page=True,
                              clip={"x": x, "y": y, "width": min(box["w"] + 2 * m, 1280 - x),
                                    "height": box["h"] + 2 * m})
            print("saved", out.relative_to(ROOT))
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
