# -*- coding: utf-8 -*-
"""
离线 OCR 引擎封装。

使用 RapidOCR（PaddleOCR 模型的 ONNX 精简版），基于 onnxruntime 纯 CPU 运行，
模型文件随程序打包，完全不依赖网络。首次调用时才加载模型，加快程序启动速度。
"""

import os
import threading


class OcrEngine:
    """RapidOCR 封装：惰性加载 + 结果结构化 + 关键词自动提取字段。"""

    def __init__(self):
        self._engine = None
        self._available = None  # None=未检测, True/False
        self._lock = threading.Lock()

    # ---------- 可用性检测 ----------
    def is_available(self):
        """检测 rapidocr 是否可用（打包后模型未丢失则应返回 True）。"""
        if self._available is None:
            try:
                import rapidocr_onnxruntime  # noqa: F401
                self._available = True
            except Exception:
                self._available = False
        return self._available

    # ---------- 模型加载 ----------
    def _load(self):
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
        return self._engine

    # ---------- 识别 ----------
    def recognize(self, image_path):
        """
        识别图片文字。

        参数:
            image_path: 图片文件路径（支持 jpg/png/bmp 等常见格式）

        返回:
            [ {"text": str, "score": float, "box": [[x,y],...]}, ... ]
        """
        if not os.path.isfile(image_path):
            raise FileNotFoundError("图片不存在: %s" % image_path)

        engine = self._load()
        result, _ = engine(image_path)

        items = []
        if result:
            for box, text, score in result:
                # 过滤置信度过低的噪声结果
                if float(score) < 0.5:
                    continue
                box_list = []
                if box is not None:
                    for p in box:
                        box_list.append([int(p[0]), int(p[1])])
                items.append({
                    "text": (text or "").strip(),
                    "score": round(float(score), 4),
                    "box": box_list,
                })
        return items

    # ---------- 关键词自动提取 ----------
    @staticmethod
    def _label_score(kw, text):
        """
        关键词匹配评分：
          2 = 标签位精确匹配（关键词在行首，或前面是空白/冒号/竖线等分隔）
          1 = 关键词出现在行中（可能只是值里恰好包含）
          0 = 不匹配
        """
        if kw not in text:
            return 0
        pos = text.index(kw)
        if pos == 0:
            return 2
        prev = text[pos - 1]
        if prev in " \t：:，,；;|":
            return 2
        return 1

    @staticmethod
    def _cut_value(seg, label_words):
        """把值里可能混入的后续标签切掉，如「李志强 手机：1550…」→「李志强」。"""
        seg = seg.lstrip("：: \t")
        cut = len(seg)
        # 去掉值中间出现的下一个标签词（前面已有内容才算）
        for lw in label_words:
            p = seg.find(lw)
            if p > 0 and p < cut:
                cut = p
        return seg[:cut].strip()

    @staticmethod
    def _metrics(box):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        return min(xs), max(xs), min(ys), max(ys)

    @staticmethod
    def auto_extract(ocr_items, fields):
        """
        根据字段配置里的关键词，从 OCR 结果中自动提取字段值。

        支持：
          - 同行文本提取：「工程名称：某某工程」→「某某工程」
          - 表格型铭牌：标签与值分行，用【坐标几何】定位值
            （优先同行右侧最近，否则正下方最近；噪声行因位置不同被自然排除）
          - 标签位精确匹配优先（避免「联系电话」干扰「电话」）
          - 同一关键词被多个字段用时自动错开（如两个「手机」）
          - requires_digit 字段要求值里含数字（电话/手机）

        返回: {"key": "value", ...}
        """
        texts = [it.get("text", "") for it in ocr_items]
        boxes = [it.get("box") or [] for it in ocr_items]

        # 所有标签词集合（用于截断值里的后续标签、过滤标签行）
        label_words = set()
        for f in fields:
            for kw in f.get("keywords", []):
                if kw:
                    label_words.add(kw)

        # 同一关键词已被哪些行消费（避免两个字段取到同一行）
        used = {}  # kw -> set(行号)

        def valid_value(t, need_digit):
            v = OcrEngine._cut_value(t, label_words)
            if not v:
                return None
            if need_digit and not any(ch.isdigit() for ch in v):
                return None
            return v

        def locate_value(i, kw, need_digit):
            """在第 i 行找到 kw 的值：同行文本 → 同行右侧最近 → 正下方最近。"""
            text = texts[i]
            idx = text.index(kw) + len(kw)
            seg = text[idx:]
            if seg.strip():
                v = valid_value(seg, need_digit)
                if v:
                    return i, v

            lb = boxes[i]
            if lb:
                lx1, lx2, ly1, ly2 = OcrEngine._metrics(lb)
                # 1) 同行右侧：先过滤（y 重叠比例≥55%），再取水平间距最小者
                best = None  # (gap, j, v)
                for j, b in enumerate(boxes):
                    if j == i or not b:
                        continue
                    if j in used.get(kw, set()):
                        continue
                    t = texts[j].strip()
                    if not t or any(k in t for k in label_words):
                        continue
                    x1, x2, y1, y2 = OcrEngine._metrics(b)
                    if x1 < lx2 - 2:
                        continue  # 不在右侧
                    if y2 < ly1 or y1 > ly2:
                        continue  # 行不重叠
                    overlap = min(y2, ly2) - max(y1, ly1)
                    if overlap <= 0:
                        continue
                    ratio = overlap / max(1, min(ly2 - ly1, y2 - y1))
                    if ratio < 0.55:
                        continue
                    v = valid_value(t, need_digit)
                    if not v:
                        continue
                    gap = x1 - lx2
                    if best is None or gap < best[0]:
                        best = (gap, j, v)
                if best:
                    return best[1], best[2]
                # 2) 正下方最近（值换行/在下一行）
                best = None
                for j, b in enumerate(boxes):
                    if j == i or not b:
                        continue
                    if j in used.get(kw, set()):
                        continue
                    t = texts[j].strip()
                    if not t or any(k in t for k in label_words):
                        continue
                    x1, x2, y1, y2 = OcrEngine._metrics(b)
                    if y1 < ly2 - 2:
                        continue  # 不在标签下方
                    v = valid_value(t, need_digit)
                    if not v:
                        continue
                    ygap = y1 - ly2
                    if best is None or ygap < best[0]:
                        best = (ygap, j, v)
                if best:
                    return best[1], best[2]

            # 3) 最后兜底：按 OCR 顺序向后找 3 行
            for j in range(i + 1, min(i + 4, len(texts))):
                nxt = texts[j].strip()
                if not nxt or any(k in nxt for k in label_words):
                    continue
                v = valid_value(nxt, need_digit)
                if v:
                    return j, v
            return None, None

        extracted = {}
        for field in fields:
            key = field.get("key")
            if not key:
                continue
            kws = [k for k in field.get("keywords", []) if k]
            need_digit = field.get("requires_digit", False)
            chosen = None

            # 两轮扫描：先精确标签位（score 2），再普通匹配（score 1）
            # 关键词在外层：优先按关键词顺序扫描（避免噪声行里的长标签抢先命中）
            for target_score in (2, 1):
                if chosen:
                    break
                for kw in kws:
                    if chosen:
                        break
                    for i, text in enumerate(texts):
                        if OcrEngine._label_score(kw, text) < target_score:
                            continue
                        if i in used.get(kw, set()):
                            continue
                        j, value = locate_value(i, kw, need_digit)
                        if value:
                            chosen = (kw, i, j, value)
                            break

            if chosen:
                kw, i, j, value = chosen
                extracted[key] = value
                used.setdefault(kw, set()).update([i, j])

        return extracted


# 全局单例，供 app.py 复用（模型只加载一次）
ocr_engine = OcrEngine()
