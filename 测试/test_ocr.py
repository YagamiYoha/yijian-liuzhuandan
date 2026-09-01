# -*- coding: utf-8 -*-
"""
真实 OCR 冒烟测试（需要已安装 rapidocr_onnxruntime + onnxruntime + pillow）：
  1. 用 Pillow 生成测试图片；
  2. 调用 ocr_engine 真实识别；
  3. 验证关键词自动提取字段逻辑。

运行：python 测试/test_ocr.py
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from PIL import Image, ImageDraw, ImageFont

from ocr_engine import ocr_engine

# 尝试找中文字体（各系统常见路径）
CJK_FONT_CANDIDATES = [
    os.path.join(BASE, "测试", "NotoSansCJKsc-Regular.otf"),  # 测试目录里的字体
    "C:/Windows/Fonts/simhei.ttf",          # Windows 黑体
    "C:/Windows/Fonts/msyh.ttc",            # Windows 微软雅黑
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]


def find_font():
    for p in CJK_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def make_test_image(path, lines, font_path=None, size=30):
    img = Image.new("RGB", (900, 40 + len(lines) * 52), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    y = 20
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 52
    img.save(path)


if __name__ == "__main__":
    font = find_font()
    lines = [
        "工程名称：某某市某某道路改造工程",
        "施工单位：某某建设集团有限公司",
        "联系电话：13800000000",
        "Project: Test Road Project",
        "日期：2025年9月1日",
    ]
    if not font:
        print("未找到中文字体，改用英文测试图")
        lines = [
            "Project Name: Test Road Project",
            "Builder: Test Construction Group",
            "Phone: 138-0000-0000",
            "Date: 2025-09-01",
        ]

    img_path = os.path.join(BASE, "测试", "_ocr_test.png")
    make_test_image(img_path, lines, font)
    print("测试图片已生成：", img_path)

    print("开始离线 OCR 识别（首次需加载模型，约 10~30 秒）...")
    items = ocr_engine.recognize(img_path)
    for it in items:
        print("  [%3.0f%%] %s" % (it["score"] * 100, it["text"]))
    print("共识别 %d 行" % len(items))
    assert len(items) >= 4, "识别行数异常"

    # 验证关键词自动提取
    fields = [
        {"key": "project_name", "keywords": ["工程名称", "Project Name"]},
        {"key": "builder", "keywords": ["施工单位", "Builder"]},
        {"key": "phone", "keywords": ["电话", "Phone", "联系电话"]},
        {"key": "date", "keywords": ["日期", "Date"]},
    ]
    extracted = ocr_engine.auto_extract(items, fields)
    print("自动提取结果：", extracted)
    assert extracted.get("phone"), "电话字段未提取到"
    print("OCR 冒烟测试通过 ✓")
