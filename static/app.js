/* 前端逻辑：与本地 Flask 后端交互（离线运行，无任何外部请求） */

let CONFIG = null;
let currentImage = null;    // { name, url } 铭牌图片
let attachments = [];       // [{ name, original }] 已上传附件
let selectedOutputDir = '';

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
function localDateIso() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function datePickerValue(value) {
  const text = String(value || '').trim();
  const m = text.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!m) return '';
  return m[1] + '-' + String(m[2]).padStart(2, '0') + '-' + String(m[3]).padStart(2, '0');
}

function syncCustomSelect(select, custom) {
  const active = select.value === '手动输入';
  custom.hidden = !active;
  if (!active) custom.value = '';
}

function buildFields(fields) {
  ['info-fields', 'trend-fields', 'blue-fields', 'excel-fields'].forEach(id => { $(id).innerHTML = ''; });
  (fields || []).forEach(f => {
    if (f.hidden) return;
    const target = f.group === '工程信息' ? $('info-fields') :
      (f.group === '工程动向' ? $('trend-fields') :
      (f.group === 'Excel补充' ? $('excel-fields') : $('blue-fields')));
    const wrap = document.createElement('div');
    wrap.className = 'field field-' + f.key;

    const label = document.createElement('label');
    label.textContent = f.label;
    label.htmlFor = 'f-' + f.key;

    const dateText = f.input_type === 'date' && f.allow_text;
    const input = f.input_type === 'textarea' ? document.createElement('textarea') :
      (f.input_type === 'select' ? document.createElement('select') : document.createElement('input'));
    if (f.input_type !== 'textarea' && f.input_type !== 'select') {
      input.type = dateText ? 'text' : (f.input_type === 'date' ? 'date' : 'text');
    }
    input.id = 'f-' + f.key;
    input.dataset.key = f.key;
    input.placeholder = dateText ? '请输入日期，可手写或点击日历' : '请输入' + f.label;

    let inputHolder = input;
    if (dateText) {
      const control = document.createElement('div');
      control.className = 'date-control';
      const picker = document.createElement('input');
      picker.type = 'date';
      picker.className = 'date-picker-native';
      picker.tabIndex = -1;
      picker.setAttribute('aria-hidden', 'true');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'date-picker-btn';
      button.textContent = '📅';
      button.title = '打开日历选择日期';
      button.addEventListener('click', () => {
        picker.value = datePickerValue(input.value);
        try {
          if (picker.showPicker) picker.showPicker();
          else picker.click();
        } catch (e) {
          picker.click();
        }
      });
      picker.addEventListener('change', () => {
        if (picker.value) input.value = picker.value;
      });
      control.appendChild(input);
      control.appendChild(button);
      control.appendChild(picker);
      inputHolder = control;
    }

    if (f.input_type === 'select') {
      if (f.default === undefined) {
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '请选择' + f.label;
        placeholder.disabled = true;
        placeholder.selected = true;
        input.appendChild(placeholder);
      }
      (f.options || []).forEach(option => {
        const item = document.createElement('option');
        item.value = option; item.textContent = option;
        input.appendChild(item);
      });
    }
    if (f.default !== undefined) input.value = f.default;
    if (f.default_today) input.value = localDateIso();

    wrap.appendChild(label);
    wrap.appendChild(inputHolder);

    if (f.input_type === 'select' && f.allow_custom) {
      const custom = document.createElement('input');
      custom.type = 'text';
      custom.className = 'custom-input';
      custom.dataset.customKey = f.key;
      custom.placeholder = '请输入自定义' + f.label;
      custom.hidden = input.value !== '手动输入';
      input.addEventListener('change', () => syncCustomSelect(input, custom));
      wrap.appendChild(custom);
    }
    target.appendChild(wrap);
  });
}

function setFieldValue(key, value) {
  const input = document.querySelector('[data-key="' + key + '"]');
  if (!input || !value) return;
  const custom = document.querySelector('[data-custom-key="' + key + '"]');
  if (input.value.trim() !== '' &&
      !(input.tagName === 'SELECT' && custom &&
        input.value === '手动输入' && !custom.value.trim())) return;
  if (input.tagName === 'SELECT' && custom) {
    const known = Array.from(input.options).some(option => option.value === String(value));
    if (known) {
      input.value = String(value);
      syncCustomSelect(input, custom);
    } else {
      input.value = '手动输入';
      custom.value = String(value);
      syncCustomSelect(input, custom);
    }
  } else {
    input.value = value;
    const picker = input.parentElement && input.parentElement.querySelector('.date-picker-native');
    if (picker) picker.value = datePickerValue(value);
  }
  input.classList.add('auto-filled');
  setTimeout(() => input.classList.remove('auto-filled'), 2500);
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
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (e) { /* 忽略 */ }
  document.body.removeChild(ta);
  if (copied) done();
  else toast('复制失败，请手动选择文字复制', true);
}

/* ---------- 附件上传 ---------- */
function setupAttachmentUpload() {
  const input = $('attach-input');
  const dropzone = $('attach-dropzone');
  $('btn-pick-attach').addEventListener('click', () => input.click());
  const uploadFiles = async (files) => {
    for (const file of Array.from(files || [])) {
      await uploadAttachment(file);
    }
    input.value = '';
  };
  input.addEventListener('change', () => uploadFiles(input.files));
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    uploadFiles(e.dataTransfer.files);
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
  $('btn-choose-output').addEventListener('click', async () => {
    try {
      const data = await fetchJson('/api/select_output_dir');
      if (data.path) {
        selectedOutputDir = data.path;
        $('output-dir').value = data.path;
        toast('输出目录已选择');
      }
    } catch (e) {
      toast('选择输出目录失败：' + e.message, true);
    }
  });
  $('btn-generate').addEventListener('click', generate);
  $('btn-open-folder').addEventListener('click', async () => {
    try { await fetchJson('/api/open_output_folder'); } catch (e) { /* 忽略 */ }
  });
}

async function generate() {
  const fields = {};
  document.querySelectorAll('[data-key]').forEach(i => {
    fields[i.dataset.key] = i.value.trim();
  });
  document.querySelectorAll('[data-custom-key]').forEach(i => {
    if (!i.hidden) fields[i.dataset.customKey] = i.value.trim();
  });

  const payload = {
    fields: fields,
    image_name: currentImage ? currentImage.name : null,
    attachments: attachments,   // [{name, original}]
    output_dir: selectedOutputDir || null,
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
    renderOutputs(data.outputs, data.att_notes, data.output_folder);
    toast('生成成功！');
  } catch (e) {
    toast('生成失败：' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚙ 生成 Word / Excel 文件';
  }
}

function renderOutputs(outputs, attNotes, outputFolder) {
  const box = $('outputs');
  box.innerHTML = '';
  (outputs || []).forEach(o => {
    const div = document.createElement('div');
    div.className = 'out-item';

    const type = document.createElement('span');
    type.className = 'out-type ' + o.type;
    type.textContent = o.type === 'word' ? 'Word' : 'Excel';

    const link = document.createElement('a');
    link.href = o.url || ('/output/' + o.name);
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
  if (outputFolder) {
    const folder = document.createElement('div');
    folder.className = 'out-folder';
    folder.textContent = '已创建文件夹：' + outputFolder;
    box.appendChild(folder);
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
