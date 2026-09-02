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
    def _right_row_score(label_box, value_box):
        """判断值是否位于标签右侧的同一行（兼容拍摄倾斜的铭牌）。

        施工铭牌经常是从屏幕或斜着拍摄的，标签和值的矩形框在原图中
        可能完全没有 y 轴重叠。仅按 y 重叠判断，会把下一行或旁边的
        内容误当成当前字段。这里额外用两框中心点的倾斜斜率判断行关系。
        返回值可直接用于排序，数值越小越优先。
        """
        if not label_box or not value_box:
            return None
        lx1, lx2, ly1, ly2 = OcrEngine._metrics(label_box)
        x1, x2, y1, y2 = OcrEngine._metrics(value_box)
        if x1 < lx2 - 2:
            return None

        gap = max(0, x1 - lx2)
        overlap = min(ly2, y2) - max(ly1, y1)
        center_dy = ((y1 + y2) - (ly1 + ly2)) / 2.0
        label_height = max(1, ly2 - ly1)
        value_height = max(1, y2 - y1)
        overlap_ratio = overlap / max(1, min(label_height, value_height))
        # 这批铭牌的行会向右上方倾斜；即使两个框有重叠，值位于
        # 标签右下方通常也意味着它属于下一行或旁边的内容。
        if overlap > 0 and overlap_ratio >= 0.55 and center_dy <= 5:
            return (0, gap, abs(center_dy))

        lx = (lx1 + lx2) / 2.0
        ly = (ly1 + ly2) / 2.0
        vx = (x1 + x2) / 2.0
        vy = (y1 + y2) / 2.0
        dx = vx - lx
        if dx <= 1:
            return None

        # 透视/斜拍时，右侧文字通常位于标签的左上方。
        slope = (ly - vy) / dx
        dy = vy - ly
        if not (0.01 <= slope <= 0.35 and -145 <= dy <= 25):
            return None
        # 先按水平距离找相邻值，再用垂直偏移和斜率作次级判断；
        # 过大的垂直偏移已在上面排除，避免上一行长文本抢值。
        return (1, gap, abs(dy), round(abs(slope - 0.10), 4))

    @staticmethod
    def _detect_primary_panel_right(ocr_items, fields=None):
        """检测主铭牌右边界，排除照片中相邻的另一块铭牌/告示栏。

        一张现场照片可能同时拍到两块铭牌。主铭牌通常能在“工程名称”
        标签右侧找到一段较长的值；如果该值右侧又出现多组字段标签，
        就将它们识别为旁边的面板。没有明显旁板时返回 None，不限制范围。
        """
        fields = fields or []
        texts = [re.sub(r"\s+", "", str(item.get("text", "") or ""))
                 for item in ocr_items]
        boxes = [item.get("box") or [] for item in ocr_items]
        label_words = set()
        for field in fields:
            for keyword in field.get("keywords", []) or []:
                if keyword:
                    label_words.add(re.sub(r"\s+", "", keyword))
        label_words.update({
            "工程名称", "项目名称", "建设单位", "施工单位", "总包单位",
            "施工总承包", "监理单位", "设计单位", "工程类别", "开工日期",
            "竣工日期", "项目经理", "负责人", "联系电话", "联系方式",
            "姓名", "电话", "手机", "告示栏",
        })

        anchors = []
        for i, text in enumerate(texts):
            if not boxes[i] or not any(
                    text.startswith(keyword) or text == keyword
                    for keyword in ("工程名称", "项目名称")):
                continue
            lx1, lx2, ly1, ly2 = OcrEngine._metrics(boxes[i])
            for j, value_text in enumerate(texts):
                if i == j or not boxes[j] or not value_text:
                    continue
                x1, x2, y1, y2 = OcrEngine._metrics(boxes[j])
                if x1 < lx2 - 2 or any(word in value_text for word in label_words):
                    continue
                overlap = min(ly2, y2) - max(ly1, y1)
                ratio = overlap / max(1, min(ly2 - ly1, y2 - y1))
                if overlap <= 0 or ratio < 0.35:
                    continue
                anchors.append((len(value_text), i, j, x2))

        if not anchors:
            return None
        _, label_index, value_index, main_right = max(
            anchors, key=lambda item: (item[0], -item[3]))
        del label_index, value_index

        known_side_labels = {
            "工程名称", "建设单位", "施工总承包", "施工单位", "监理单位",
            "设计单位", "工程类别", "开工日期", "竣工日期", "项目经理",
            "负责人", "联系电话", "联系方式", "总包企业", "总包单位",
        }
        side_items = []
        for i, text in enumerate(texts):
            if not boxes[i] or not text:
                continue
            x1, _, _, _ = OcrEngine._metrics(boxes[i])
            if x1 <= main_right + 120:
                continue
            if any(label in text for label in known_side_labels):
                side_items.append((x1, i))

        # 至少两组标签才认为是旁板，避免误切掉主铭牌右侧的普通文字。
        if len(side_items) < 2:
            return None
        return min(x1 for x1, _ in side_items) - 20

    @staticmethod
    def _extract_manager_contacts(ocr_items):
        """按铭牌上的角色标签提取项目经理、负责人及其联系方式。

        这里不能只按 OCR 返回顺序向后取值：斜拍铭牌会让右侧的“姓名/电话”
        在 OCR 列表中出现在角色标签之前，照片中还有相邻告示栏时也会把
        旁栏的“项目经理”误识别进来。因此先限制到主铭牌，再用坐标关系
        找“姓名”和“电话”对应的值。
        """
        texts = [str(item.get("text", "") or "") for item in ocr_items]
        compact = [re.sub(r"\s+", "", text) for text in texts]
        boxes = [item.get("box") or [] for item in ocr_items]
        panel_right = OcrEngine._detect_primary_panel_right(ocr_items)

        def in_primary_panel(index):
            if panel_right is None or not boxes[index]:
                return True
            return OcrEngine._metrics(boxes[index])[0] < panel_right

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

        role_anchors = []

        def add_anchor(role, label, index, pos=0, indices=None):
            """添加角色标签，并合并同一位置的重复/拆分 OCR 框。"""
            indices = list(indices or [index])
            valid_indices = [i for i in indices if 0 <= i < len(texts)]
            anchor_boxes = [boxes[i] for i in valid_indices if boxes[i]]
            if anchor_boxes:
                x_values = [OcrEngine._metrics(b)[0] for b in anchor_boxes]
                x2_values = [OcrEngine._metrics(b)[1] for b in anchor_boxes]
                y_values = [OcrEngine._metrics(b)[2] for b in anchor_boxes]
                y2_values = [OcrEngine._metrics(b)[3] for b in anchor_boxes]
                cx = (min(x_values) + max(x2_values)) / 2.0
                cy = (min(y_values) + max(y2_values)) / 2.0
            else:
                cx = cy = None
            for existing in role_anchors:
                if existing["role"] != role:
                    continue
                if cx is None or existing["cx"] is None:
                    if existing["index"] == index:
                        return
                elif abs(existing["cx"] - cx) < 180 and abs(existing["cy"] - cy) < 180:
                    return
            role_anchors.append({
                "role": role,
                "label": label,
                "index": index,
                "pos": pos,
                "indices": valid_indices,
                "cx": cx,
                "cy": cy,
            })

        # 1) 直接识别到完整标签的角色框。
        for index, text in enumerate(compact):
            if not in_primary_panel(index):
                continue
            for role, labels in role_defs:
                found = False
                for label in labels:
                    pos = text.find(label)
                    if pos >= 0:
                        add_anchor(role, label, index, pos)
                        found = True
                        break
                if found:
                    break

        # 2) “项目”+“经理”可能被 OCR 拆成两个框，中间还可能夹着旁栏文字。
        #    通过框的实际位置配对，而不是要求它们在 OCR 列表中相邻。
        for i, text in enumerate(compact):
            if not in_primary_panel(i) or "项目" not in text:
                continue
            for j, other in enumerate(compact):
                if i == j or not in_primary_panel(j) or "经理" not in other:
                    continue
                if not boxes[i] or not boxes[j]:
                    continue
                ix1, ix2, iy1, iy2 = OcrEngine._metrics(boxes[i])
                jx1, jx2, jy1, jy2 = OcrEngine._metrics(boxes[j])
                icx, jcx = (ix1 + ix2) / 2.0, (jx1 + jx2) / 2.0
                icy, jcy = (iy1 + iy2) / 2.0, (jy1 + jy2) / 2.0
                if abs(icx - jcx) <= 220 and abs(icy - jcy) <= 220:
                    add_anchor("manager", "项目经理", i, 0, [i, j])
                    break

        def direct_values(anchor):
            """处理“项目经理：张三 138...”这种标签和值在同一框的情况。"""
            text = compact[anchor["index"]]
            suffix = text[anchor["pos"] + len(anchor["label"]):]
            phone_match = phone_pattern.search(suffix)
            phone = phone_match.group(0) if phone_match else ""
            name = valid_name(suffix[:phone_match.start()] if phone_match else suffix)
            return name, phone

        def spatial_name(anchor):
            """在角色标签右侧的姓名行中找姓名。"""
            if anchor["cx"] is None:
                return None
            anchor_right = max(
                (OcrEngine._metrics(boxes[i])[1]
                 for i in anchor["indices"] if boxes[i]),
                default=anchor["cx"],
            )
            best = None
            for label_index, label_text in enumerate(compact):
                if (not in_primary_panel(label_index) or "姓名" not in label_text or
                        not boxes[label_index]):
                    continue
                lx1, lx2, ly1, ly2 = OcrEngine._metrics(boxes[label_index])
                if lx1 < anchor_right - 20:
                    continue
                name_value = None
                for value_index, value_text in enumerate(compact):
                    if (value_index == label_index or not value_text or
                            not in_primary_panel(value_index) or not boxes[value_index]):
                        continue
                    if any(word in value_text for word in (
                            "姓名", "电话", "手机", "联系方式", "项目经理", "负责人")):
                        continue
                    relation = OcrEngine._right_row_score(
                        boxes[label_index], boxes[value_index])
                    if relation is None:
                        continue
                    candidate_name = valid_name(value_text)
                    if not candidate_name:
                        continue
                    if name_value is None or relation < name_value[0]:
                        name_value = (relation, value_index, candidate_name)
                if name_value is None:
                    continue
                label_center_y = (ly1 + ly2) / 2.0
                role_center_y = anchor["cy"]
                distance = abs(label_center_y - role_center_y)
                if distance > 500:
                    continue
                item = (distance, name_value[0], label_index,
                        name_value[1], name_value[2])
                if best is None or item < best:
                    best = item
            if best is None:
                return None
            return {
                "label_index": best[2],
                "value_index": best[3],
                "name": best[4],
            }

        def spatial_phone(anchor, name_info):
            """在姓名行下方找电话行，防止拿到监督单位的电话。"""
            if not name_info:
                return ""
            name_box = boxes[name_info["label_index"]]
            name_center_y = sum(OcrEngine._metrics(name_box)[2:4]) / 2.0
            anchor_right = max(
                (OcrEngine._metrics(boxes[i])[1]
                 for i in anchor["indices"] if boxes[i]),
                default=anchor["cx"] or 0,
            )
            best = None
            for label_index, label_text in enumerate(compact):
                if (not in_primary_panel(label_index) or not boxes[label_index] or
                        not re.search(r"(?:电话|手机|联系方式)", label_text)):
                    continue
                lx1, lx2, ly1, ly2 = OcrEngine._metrics(boxes[label_index])
                if lx1 < anchor_right - 20:
                    continue
                label_center_y = (ly1 + ly2) / 2.0
                below_distance = label_center_y - name_center_y
                if below_distance < -20 or below_distance > 420:
                    continue
                phone_value = None
                for value_index, value_text in enumerate(compact):
                    if (value_index == label_index or not value_text or
                            not in_primary_panel(value_index) or not boxes[value_index]):
                        continue
                    if not any(ch.isdigit() for ch in value_text):
                        continue
                    relation = OcrEngine._right_row_score(
                        boxes[label_index], boxes[value_index])
                    if relation is None:
                        continue
                    match = phone_pattern.search(value_text)
                    if not match:
                        continue
                    item = (relation, value_index, match.group(0))
                    if phone_value is None or item < phone_value:
                        phone_value = item
                if phone_value is None:
                    continue
                item = (below_distance, phone_value[0], label_index,
                        phone_value[1], phone_value[2])
                if best is None or item < best:
                    best = item
            return best[4] if best else ""

        records = []
        for anchor in role_anchors:
            name, phone = direct_values(anchor)
            name_info = spatial_name(anchor)
            if name_info:
                name = name_info["name"]
                spatial_phone_value = spatial_phone(anchor, name_info)
                if spatial_phone_value:
                    phone = spatial_phone_value

            # 无坐标或版式简单时，保留按 OCR 顺序向后读取的兼容兜底。
            if not name or not phone:
                phone_label_seen = bool(
                    re.search(r"(?:电话|手机|联系方式|联系人)", compact[anchor["index"]]))
                for next_index in range(anchor["index"] + 1,
                                         min(anchor["index"] + 12, len(compact))):
                    if not in_primary_panel(next_index):
                        continue
                    candidate = compact[next_index]
                    if not candidate:
                        continue
                    phone_match = phone_pattern.search(candidate)
                    if re.search(r"(?:电话|手机|联系方式|联系人)", candidate):
                        phone_label_seen = True
                    if phone_match and phone_label_seen and not phone:
                        phone = phone_match.group(0)
                    candidate_name = valid_name(
                        candidate[:phone_match.start()] if phone_match else candidate)
                    if not name and candidate_name and not re.search(
                            r"(?:电话|手机|联系方式|联系人)", candidate):
                        name = candidate_name
                    if name and phone:
                        break
            records.append({"role": anchor["role"], "index": anchor["index"],
                            "name": name, "phone": phone})

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
        panel_right = OcrEngine._detect_primary_panel_right(ocr_items, fields)

        def in_primary_panel(index):
            if panel_right is None or not boxes[index]:
                return True
            return OcrEngine._metrics(boxes[index])[0] < panel_right

        date_fields = [
            field for field in fields
            if field.get("key") in ("start_date", "end_date")
        ]
        date_candidates = []
        for index, text in enumerate(texts):
            if not in_primary_panel(index):
                continue
            normalized = OcrEngine._normalize_date(text)
            if normalized:
                date_candidates.append((index, normalized))

        extracted = {}
        used_candidates = set()
        for field in date_fields:
            key = field.get("key")
            keywords = [word for word in field.get("keywords", []) if word]
            best = None
            for label_index, text in enumerate(compact):
                if not in_primary_panel(label_index):
                    continue
                for keyword in keywords:
                    position = text.find(keyword)
                    if position < 0:
                        continue
                    # 先处理“开工日期：2024-01-01”这种同行写法。
                    same_line = OcrEngine._normalize_date(
                        text[position + len(keyword):])
                    if same_line:
                        best = ((0, 0), label_index, label_index, same_line)
                        break

                    for candidate_index, normalized in date_candidates:
                        if candidate_index in used_candidates or candidate_index == label_index:
                            continue
                        relation = OcrEngine._right_row_score(
                            boxes[label_index], boxes[candidate_index])
                        if relation is None:
                            continue
                        # 日期值必须位于标签右侧的同一行；不再依赖 OCR 返回顺序，
                        # 因为斜拍图片中右侧日期经常会先于左侧标签返回。
                        item = (relation, label_index, candidate_index, normalized)
                        if best is None or item < best:
                            best = item
                if best and best[0][0] == 0:
                    break
            if best:
                extracted[key] = best[3]
                used_candidates.add(best[2])
        return extracted

    @staticmethod
    def auto_extract(ocr_items, fields):
        """
        根据字段配置里的关键词，从 OCR 结果中自动提取字段值。

        支持：
          - 同行文本提取：「工程名称：某某工程」→「某某工程」
          - 表格型铭牌：标签与值分行，用【坐标几何】定位值
            （支持斜拍透视同行；优先主铭牌右侧最近，其次正下方）
          - 一张照片包含相邻告示栏时，依据主铭牌边界排除旁板噪声
          - 标签位精确匹配优先（避免「联系电话」干扰「电话」）
          - 同一关键词被多个字段用时自动错开（如两个「手机」）
          - requires_digit 字段要求值里含数字（电话/手机）

        返回: {"key": "value", ...}
        """
        texts = [it.get("text", "") for it in ocr_items]
        boxes = [it.get("box") or [] for it in ocr_items]
        panel_right = OcrEngine._detect_primary_panel_right(ocr_items, fields)

        def in_primary_panel(index):
            if panel_right is None or not boxes[index]:
                return True
            return OcrEngine._metrics(boxes[index])[0] < panel_right

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
            """在第 i 行找到 kw 的值：同行文本 → 透视同行右侧 → 正下方。"""
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
                # 1) 同行右侧：兼容斜拍后 y 轴不重叠的文字框。
                best = None  # (gap, j, v)
                for j, b in enumerate(boxes):
                    if j == i or not b or not in_primary_panel(j):
                        continue
                    if j in used.get(kw, set()):
                        continue
                    t = texts[j].strip()
                    if not t or any(k in t for k in label_words):
                        continue
                    relation = OcrEngine._right_row_score(lb, b)
                    if relation is None:
                        continue
                    v = valid_value(t, need_digit)
                    if not v:
                        continue
                    if best is None or relation < best[0]:
                        best = (relation, j, v)
                if best:
                    return best[1], best[2]
                # 2) 正下方最近（值换行/在下一行）
                best = None
                for j, b in enumerate(boxes):
                    if j == i or not b or not in_primary_panel(j):
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
                        if not in_primary_panel(i):
                            continue
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
