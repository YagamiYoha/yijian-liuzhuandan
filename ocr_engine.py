# -*- coding: utf-8 -*-
"""
离线 OCR 引擎封装。

使用 RapidOCR（PaddleOCR 模型的 ONNX 精简版），基于 onnxruntime 纯 CPU 运行，
模型文件随程序打包，完全不依赖网络。首次调用时才加载模型，加快程序启动速度。
"""

import os
import re
import threading
import importlib.util
import datetime


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
                # 这里只检查模块是否存在，不实际导入 cv2/numpy/onnxruntime。
                # 这样桌面窗口初始化时不会与 OCR 原生 DLL 加载发生竞争。
                self._available = importlib.util.find_spec(
                    "rapidocr_onnxruntime") is not None
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
    def _extract_manager_contacts(ocr_items):
        """按铭牌上的角色标签提取项目经理、负责人及其联系方式。"""
        texts = [str(item.get("text", "") or "") for item in ocr_items]
        compact = [re.sub(r"\s+", "", text) for text in texts]
        phone_pattern = re.compile(
            r"(?<!\d)(?:1\d{10}|0\d{2,3}[-－]?\d{7,8})(?!\d)")
        role_defs = [
            ("manager", ("项目经理", "项目负责人")),
            ("responsible", ("现场负责人", "施工负责人", "负责人")),
        ]
        invalid_name_words = {
            "姓名", "名称", "手机", "电话", "联系电话", "联系方式", "联系人",
            "项目经理", "项目负责人", "负责人", "现场负责人", "施工负责人",
            "文明施工专管员", "文明施工", "专管员", "建设单位", "施工单位", "监理单位", "设计单位",
            "工程名称", "建设地址", "工程类别", "开工日期", "竣工日期",
        }

        def role_match(index):
            text = compact[index]
            for role, labels in role_defs:
                for label in labels:
                    pos = text.find(label)
                    if pos >= 0:
                        return role, label, pos, index + 1
            # 有些铭牌会把“项目经理/负责人”拆成两个 OCR 框，例如“项目”+“经理”。
            # 将相邻的最多三个框拼接后再判别，但不把远处的普通文字串起来。
            for span in (2, 3):
                joined = "".join(compact[index:index + span])
                for role, labels in role_defs:
                    for label in labels:
                        pos = joined.find(label)
                        if pos >= 0 and pos < len(compact[index]):
                            return role, label, pos, index + span
            return None

        def clean_name(text):
            text = re.sub(r"(?:电话|手机|联系方式|联系人)", "", text)
            text = re.sub(r"^(?:姓名|名称)", "", text)
            return text.strip(" \t：:，,；;|/\\-()（）")

        def valid_name(text):
            """只接受看起来像姓名的内容，拒绝铭牌中的字段表头。"""
            value = clean_name(text)
            if not value or value in invalid_name_words:
                return ""
            if any(word in value for word in invalid_name_words):
                return ""
            if any(word in value for word in ("日期", "单位", "地址", "工程", "类别")):
                return ""
            if not re.search(r"[\u4e00-\u9fffA-Za-z]", value):
                return ""
            return value

        records = []
        for index, text in enumerate(compact):
            match = role_match(index)
            if not match:
                continue
            role, label, pos, value_start = match
            # 标签完整位于当前 OCR 框时可直接取同行后缀；标签跨框时从下一个框开始取值。
            suffix = text[pos + len(label):] if value_start == index + 1 else ""
            phone_match = phone_pattern.search(suffix)
            phone = phone_match.group(0) if phone_match else ""
            name = valid_name(
                suffix[:phone_match.start()] if phone_match else suffix)
            record = {"role": role, "index": index,
                      "name": name, "phone": phone}
            phone_label_seen = bool(re.search(r"(?:电话|手机|联系方式|联系人)", suffix))

            # 铭牌常把标签、姓名、电话拆成相邻几行，按 OCR 顺序补齐。
            for next_index in range(value_start, min(value_start + 11, len(compact))):
                if role_match(next_index):
                    break
                candidate = compact[next_index]
                if not candidate:
                    continue
                phone_match = phone_pattern.search(candidate)
                if re.search(r"(?:电话|手机|联系方式|联系人)", candidate):
                    phone_label_seen = True
                if phone_match and phone_label_seen and not record["phone"]:
                    record["phone"] = phone_match.group(0)
                candidate_name = valid_name(
                    candidate[:phone_match.start()] if phone_match else candidate)
                if (not record["name"] and candidate_name and
                        not any(word in candidate for word in ("电话", "手机", "联系方式"))):
                    record["name"] = candidate_name
                if record["name"] and record["phone"]:
                    break
            records.append(record)

        return records

    @staticmethod
    def _normalize_date(text):
        """从 OCR 文本中提取并校验日期，返回统一的 YYYY-MM-DD。"""
        match = re.search(
            r"(?<!\d)(20\d{2})\s*(?:年|[./-])\s*"
            r"(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})\s*日?",
            str(text or ""),
        )
        if not match:
            return ""
        try:
            value = datetime.date(
                int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return ""
        return value.isoformat()

    @staticmethod
    def _extract_labeled_dates(ocr_items, fields):
        """只从开工/竣工标签附近的明确日期文本中提取日期。"""
        texts = [str(item.get("text", "") or "") for item in ocr_items]
        compact = [re.sub(r"\s+", "", text) for text in texts]
        boxes = [item.get("box") or [] for item in ocr_items]
        date_fields = [
            field for field in fields
            if field.get("key") in ("start_date", "end_date")
        ]
        date_candidates = []
        for index, text in enumerate(texts):
            normalized = OcrEngine._normalize_date(text)
            if normalized:
                date_candidates.append((index, normalized))

        def candidate_score(label_index, candidate_index):
            """分数越小越近；优先同一行右侧，其次正下方，再按 OCR 顺序。"""
            label_box = boxes[label_index]
            value_box = boxes[candidate_index]
            if label_box and value_box:
                lx1, lx2, ly1, ly2 = OcrEngine._metrics(label_box)
                x1, x2, y1, y2 = OcrEngine._metrics(value_box)
                overlap = min(ly2, y2) - max(ly1, y1)
                if overlap > 0 and x1 >= lx2 - 2:
                    return (0, max(0, x1 - lx2))
                if y1 >= ly2 - 2:
                    return (1, max(0, y1 - ly2))
            return (2, abs(candidate_index - label_index))

        extracted = {}
        used_candidates = set()
        for field in date_fields:
            key = field.get("key")
            keywords = [word for word in field.get("keywords", []) if word]
            best = None
            for label_index, text in enumerate(compact):
                for keyword in keywords:
                    position = text.find(keyword)
                    if position < 0:
                        continue
                    # 先处理“开工日期：2024-01-01”这种同行写法。
                    same_line = OcrEngine._normalize_date(
                        text[position + len(keyword):])
                    if same_line:
                        best = ((0, 0), label_index, same_line)
                        break

                    for candidate_index, normalized in date_candidates:
                        if candidate_index in used_candidates or candidate_index < label_index:
                            continue
                        # 日期值只在标签后面很近的 OCR 范围内考虑，避免串到别的区域。
                        if candidate_index > label_index + 6:
                            continue
                        score = candidate_score(label_index, candidate_index)
                        item = (score, candidate_index, normalized)
                        if best is None or item < best:
                            best = item
                if best and best[0][0] == 0:
                    break
            if best:
                extracted[key] = best[2]
                used_candidates.add(best[1])
        return extracted

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
        role_keys = {"manager", "manager_phone", "manager2", "manager2_phone"}
        for field in fields:
            key = field.get("key")
            if not key:
                continue
            # 手动字段不能被 OCR 覆盖；角色和日期使用下面的专用、证据约束提取。
            if field.get("source") == "manual" or key in role_keys:
                continue
            if key in {"start_date", "end_date"}:
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

        # 日期只接受明确的日期格式；没有识别到日期时不返回该字段，前端会保持空白。
        extracted.update(OcrEngine._extract_labeled_dates(ocr_items, fields))

        # 角色字段单独按「项目经理/负责人」标签分流，避免通用关键词把两者混为一人。
        role_records = OcrEngine._extract_manager_contacts(ocr_items)
        manager = next((r for r in role_records if r["role"] == "manager" and r["name"]), None)
        responsible = next((r for r in role_records if r["role"] == "responsible" and r["name"]), None)
        if manager:
            extracted["manager"] = manager["name"]
            extracted["manager_phone"] = manager["phone"]
            extracted["manager2"] = responsible["name"] if responsible else ""
            extracted["manager2_phone"] = responsible["phone"] if responsible else ""
        elif responsible:
            # 没有项目经理时，把负责人及电话作为项目经理填入；第二项目经理留空。
            extracted["manager"] = responsible["name"]
            extracted["manager_phone"] = responsible["phone"]
            extracted["manager2"] = ""
            extracted["manager2_phone"] = ""
        else:
            # 没有可靠角色证据时，明确清空四个字段，避免残留通用关键词误判。
            extracted["manager"] = ""
            extracted["manager_phone"] = ""
            extracted["manager2"] = ""
            extracted["manager2_phone"] = ""

        return extracted


# 全局单例，供 app.py 复用（模型只加载一次）
ocr_engine = OcrEngine()
