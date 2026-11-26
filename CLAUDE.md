# Project rules

- **User guide must stay in sync with the app.** Any change to UI, workflow, rules or labels must update `docs/guide/*.md`
  and regenerate affected screenshots (`python -m scripts.screenshots`) in the same change. See `docs/guide/MAINTAINING.md`.
  `pytest` (tests/test_help.py) enforces links, anchors and screenshot coverage.
- Never commit organisational data (workbooks, databases, real names). Screenshots use only `scripts/demo_data.py`.
- Gap rules live in `app/logic.py` and are documented in `docs/assessment-rules.md`; keep both aligned.
- Run `pytest` before committing.
