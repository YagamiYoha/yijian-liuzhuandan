# -*- coding: utf-8 -*-
"""
Word / Excel 模板填充。

约定：模板中使用 {{key}} 占位符，程序把对应值替换进去。
  - 文本字段：{{project_name}} 等，替换为对应文字。
  - 图片字段：{{铭牌图片}} 等，替换为上传的图片（插入到该位置）。
  - 附件字段：{{附件}}，替换为上传的附件（图片直接插入，其它文件记录文件名）。

Word 模板中的占位符可以放在正文段落或表格单元格里，两者都会被处理。
"""

import os

from docx import Document
from docx.shared import Cm


class TemplateFiller:
    """模板填充器（Word 用 python-docx，Excel 用 openpyxl）。"""

    # ---------- 文本占位符替换 ----------
    @staticmethod
    def _replace_in_paragraph(paragraph, placeholder, value):
        """替换单个段落里的占位符，兼容占位符跨多个 run 的情况。"""
        if placeholder not in paragraph.text:
            return False

        # 优先单 run 内替换，尽量保留原有格式
        for run in paragraph.runs:
            if placeholder in run.text:
                run.text = run.text.replace(placeholder, value)
                return True

        # 占位符被拆分到多个 run 时：合并到第一个 run，清空其余
        full = "".join(r.text for r in paragraph.runs)
        new_full = full.replace(placeholder, value)
        if paragraph.runs:
            paragraph.runs[0].text = new_full
            for r in paragraph.runs[1:]:
                r.text = ""
        return True

    @staticmethod
    def _iter_paragraphs(doc):
        """遍历正文所有段落 + 所有表格单元格里的段落。"""
        for p in doc.paragraphs:
            yield p
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        yield p

    # ---------- 图片插入 ----------
    @staticmethod
    def _insert_images_at(paragraph, images):
        """
        在指定段落末尾依次插入图片。

        images: [ (图片路径, 宽度cm), ... ]
        """
        for path, width_cm in images:
            if path and os.path.isfile(path):
                run = paragraph.add_run()
                run.add_picture(path, width=Cm(width_cm))

    # ---------- Word 填充 ----------
    @classmethod
    def fill_word(cls, template_path, output_path, text_map,
                  image_map=None, attachment_images=None, attachment_text=""):
        """
        填充 Word 模板。

        参数:
            template_path: 模板 .docx 路径
            output_path:   输出 .docx 路径
            text_map:      {"key": "value", ...} 替换 {{key}}
            image_map:     {"{{占位符}}": [(图片路径, 宽度cm), ...], ...}
            attachment_images: [(图片路径, 宽度cm), ...] 插入到 {{附件}} 占位符
            attachment_text: 非图片附件的文件名（写入 {{附件}} 位置）
        """
        doc = Document(template_path)

        # 1) 文本替换（正文 + 表格）
        for p in cls._iter_paragraphs(doc):
            for key, value in text_map.items():
                cls._replace_in_paragraph(p, "{{%s}}" % key, str(value if value is not None else ""))

        # 2) 图片替换（铭牌图片等）
        for placeholder, images in (image_map or {}).items():
            for p in cls._iter_paragraphs(doc):
                if placeholder in p.text:
                    cls._replace_in_paragraph(p, placeholder, "")
                    cls._insert_images_at(p, images)
                    break  # 只处理第一处

        # 3) 附件插入（图片直接插入；非图片附件写入文件名）
        if attachment_images or attachment_text:
            for p in cls._iter_paragraphs(doc):
                if "{{附件}}" in p.text:
                    if attachment_images:
                        cls._replace_in_paragraph(p, "{{附件}}", "")
                        cls._insert_images_at(p, attachment_images)
                    else:
                        cls._replace_in_paragraph(p, "{{附件}}", attachment_text)
                    break

        doc.save(output_path)
        return output_path

    # ---------- Excel 填充 ----------
    @classmethod
    def fill_excel(cls, template_path, output_path, text_map, sheet_name=None):
        """
        填充 Excel 模板（替换单元格里的 {{key}} 占位符）。

        参数:
            template_path: 模板 .xlsx 路径
            output_path:   输出 .xlsx 路径
            text_map:      {"key": "value", ...}
            sheet_name:    指定工作表名；为空则处理所有工作表
        """
        import openpyxl

        wb = openpyxl.load_workbook(template_path)
        sheets = [wb[sheet_name]] if sheet_name else wb.worksheets

        for ws in sheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        for key, value in text_map.items():
                            placeholder = "{{%s}}" % key
                            if placeholder in cell.value:
                                cell.value = cell.value.replace(
                                    placeholder, str(value if value is not None else ""))

        wb.save(output_path)
        return output_path
