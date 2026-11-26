# Keeping the user guide up to date

The user guide is part of the product. **Every change that affects what users see or do must update the guide in the same
change (commit / pull request).**

## Where things live

| What | Where |
|---|---|
| Guide pages (Markdown) | `docs/guide/*.md`, shown in the app under **Help** and on GitHub |
| List of guide pages in the app | `PAGES` in `app/routes/help.py` |
| Screenshots | `docs/guide/img/*.png`, generated, never edited by hand |
| Screenshot definitions | `SHOTS` in `scripts/screenshots.py` |
| Demo data used for screenshots | `scripts/demo_data.py` (fictional; never put real data here) |
| Contextual "?" links in the app | `help(...)` macro calls in `app/templates/*.html` |

## When you change the app

1. **Update the text** in the affected guide page(s): button labels, steps, rules, statuses.
2. **Regenerate screenshots**:
   ```bash
   pip install -r requirements-dev.txt
   python -m playwright install chromium     # once
   python -m scripts.screenshots            # all, or: python -m scripts.screenshots emp-area mgr-review
   ```
3. **New page or element worth showing?** Add an entry to `SHOTS`, reference it in the guide as `![Alt text](img/<name>.png)`,
   and run the script for that name. Extend `scripts/demo_data.py` if the screen needs data.
4. **New guide page?** Add the `.md` file and an entry in `PAGES` (`app/routes/help.py`) and in `docs/guide/README.md`.
5. **Renamed a heading?** Check `help(...)` links in the templates. Anchors are derived from headings (lower-case, spaces → `-`).
6. Run `pytest`. `tests/test_help.py` fails if:
   - a guide page does not render,
   - an image referenced in the guide is missing, or a screenshot in `SHOTS` is not used in the guide,
   - a screenshot exists that is not defined in `SHOTS`,
   - a contextual help link in a template points to a missing page or heading,
   - a link between guide pages is broken.
7. Look at the changed screenshots in the diff before committing.

## Style

- Write for the role, in the imperative ("Click **Submit to manager**"). Use the exact labels from the app in **bold**.
- Each role guide starts with *For*, then *What you need to do* (checklist), then steps.
- Keep screenshots focused on one element where possible, and use the `highlight` option to point at the relevant control.
