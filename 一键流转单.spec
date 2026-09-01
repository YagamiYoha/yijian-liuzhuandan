# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files


datas = [('static', 'static')]
binaries = []
hiddenimports = [
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineCore',
    'shiboken6',
]

# RapidOCR 的模型和 yaml 配置不是 Python 导入依赖，需要显式收集。
# PySide6/onnxruntime 则由 PyInstaller 官方 Qt/onnxruntime hooks 根据实际
# 导入的模块自动收集，避免把全部 Qt 模块、开发工具和调试资源带入成品。
datas += collect_data_files('rapidocr_onnxruntime')


def is_foreign_icu(item):
    """排除从打包机 PATH 误收集的 Poppler ICU DLL。"""
    for part in item:
        name = os.path.basename(str(part)).lower()
        if name.startswith('icu') and name.endswith('.dll'):
            return True
    return False


def is_build_artifact(item):
    """排除 PySide6 包内仅用于开发/链接的 QML 构建产物。"""
    for part in item:
        path = str(part).replace('\\', '/').lower()
        name = os.path.basename(path)
        if '/objects-debug/' in path or '/objects-relwithdebinfo/' in path:
            return True
        if name.endswith('.debug.pak'):
            return True
        if name.endswith(('.obj', '.lib', '.prl')):
            return True
    return False


datas = [item for item in datas
         if not is_foreign_icu(item) and not is_build_artifact(item)]
binaries = [item for item in binaries
            if not is_foreign_icu(item) and not is_build_artifact(item)]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    # 删除未使用的断言/调试字节码，减小纯 Python 部分体积。
    optimize=1,
)
pyz = PYZ(a.pure)

# Analysis 会在扫描所有原生扩展的依赖时再次加入宿主机 ICU，必须在
# Analysis 完成后再过滤一次，才能确保这些 DLL 不会进入最终目录。
final_binaries = [item for item in a.binaries
                  if not is_foreign_icu(item) and not is_build_artifact(item)]
final_datas = [item for item in a.datas
               if not is_foreign_icu(item) and not is_build_artifact(item)]

# 使用 onedir：QtWebEngine + OCR 模型等大文件只部署一次，启动时无需把整个
# 程序重新解压到临时目录，也更不容易被内网杀毒软件误判为自解压行为。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='一键流转单',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

COLLECT(
    exe,
    final_binaries,
    final_datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='一键流转单',
)
