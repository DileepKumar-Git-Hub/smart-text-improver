const qs = (s) => document.querySelector(s);
let lastCorrected = "";

// Highlight differences between original & corrected text
function highlightDiff(original, corrected) {
  const o = original.split(/(\s+)/);
  const c = corrected.split(/(\s+)/);
  let i = 0, j = 0, res = [];
  while (i < o.length && j < c.length) {
    if (o[i] === c[j]) { res.push(o[i]); i++; j++; continue; }
    if (o[i].trim() && c[j].trim()) {
      res.push(`<span class="hl-del">${o[i]}</span><span class="hl-add">${c[j]}</span>`);
      i++; j++; continue;
    }
    res.push(c[j]); j++;
  }
  while (j < c.length) res.push(c[j++]);
  return res.join('');
}

// Render statistics badges
function renderBadges(data) {
  const b = [];
  b.push(`<span class="badge">Words: ${data.metrics.words}</span>`);
  b.push(`<span class="badge">Sentences: ${data.metrics.sentences}</span>`);
  b.push(`<span class="badge">Spelling fixes: ${data.suggestions.length}</span>`);
  qs('#badges').innerHTML = `<div class="badges">${b.join('')}</div>`;

  // Update Grammar Score & Readability
  qs('#extraMetrics').classList.remove('hidden');
  qs('#grammarScore').textContent = `${data.grammar_score}%`;
  qs('#readabilityIndex').textContent = data.readability;
}

// Fetch corrected text + metrics from backend
async function correctNow() {
  const text = qs('#input').value;
  const r = await fetch('/api/correct', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  const data = await r.json();

  lastCorrected = data.corrected;
  qs('#outText').innerHTML = highlightDiff(data.original, data.corrected);
  renderBadges(data);

  const sugWrap = qs('#suggestions');
  if (data.suggestions.length) {
    sugWrap.innerHTML = '<ul>' +
      data.suggestions.map(s => `<li><b>${s.from}</b> → <b>${s.to}</b> <span class="muted">(${(s.candidates || []).slice(0, 5).join(', ')})</span></li>`).join('') +
      '</ul>';
  } else {
    sugWrap.innerHTML = '<span class="muted">No spelling suggestions — looks good! ✅</span>';
  }
  return data;
}

// Button Actions
qs('#btnCorrect').addEventListener('click', correctNow);
qs('#btnClear').addEventListener('click', () => {
  qs('#input').value = '';
  qs('#outText').textContent = '';
  qs('#suggestions').textContent = '';
  qs('#badges').innerHTML = '';
  qs('#extraMetrics').classList.add('hidden');
  lastCorrected = "";
});
qs('#btnCopy').addEventListener('click', () => {
  if (!lastCorrected) { alert('Nothing to copy yet.'); return; }
  navigator.clipboard.writeText(lastCorrected).then(() => alert('✅ Copied to clipboard')).catch(() => alert('❌ Copy failed'));
});
qs('#btnDownload').addEventListener('click', () => {
  if (!lastCorrected) { alert('Nothing to download yet.'); return; }
  const blob = new Blob([lastCorrected], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'corrected.txt';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 400);
});

// Live correction on typing
let t = null;
qs('#input').addEventListener('input', () => {
  clearTimeout(t);
  t = setTimeout(correctNow, 500);
});

// Add custom word to dictionary
qs('#addWordBtn').addEventListener('click', async () => {
  const w = qs('#dictWord').value.trim();
  if (!w) return;
  const r = await fetch('/api/add_word', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word: w })
  });
  const j = await r.json();
  if (j.success) {
    alert(`✅ Word "${j.word}" added to dictionary.`);
    qs('#dictWord').value = '';
  } else {
    alert('❌ ' + j.error);
  }
});

// File upload autocorrect
qs('#btnFileCorrect').addEventListener('click', async () => {
  const fi = qs('#fileInput');
  if (!fi.files.length) { alert('Please choose a .txt file first'); return; }
  const fd = new FormData(); fd.append('file', fi.files[0]);
  const r = await fetch('/api/correct_file', { method: 'POST', body: fd });
  const j = await r.json();
  if (!j.success) { alert('❌ ' + j.error); return; }
  lastCorrected = j.corrected;
  qs('#outText').textContent = lastCorrected;
  renderBadges(j);
  qs('#suggestions').innerHTML = '<ul>' + j.suggestions.map(s => `<li><b>${s.from}</b> → <b>${s.to}</b></li>`).join('') + '</ul>';
});

qs('#btnFileDownload').addEventListener('click', () => {
  if (!lastCorrected) { alert('No corrected text to download.'); return; }
  const blob = new Blob([lastCorrected], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'file_corrected.txt';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 400);
});
