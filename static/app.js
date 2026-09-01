/* 前端逻辑：与本地 Flask 后端交互（离线运行，无任何外部请求） */

let CONFIG = null;
let currentImage = null;    // { name, url } 铭牌图片
let attachments = [];       // [{ name, original }] 已上传附件

const $ = (id) => document.getElementById(id);

/* ---------- 通用工具 ---------- */
function toast(msg, isError) {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' error' : '');
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = 'toast'; el.hidden = true; }, 3200);
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || ('请求失败（' + res.status + '）'));
  }
  return data;
}

/* ---------- 初始化 ---------- */
async function init() {
  try {
    CONFIG = await fetchJson('/api/config');
  } catch (e) {
    toast('加载配置失败：' + e.message, true);
    return;
  }
  $('app-title').textContent = CONFIG.title;
  document.title = CONFIG.title;
  buildFields(CONFIG.fields);
  if (!CONFIG.ocr_available) {
    toast('警告：OCR 引擎不可用（离线模型缺失），请检查打包', true);
  }
}

/* ---------- 表单字段 ---------- */
function buildFields(fields) {
  const form = $('fields-form');
  form.innerHTML = '';
  (fields || []).forEach(f => {
    const wrap = document.createElement('div');
    wrap.className = 'field';

    const label = document.createElement('label');
    label.textContent = f.label;
    label.htmlFor = 'f-' + f.key;

    const input = document.createElement('input');
    input.type = 'text';
    input.id = 'f-' + f.key;
    input.dataset.key = f.key;
    input.placeholder = '请输入' + f.label;

    wrap.appendChild(label);
    wrap.appendChild(input);
    form.appendChild(wrap);
  });
}

function setFieldValue(key, value) {
  const input = document.querySelector('#fields-form input[data-key="' + key + '"]');
  if (!input || !value) return;
  // 仅填充空字段，避免覆盖用户已输入的内容
  if (input.value.trim() === '') {
    input.value = value;
    input.classList.add('auto-filled');
    setTimeout(() => input.classList.remove('auto-filled'), 2500);
  }
}

/* ---------- 图片选择与 OCR ---------- */
function setupImageUpload() {
  const input = $('image-input');
  const dropzone = $('dropzone');

  $('btn-pick-image').addEventListener('click', () => input.click());
  dropzone.addEventListener('click', (e) => {
    if (e.target.tagName !== 'BUTTON') input.click();
  });
  input.addEventListener('change', () => {
    if (input.files.length) handleImage(input.files[0]);
    input.value = '';
  });
  // 浏览器中支持拖拽（桌面窗口内用按钮选择即可）
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleImage(e.dataTransfer.files[0]);
  });
}

async function handleImage(file) {
  const status = $('ocr-status');
  status.hidden = false;
  status.textContent = '正在离线识别文字，请稍候…（首次识别需加载模型，约十几秒）';

  const fd = new FormData();
  fd.append('image', file);

  try {
    const data = await fetchJson('/api/ocr', { method: 'POST', body: fd });

    currentImage = { name: data.image, url: '/uploads/' + data.image };
    $('preview-img').src = currentImage.url;
    $('preview-meta').textContent = file.name;
    $('image-preview').hidden = false;

    renderOcrLines(data.texts || [], data.items || []);
    Object.keys(data.extracted || {}).forEach(k => setFieldValue(k, data.extracted[k]));

    const n = Object.keys(data.extracted || {}).length;
    status.textContent = '识别完成：共 ' + (data.texts || []).length + ' 行文字' +
      (n ? '，自动填入 ' + n + ' 个字段' : '');
    toast('识别完成，请核对并补充信息');
  } catch (e) {
    status.textContent = '';
    toast('识别失败：' + e.message, true);
  }
}

