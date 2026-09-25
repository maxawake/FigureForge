const $ = id => document.getElementById(id);
const token = location.hash.slice(1);
let state, selected = [], queue = Promise.resolve(), pending = 0, finished = false;
const drafts = new Map();
async function api(path, data) {
  const response = await fetch(path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {'X-FigureForge-Token': token, 'Content-Type': 'application/json'},
    ...(data === undefined ? {} : {body: JSON.stringify(data)})
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function showError(error) { $('error').textContent = error.message; $('error').hidden = false; }
function enqueue(task) {
  pending++;
  $('status').textContent = 'Updating…';
  queue = queue.then(task).catch(showError).finally(() => {
    pending--;
    $('status').textContent = finished ? 'Session finished' : pending ? 'Updating…' : `Live preview · ${state?.edits || 0} edits`;
  });
  return queue;
}
function render(next, rebuild = true) {
  state = next; selected = next.selected;
  $('preview').src = next.preview; $('code').textContent = next.code;
  $('undo').disabled = $('reset').disabled = !next.edits;
  $('artist-count').textContent = next.tree.length;
  renderTree();
  if (rebuild) renderProperties();
  else for (const row of $('properties').children) {
    const prop = next.properties.find(item => item.name === row.dataset.name);
    const input = row.querySelector('input,textarea');
    if (!prop || document.activeElement === input || drafts.has(input)) continue;
    if (input.type === 'checkbox') input.checked = prop.value;
    else input.value = prop.value === null || typeof prop.value === 'object' ? JSON.stringify(prop.value) : prop.value;
  }
}
function renderTree() {
  const query = $('artist-search').value.toLowerCase();
  $('tree').replaceChildren();
  for (const node of state.tree) {
    if (!(node.name + ' ' + node.label).toLowerCase().includes(query)) continue;
    const button = document.createElement('button');
    button.className = 'artist' + (JSON.stringify(node.path) === JSON.stringify(selected) ? ' active' : '');
    button.style.paddingLeft = `${10 + node.depth * 12}px`;
    button.textContent = node.name;
    const label = document.createElement('small'); label.textContent = node.label; button.append(label);
    button.title = `${node.name} ${node.label}`;
    button.onclick = () => { flushDrafts(); enqueue(async () => render(await api('/api/state?path=' + encodeURIComponent(JSON.stringify(node.path))))); };
    $('tree').append(button);
  }
}
function renderProperties() {
  const node = state.tree.find(n => JSON.stringify(n.path) === JSON.stringify(selected));
  $('selected-name').textContent = node?.name || 'Figure';
  $('properties').replaceChildren();
  for (const prop of state.properties) {
    const row = document.createElement('div'); row.className = 'property'; row.dataset.name = prop.name;
    const label = document.createElement('label'); label.textContent = prop.name.replaceAll('_', ' ');
    const complex = prop.value === null || typeof prop.value === 'object';
    const input = document.createElement(complex ? 'textarea' : 'input');
    if (!complex) input.type = typeof prop.value === 'boolean' ? 'checkbox' : typeof prop.value === 'number' ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any';
    if (input.type === 'checkbox') input.checked = prop.value;
    else input.value = complex ? JSON.stringify(prop.value) : prop.value;
    input.title = prop.hint; input.setAttribute('aria-label', prop.name);
    const path = [...selected];
    const commit = () => {
      drafts.delete(input);
      try {
        let value;
        if (input.type === 'checkbox') value = input.checked;
        else if (input.type === 'number') {
          if (!input.value.trim() || !Number.isFinite(Number(input.value))) throw new Error('Enter a finite number for ' + prop.name);
          value = Number(input.value);
        } else value = complex ? JSON.parse(input.value) : input.value;
        enqueue(async () => {
          const next = await api('/api/edit', {path, property: prop.name, value});
          $('error').hidden = true;
          render(next, false);
        });
      } catch (error) { showError(error); }
    };
    input.addEventListener('input', () => {
      clearTimeout(drafts.get(input)?.timer);
      drafts.set(input, {commit, timer: setTimeout(commit, 450)});
    });
    input.addEventListener('change', () => {
      const draft = drafts.get(input);
      if (draft) { clearTimeout(draft.timer); commit(); }
    });
    label.append(input); row.append(label); $('properties').append(row);
  }
  filterProperties();
}
function flushDrafts() { for (const draft of [...drafts.values()]) { clearTimeout(draft.timer); draft.commit(); } }
function filterProperties() {
  const query = $('property-search').value.toLowerCase().replaceAll(' ', '_');
  for (const row of $('properties').children) row.hidden = !row.dataset.name.includes(query);
}
function download(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('artist-search').oninput = () => state && renderTree();
$('property-search').oninput = filterProperties;
for (const action of ['undo', 'reset']) $(action).onclick = () => { flushDrafts(); enqueue(async () => { render(await api('/api/' + action, {path: selected})); $('error').hidden = true; }); };
$('download-code').onclick = () => { flushDrafts(); enqueue(async () => download(state.code, 'figure_settings.py', 'text/x-python')); };
$('copy').onclick = () => { flushDrafts(); enqueue(async () => { await navigator.clipboard.writeText(state.code); $('copy').textContent = 'Copied!'; setTimeout(() => $('copy').textContent = 'Copy code', 1600); }); };
$('download-image').onclick = () => { flushDrafts(); enqueue(async () => { const link = document.createElement('a'); link.href = state.preview; link.download = 'figure.png'; link.click(); }); };
$('finish').onclick = () => { flushDrafts(); enqueue(async () => { await api('/api/finish', {}); finished = true; for (const el of document.querySelectorAll('button,input,textarea')) el.disabled = true; }); };
enqueue(async () => render(await api('/api/state')));
