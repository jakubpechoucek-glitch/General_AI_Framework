// Progressive enhancement only; every page works without JavaScript.
document.addEventListener('click', (e) => {
  const c = e.target.closest('[data-confirm]');
  if (c && !confirm(c.dataset.confirm)) e.preventDefault();
  const d = e.target.closest('[data-download-table]');
  if (d) {
    const rows = [...document.querySelectorAll(d.dataset.downloadTable + ' tr')]
      .map(tr => [...tr.children].map(td => '"' + td.innerText.replace(/"/g, '""') + '"').join(','));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([rows.join('\n')], {type: 'text/csv'}));
    a.download = d.dataset.filename || 'export.csv';
    a.click();
  }
});
// Role mismatch toggle on the start page
document.querySelectorAll('input[name="confirm"]').forEach(r => r.addEventListener('change', () => {
  const box = document.getElementById('mismatch');
  if (box) box.hidden = document.querySelector('input[name="confirm"]:checked').value !== 'no';
}));
// Self-assessment progress + evidence hint
const form = document.getElementById('selfform');
if (form) {
  const cards = [...form.querySelectorAll('[data-response]')];
  const update = () => {
    let n = 0;
    cards.forEach(card => {
      const sel = card.querySelector('input[type=radio][name^="level_"]:checked');
      if (sel) n++;
      const hint = card.querySelector('[data-ev-hint]');
      const ta = card.querySelector('textarea');
      const need = sel && +sel.value >= 2;
      if (hint) hint.textContent = need ? '(required for this level)' : '(required for levels 2–4, recommended for level 1)';
      if (ta) ta.required = false;
      card.style.borderLeft = need && !ta.value.trim() ? '4px solid #f59e0b' : '';
    });
    document.getElementById('answered').textContent = n;
    document.getElementById('progressbar').style.width = (cards.length ? 100 * n / cards.length : 0) + '%';
  };
  form.addEventListener('input', update); form.addEventListener('change', update); update();
}
// Matrix select colouring
document.querySelectorAll('.matrix select').forEach(s => s.addEventListener('change', () => { s.className = 'l' + s.value; }));
// Filter role list by team on the employee form
const team = document.getElementById('tm'), role = document.getElementById('rl');
if (team && role) {
  const f = () => [...role.options].forEach(o => { if (o.dataset.team) o.hidden = team.value && o.dataset.team !== team.value; });
  team.addEventListener('change', f); f();
}