function renderOcrLines(texts, items) {
  const box = $('ocr-result');
  box.innerHTML = '';
  if (!texts.length) {
    box.innerHTML = '<div class="empty-hint">未识别到文字。请确认图片清晰、文字朝向正确后重试。</div>';
    return;
  }
  texts.forEach((t, i) => {
    const div = document.createElement('div');
    div.className = 'ocr-line';
    div.title = '点击复制';

    const txt = document.createElement('span');
    txt.className = 'txt';
    txt.textContent = t;

    const score = document.createElement('span');
    score.className = 'score';
    score.textContent = Math.round(((items[i] || {}).score || 1) * 100) + '%';

    div.appendChild(txt);
    div.appendChild(score);
    div.addEventListener('click', () => copyText(t));
    box.appendChild(div);
  });
}

function copyText(text) {
  const done = () => toast('已复制：' + text);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

function fallbackCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (e) { /* 忽略 */ }
  document.body.removeChild(ta);
  done();
}

/* ---------- 附件上传 ---------- */
function setupAttachmentUpload() {
  const input = $('attach-input');
  $('btn-pick-attach').addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    for (const file of Array.from(input.files)) {
      await uploadAttachment(file);
    }
    input.value = '';
  });
}

async function uploadAttachment(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const data = await fetchJson('/api/upload_attachment', { method: 'POST', body: fd });
    attachments.push({ name: data.filename, original: data.original });
    renderAttachments();
    toast('附件已上传：' + data.original);
  } catch (e) {
    toast('附件上传失败：' + e.message, true);
  }
}

function renderAttachments() {
  const ul = $('attach-list');
  ul.innerHTML = '';
  attachments.forEach((a, i) => {
    const li = document.createElement('li');
    const name = document.createElement('span');
    name.className = 'att-name';
    name.textContent = a.original;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'att-remove';
    btn.textContent = '移除';
    btn.addEventListener('click', () => {
      attachments.splice(i, 1);
      renderAttachments();
    });
    li.appendChild(name);
    li.appendChild(btn);
    ul.appendChild(li);
  });
}

/* ---------- 生成文件 ---------- */
function setupGenerate() {
  $('btn-generate').addEventListener('click', generate);
  $('btn-open-folder').addEventListener('click', async () => {
    try { await fetchJson('/api/open_output_folder'); } catch (e) { /* 忽略 */ }
  });
}

async function generate() {
  const fields = {};
  document.querySelectorAll('#fields-form input').forEach(i => {
    fields[i.dataset.key] = i.value.trim();
  });

  const payload = {
    fields: fields,
    image_name: currentImage ? currentImage.name : null,
    attachments: attachments,   // [{name, original}]
  };

  const btn = $('btn-generate');
  btn.disabled = true;
  btn.textContent = '正在生成…';
  try {
    const data = await fetchJson('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    renderOutputs(data.outputs, data.att_notes);
    toast('生成成功！');
  } catch (e) {
    toast('生成失败：' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚙ 生成 Word / Excel 文件';
  }
}

function renderOutputs(outputs, attNotes) {
  const box = $('outputs');
  box.innerHTML = '';
  (outputs || []).forEach(o => {
    const div = document.createElement('div');
    div.className = 'out-item';

    const type = document.createElement('span');
    type.className = 'out-type ' + o.type;
    type.textContent = o.type === 'word' ? 'Word' : 'Excel';

    const link = document.createElement('a');
    link.href = '/output/' + o.name;
    link.textContent = '⬇ 下载 ' + o.name;
    link.setAttribute('download', o.name);

    div.appendChild(type);
    div.appendChild(link);
    box.appendChild(div);
  });
  if (attNotes && attNotes.length) {
    const note = document.createElement('div');
    note.className = 'out-note';
    note.textContent = '提示：以下附件为非图片格式，已将其文件名写入 Word「附件」处：' + attNotes.join('、');
    box.appendChild(note);
  }
  $('btn-open-folder').hidden = !(outputs || []).length;
}

/* ---------- 启动 ---------- */
document.addEventListener('DOMContentLoaded', () => {
  init();
  setupImageUpload();
  setupAttachmentUpload();
  setupGenerate();
});
