# -*- coding: utf-8 -*-
"""
后端服务：提供 OCR 识别、附件上传、模板填充、文件下载等接口。

本文件既可以被 main.py 引入（桌面窗口模式），也可以单独运行进行调试：
    python app.py --web     （用浏览器打开界面，便于开发调试）
"""

import datetime
import json
import os
import sys
import time
import traceback
import uuid

from flask import Flask, jsonify, request, send_from_directory

from ocr_engine import ocr_engine
from template_filler import TemplateFiller


# ============================================================
# 路径工具（兼容打包成 exe 后的路径）
# ============================================================
def is_frozen():
    return getattr(sys, "frozen", False)


def base_dir():
    """exe 同目录（存放 config.json、templates、uploads、output）。"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """打包后的内置资源目录（static 前端文件等）。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", base_dir())
    return base_dir()


BASE = base_dir()
STATIC_DIR = os.path.join(resource_dir(), "static")
CONFIG_PATH = os.path.join(BASE, "config.json")
UPLOAD_DIR = os.path.join(BASE, "uploads")
ATTACH_DIR = os.path.join(BASE, "uploads", "attachments")
OUTPUT_DIR = os.path.join(BASE, "output")
TEMPLATE_DIR = os.path.join(BASE, "templates")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}

for _d in (UPLOAD_DIR, ATTACH_DIR, OUTPUT_DIR, TEMPLATE_DIR):
    os.makedirs(_d, exist_ok=True)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def log_error(context, exc):
    """把接口层异常写入 exe 旁边的 崩溃日志.log，便于打包后排查。"""
    try:
        with open(os.path.join(BASE, "崩溃日志.log"), "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), context))
            f.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
            f.write("\n")
    except Exception:
        pass


def create_app():
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 单次上传上限 200MB
    cfg = load_config()

    # ---------- 页面 ----------
    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    # ---------- 配置 ----------
    @app.route("/api/config")
    def api_config():
        return jsonify({
            "title": cfg["app"].get("title", "一键流转单生成工具"),
            "fields": cfg.get("fields", []),
            "images": cfg.get("images", []),
            "attachments": cfg.get("attachments", []),
            "word_enabled": cfg.get("word", {}).get("enabled", True),
            "excel_enabled": cfg.get("excel", {}).get("enabled", False),
            "ocr_available": ocr_engine.is_available(),
        })

    # ---------- OCR 识别 ----------
    @app.route("/api/ocr", methods=["POST"])
    def api_ocr():
        if "image" not in request.files:
            return jsonify({"ok": False, "error": "未收到图片文件"}), 400

        file = request.files["image"]
        ext = os.path.splitext(file.filename)[1].lower() or ".png"
        name = "img_" + uuid.uuid4().hex[:10] + ext
        path = os.path.join(UPLOAD_DIR, name)
        file.save(path)

        try:
            items = ocr_engine.recognize(path)
            extracted = ocr_engine.auto_extract(items, cfg.get("fields", []))
        except Exception as e:
            log_error("OCR 识别异常", e)
            return jsonify({"ok": False, "error": "OCR 识别失败：%s" % e,
                            "image": name}), 500

        return jsonify({
            "ok": True,
            "image": name,
            "texts": [it["text"] for it in items],
            "items": items,
            "extracted": extracted,
        })

    # ---------- 附件上传 ----------
    @app.route("/api/upload_attachment", methods=["POST"])
    def api_upload_attachment():
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "未收到文件"}), 400
        file = request.files["file"]
        ext = os.path.splitext(file.filename)[1]
        name = "att_" + uuid.uuid4().hex[:10] + ext
        path = os.path.join(ATTACH_DIR, name)
        file.save(path)
        return jsonify({"ok": True, "filename": name,
                        "original": file.filename})

    # ---------- 生成文件 ----------
    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        data = request.get_json(force=True)
        fields = data.get("fields", {})
        image_name = data.get("image_name")  # 铭牌图片文件名（uploads 下）
        attachments = data.get("attachments", [])  # [{"name","original"}, ...]

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        outputs = []
        att_notes = []

        # 文本映射：所有字段 -> {{key}}
        text_map = {}
        for f in cfg.get("fields", []):
            key = f.get("key")
            text_map[key] = fields.get(key, "")

        # 图片映射：铭牌图片 -> 各图片占位符
        image_map = {}
        if image_name:
            image_path = os.path.join(UPLOAD_DIR, image_name)
            if os.path.isfile(image_path):
                for img_cfg in cfg.get("images", []):
                    image_map[img_cfg["placeholder"]] = [
                        (image_path, img_cfg.get("width_cm", 8.0))]

        # 附件分类：图片类直接插入 Word，其它类型记录文件名
        att_imgs = []
        for a in attachments:
            if isinstance(a, dict):
                fn, orig = a.get("name", ""), a.get("original", "")
            else:
                fn, orig = a, a
            p = os.path.join(ATTACH_DIR, fn)
            if os.path.isfile(p):
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMAGE_EXTS:
                    att_imgs.append((p, 8.0))
                else:
                    att_notes.append(orig or fn)
        attachment_text = "、".join(att_notes) if att_notes else ""

        # 生成 Word
        if cfg.get("word", {}).get("enabled"):
            w_cfg = cfg["word"]
            template = os.path.join(BASE, w_cfg["template"])
            if not os.path.isfile(template):
                return jsonify({"ok": False,
                                "error": "Word 模板不存在：" + template}), 400
            out_name = "%s_%s.docx" % (w_cfg.get("output_prefix", "文档"), stamp)
            out_path = os.path.join(OUTPUT_DIR, out_name)
            TemplateFiller.fill_word(template, out_path, text_map,
                                     image_map, att_imgs, attachment_text)
            outputs.append({"type": "word", "name": out_name})

        # 生成 Excel
        if cfg.get("excel", {}).get("enabled"):
            e_cfg = cfg["excel"]
            template = os.path.join(BASE, e_cfg["template"])
            if not os.path.isfile(template):
                return jsonify({"ok": False,
                                "error": "Excel 模板不存在：" + template}), 400
            out_name = "%s_%s.xlsx" % (e_cfg.get("output_prefix", "表格"), stamp)
            out_path = os.path.join(OUTPUT_DIR, out_name)
            sheet = e_cfg.get("sheet_name") or None
            TemplateFiller.fill_excel(template, out_path, text_map, sheet)
            outputs.append({"type": "excel", "name": out_name})

        return jsonify({"ok": True, "outputs": outputs, "att_notes": att_notes})

    # ---------- 文件服务 ----------
    @app.route("/uploads/<path:filename>")
    def uploads(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    @app.route("/uploads/attachments/<path:filename>")
    def attachments_file(filename):
        return send_from_directory(ATTACH_DIR, filename)

    @app.route("/output/<path:filename>")
    def download_output(filename):
        return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

    # ---------- 打开输出目录 ----------
    @app.route("/api/open_output_folder")
    def open_output_folder():
        try:
            if os.name == "nt":
                os.startfile(OUTPUT_DIR)  # noqa
            else:
                import subprocess
                subprocess.Popen(["xdg-open", OUTPUT_DIR])
        except Exception:
            pass
        return jsonify({"ok": True})

    return app


def run_server(port):
    """在独立线程中启动 Flask（供 main.py 调用）。"""
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False,
            use_reloader=False, threaded=True)


if __name__ == "__main__":
    # 开发调试入口：python app.py --web 用浏览器打开
    import threading
    import time
    import socket
    import webbrowser

    cfg = load_config()
    port = cfg["app"].get("port", 8090)
    url = "http://127.0.0.1:%d/" % port

    server = threading.Thread(target=run_server, args=(port,), daemon=True)
    server.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
