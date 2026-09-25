const $ = id => document.getElementById(id);
const token = location.hash.slice(1);
let state, selected = [], queue = Promise.resolve(), pending = 0, finished = false, builderInitialized = false;
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
  renderBuilder();
  if (rebuild) { renderProperties(); renderRcProperties(); }
  else for (const row of [...$('properties').children, ...$('rc-properties').children]) {
    const props = row.dataset.scope === 'rc' ? next.rc_properties : next.properties;
    const prop = props.find(item => item.name === row.dataset.name);
    const input = row.querySelector('input,textarea');
    if (!prop || document.activeElement === input || drafts.has(input)) continue;
    if (input.type === 'checkbox') input.checked = prop.value;
    else input.value = prop.input_type ? (prop.value ?? '') : prop.value === null || typeof prop.value === 'object' ? JSON.stringify(prop.value) : prop.value;
  }
}
function bindingFields(container, name, bindings = {}, onChange = null) {
  const target = $(container); target.replaceChildren();
  const spec = state.functions[name];
  if (!spec) return;
  for (const field of [...spec.positional, ...spec.optional]) {
    const row = document.createElement('div'); row.className = 'binding-field';
    const label = document.createElement('label');
    label.textContent = field + (spec.required.includes(field) ? ' *' : ' (optional)');
    const select = document.createElement('select'); select.dataset.field = field;
    select.setAttribute('aria-label', container + ' ' + field);
    const blank = document.createElement('option'); blank.value = '';
    blank.textContent = spec.required.includes(field) ? 'Choose a data key…' : 'Use default / literal';
    select.append(blank);
    for (const dataset of state.datasets) {
      const option = document.createElement('option');
      option.value = JSON.stringify(dataset.key);
      option.textContent = dataset.key + ' — ' + dataset.description;
      select.append(option);
    }
    select.value = Object.hasOwn(bindings, field) ? JSON.stringify(bindings[field]) : '';
    select.onchange = () => {
      if (onChange) onChange(readBindings(container));
      else updateAddButton();
    };
    label.append(select); row.append(label); target.append(row);
  }
}
function readBindings(container) {
  const bindings = {};
  for (const select of $(container).querySelectorAll('select')) {
    if (select.value !== '') bindings[select.dataset.field] = JSON.parse(select.value);
  }
  return bindings;
}
function updateAddButton() {
  const spec = state.functions[$('plot-function').value];
  const bindings = readBindings('new-bindings');
  $('add-plot').disabled = !spec || spec.required.some(field => !Object.hasOwn(bindings, field));
}
function renderBuilder() {
  if (!state.builder) return;
  if (!builderInitialized) {
    for (const name of Object.keys(state.functions)) {
      const option = document.createElement('option'); option.value = name; option.textContent = name + '(…)';
      $('plot-function').append(option);
    }
    $('data-summary').textContent = state.datasets.length ? `${state.datasets.length} named data entries available. Choose a function and its inputs.` : 'No data entries. Pass a dictionary to figureforge.run(data).';
    $('plot-function').onchange = () => { bindingFields('new-bindings', $('plot-function').value); updateAddButton(); };
    bindingFields('new-bindings', $('plot-function').value);
    updateAddButton();
    builderInitialized = true;
  }
  $('remove-plot').hidden = !state.layer;
  if (state.layer) {
    const path = [...selected];
    bindingFields('layer-bindings', state.layer.function, state.layer.bindings, bindings => {
      flushDrafts();
      enqueue(async () => {
        try { render(await api('/api/edit', {op: 'bind', path, bindings})); $('error').hidden = true; }
        catch (error) { renderBuilder(); throw error; }
      });
    });
  } else $('layer-bindings').replaceChildren();
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
  renderFields(state.properties, 'properties', 'actor');
  filterProperties();
}
function renderRcProperties() {
  renderFields(state.rc_properties, 'rc-properties', 'rc');
  filterRcProperties();
}
function renderFields(properties, containerId, scope) {
  $(containerId).replaceChildren();
  for (const prop of properties) {
    const row = document.createElement('div'); row.className = 'property'; row.dataset.name = prop.name; row.dataset.scope = scope;
    const label = document.createElement('label'); label.textContent = prop.name;
    const complex = !prop.input_type && (prop.value === null || typeof prop.value === 'object');
    const input = document.createElement(complex ? 'textarea' : 'input');
    if (!complex) input.type = prop.input_type || (typeof prop.value === 'boolean' ? 'checkbox' : typeof prop.value === 'number' ? 'number' : 'text');
    if (input.type === 'number') input.step = 'any';
    if (input.type === 'checkbox') input.checked = prop.value;
    else input.value = complex ? JSON.stringify(prop.value) : (prop.value ?? '');
    if (prop.input_type) input.placeholder = 'Matplotlib default';
    input.title = prop.hint; input.setAttribute('aria-label', prop.name);
    input.disabled = !prop.editable;
    if (!prop.editable) {
      const note = document.createElement('small'); note.className = 'parameter-note';
      note.textContent = 'Set in Python'; note.title = prop.hint; label.append(note);
    }
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
          const next = await api('/api/edit', {path, scope, property: prop.name, value, reset: !!prop.input_type && value === '' && prop.name !== 'label'});
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
    label.append(input); row.append(label);
    if (scope === 'actor' && prop.editable) {
      const reset = document.createElement('button'); reset.className = 'reset-parameter';
      reset.textContent = state.builder ? 'Use Matplotlib default' : 'Use initial / global value';
      reset.title = 'Remove this override and inherit the global Matplotlib default.';
      reset.onclick = () => {
        flushDrafts();
        enqueue(async () => { render(await api('/api/edit', {path, property: prop.name, reset: true})); $('error').hidden = true; });
      };
      row.append(reset);
    }
    $(containerId).append(row);
  }
}
function filterRcProperties() {
  const query = $('rc-search').value.toLowerCase();
  for (const row of $('rc-properties').children) row.hidden = !row.dataset.name.includes(query);
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
$('add-plot').onclick = () => {
  const fn = $('plot-function').value, bindings = readBindings('new-bindings');
  flushDrafts();
  enqueue(async () => { render(await api('/api/edit', {op: 'add', function: fn, bindings})); $('error').hidden = true; });
};
$('remove-plot').onclick = () => {
  const path = [...selected]; flushDrafts();
  enqueue(async () => { render(await api('/api/edit', {op: 'remove', path})); $('error').hidden = true; });
};
$('artist-search').oninput = () => state && renderTree();
$('property-search').oninput = filterProperties;
$('rc-search').oninput = filterRcProperties;
for (const action of ['undo', 'reset']) $(action).onclick = () => { flushDrafts(); enqueue(async () => { render(await api('/api/' + action, {path: selected})); $('error').hidden = true; }); };
$('download-code').onclick = () => { flushDrafts(); enqueue(async () => download(state.code, 'make_figure.py', 'text/x-python')); };
$('copy').onclick = () => { flushDrafts(); enqueue(async () => { await navigator.clipboard.writeText(state.code); $('copy').textContent = 'Copied!'; setTimeout(() => $('copy').textContent = 'Copy code', 1600); }); };
$('download-image').onclick = () => { flushDrafts(); enqueue(async () => { const link = document.createElement('a'); link.href = state.preview; link.download = 'figure.png'; link.click(); }); };
$('finish').onclick = () => { flushDrafts(); enqueue(async () => { await api('/api/finish', {}); finished = true; for (const el of document.querySelectorAll('button,input,textarea,select')) el.disabled = true; }); };
enqueue(async () => render(await api('/api/state')));
