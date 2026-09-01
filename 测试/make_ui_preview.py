# -*- coding: utf-8 -*-
"""生成界面预览 HTML（内联样式+示例数据，用于截图预览界面效果，不参与实际运行）。"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASE, "static")

with open(os.path.join(STATIC, "index.html"), "r", encoding="utf-8") as f:
    html = f.read()
with open(os.path.join(STATIC, "style.css"), "r", encoding="utf-8") as f:
    css = f.read()

# 1) 内联 CSS
html = html.replace(
    '<link rel="stylesheet" href="/static/style.css">',
    "<style>\n" + css + "\n</style>",
)

# 2) 示例表单字段（与 config.json 一致，用真实铭牌照片提取结果展示自动填充效果）
sample_fields = [
    ("project_name", "工程名称", "宝山区规划N12-0402单元M2-01A地块项目", True),
    ("address", "建设地址", "宝山区淞南镇东至M2-01B地块，南至一二八纪念路，西至淞南路，北至长逸路", True),
    ("owner", "建设单位", "上海汇络文化科技有限公司", True),
    ("builder", "施工单位", "上海普宏建设工程有限公司", True),
    ("supervisor", "监理单位", "上海市工程建设咨询监理有限公司", True),
    ("designer", "设计单位", "上海经安建筑设计院有限公司", True),
    ("category", "工程类别", "框架结构", True),
    ("area", "建筑面积", "10510平方米", True),
    ("start_date", "开工日期", "2026年6月30日", True),
    ("end_date", "竣工日期", "2027年6月30日", True),
    ("manager", "项目经理", "李志强", True),
    ("manager_phone", "项目经理手机", "15502188920", True),
    ("site_manager", "文明施工专管员", "俞光明", True),
    ("site_phone", "专管员手机", "18701805015", True),
    ("phone", "联系电话", "021-56174211", True),
    ("serial_no", "流转单编号", "", False),
    ("reason", "事由", "", False),
    ("handler", "经办人", "", False),
    ("department", "申请部门", "", False),
]
fields_html = ""
for key, label, value, auto in sample_fields:
    cls = ' class="auto-filled"' if auto else ""
    fields_html += (
        '<div class="field"><label for="f-%s">%s</label>'
        '<input type="text" id="f-%s" data-key="%s" placeholder="请输入%s" value="%s"%s></div>\n'
    ) % (key, label, key, key, label, value, cls)
html = html.replace('<form id="fields-form" class="fields-grid"></form>',
                    '<form id="fields-form" class="fields-grid">\n' + fields_html + "</form>")

# 3) 示例识别结果（真实铭牌 OCR 关键行）
ocr_lines = [
    "工程名称 宝山区规划N12-0402单元M2-01A地块项目",
    "建设地址 宝山区淞南镇东至M2-01B地块，南至一二八纪念路",
    "建设单位 上海汇络文化科技有限公司",
    "监理单位 上海市工程建设咨询监理有限公司",
    "总包单位 上海普宏建设工程有限公司",
    "工程类别 框架结构    建筑面积 10510平方米",
    "开工日期 2026年6月30日  竣工日期 2027年6月30日",
    "设计单位 上海经安建筑设计院有限公司",
    "项目经理 李志强    手机 15502188920",
    "文明施工专管员 俞光明  手机 18701805015",
    "电话 021-56174211",
]
ocr_html = ""
for i, t in enumerate(ocr_lines):
    score = [95, 91, 92, 90, 88, 94, 93, 89, 87, 86, 90][i]
    ocr_html += ('<div class="ocr-line" title="点击复制"><span class="txt">%s</span>'
                 '<span class="score">%d%%</span></div>\n') % (t, score)
html = html.replace(
    '<div class="empty-hint">识别出的文字会显示在这里，并按关键词自动填入右侧表单（可手动修改）</div>',
    ocr_html,
)

# 4) 示例图片预览（示意 SVG）
svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240">'
       '<rect width="400" height="240" fill="#dbeafe"/>'
       '<rect x="46" y="38" width="308" height="118" fill="#93c5fd" rx="6"/>'
       '<text x="200" y="102" font-size="22" text-anchor="middle" fill="#1e3a8a" '
       'font-family="Microsoft YaHei, sans-serif">工程铭牌照片</text>'
       '<text x="200" y="196" font-size="14" text-anchor="middle" fill="#475569" '
       'font-family="Microsoft YaHei, sans-serif">（示例图片）</text></svg>')
svg_uri = "data:image/svg+xml;charset=utf-8," + svg.replace("#", "%23").replace('"', "'")
html = html.replace('<div class="preview" id="image-preview" hidden>',
                    '<div class="preview" id="image-preview">')
html = html.replace('<img id="preview-img" alt="图片预览">',
                    '<img id="preview-img" alt="图片预览" src="%s">' % svg_uri)
html = html.replace('<div class="preview-meta" id="preview-meta"></div>',
                    '<div class="preview-meta" id="preview-meta">铭牌照片.jpg · 识别完成，共 8 行文字，自动填入 8 个字段</div>')
html = html.replace('<div class="ocr-status" id="ocr-status" hidden></div>',
                    '<div class="ocr-status" id="ocr-status">识别完成</div>')

# 5) 示例附件
html = html.replace('<ul class="attach-list" id="attach-list"></ul>',
                    '<ul class="attach-list" id="attach-list">'
                    '<li><span class="att-name">盖章扫描件.png</span>'
                    '<button type="button" class="att-remove">移除</button></li>'
                    '<li><span class="att-name">营业执照照片.jpg</span>'
                    '<button type="button" class="att-remove">移除</button></li></ul>')

# 6) 示例输出
html = html.replace('<div class="outputs" id="outputs"></div>',
                    '<div class="outputs" id="outputs">'
                    '<div class="out-item"><span class="out-type word">Word</span>'
                    '<a href="#">⬇ 下载 流转单_20260831_183155.docx</a></div>'
                    '<div class="out-item"><span class="out-type excel">Excel</span>'
                    '<a href="#">⬇ 下载 台账_20260831_183155.xlsx</a></div></div>')
html = html.replace('<button class="btn btn-link" id="btn-open-folder" type="button" hidden>📂 打开输出文件夹</button>',
                    '<button class="btn btn-link" id="btn-open-folder" type="button">📂 打开输出文件夹</button>')

# 7) 去掉 JS（截图预览不需要）
html = html.replace('<script src="/static/app.js"></script>', "")

out = os.path.join(BASE, "测试", "ui_preview.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("已生成界面预览：", out)
