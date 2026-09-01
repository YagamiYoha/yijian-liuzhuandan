# -*- coding: utf-8 -*-
"""
程序入口（PyInstaller 打包入口）。

流程：
  1. 在后台线程启动本地 Flask 服务（OCR、模板填充、文件上传下载）；
  2. 打开 PySide6 原生桌面窗口，加载本地界面；
  3. 若 PySide6/QtWebEngine 不可用（如开发机上没装），退回系统浏览器。

在能上网的 Windows 电脑上用 build_windows.bat 打包成目录版程序。
"""

import faulthandler
import os
import platform
import socket
import sys
import threading
import time
import traceback
import webbrowser


_QT_DLL_HANDLES = []
_FAULT_LOG_HANDLE = None


def prepare_qt_dll_path():
    """显式加入 PyInstaller 内置的 Qt/Shiboken DLL 目录。"""
    if not getattr(sys, "frozen", False):
        return
    root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for path in (root, os.path.join(root, "PySide6"), os.path.join(root, "shiboken6")):
        if not os.path.isdir(path):
            continue
        try:
            _QT_DLL_HANDLES.append(os.add_dll_directory(path))
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")

from app import create_app, load_config


def app_dir():
    """exe/脚本所在目录（崩溃日志、config.json 等都放这里）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def crash_log_path():
    return os.path.join(app_dir(), "崩溃日志.log")


def log_crash(context, exc):
    """把启动/桌面异常写成便于外部排查的完整诊断记录。"""
    try:
        with open(crash_log_path(), "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("发生时间：%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("故障位置：%s\n" % context)
            f.write("程序目录：%s\n" % app_dir())
            f.write("运行模式：%s\n" % ("打包版 exe" if getattr(sys, "frozen", False) else "源码运行"))
            f.write("Python：%s\n" % sys.version.replace("\n", " "))
            f.write("系统：%s\n" % platform.platform())
            f.write("可执行文件：%s\n" % sys.executable)
            f.write("异常类型：%s\n" % type(exc).__name__)
            f.write("异常信息：%s\n\n" % exc)
            f.write("详细堆栈：\n")
            f.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
            f.write("\n排查提示：请把本日志文件完整发回，并同时说明操作步骤。\n")
    except Exception:
        pass


def show_error(title, message):
    """尽量弹系统对话框提示；失败则退化为打印。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
    except Exception:
        print(title, message)


def find_free_port(preferred):
    """优先使用配置端口，被占用则自动换一个空闲端口。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def wait_until_ready(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    # 开启 faulthandler：程序发生原生崩溃(段错误等)时把各线程栈写入崩溃日志
    global _FAULT_LOG_HANDLE
    try:
        _FAULT_LOG_HANDLE = open(crash_log_path(), "a", encoding="utf-8")
        faulthandler.enable(_FAULT_LOG_HANDLE)
    except Exception:
        pass

    try:
        cfg = load_config()
    except Exception as e:
        log_crash("加载 config.json 失败", e)
        show_error("程序无法启动",
                   "找不到配置文件 config.json（或格式错误）。\n\n"
                   "请确认 config.json 与程序放在同一个文件夹里。\n\n"
                   "详细错误：%s" % e)
        return

    app_cfg = cfg.get("app", {})
    title = app_cfg.get("title", "一键流转单生成工具")
    port = find_free_port(app_cfg.get("port", 8090))
    url = "http://127.0.0.1:%d/" % port

    try:
        app = create_app()
    except Exception as e:
        log_crash("创建应用失败", e)
        show_error("程序无法启动", "初始化失败：%s" % e)
        return

    prepare_qt_dll_path()

    # 先在主线程加载 Qt 核心 DLL，再启动 Flask/OCR 线程，避免 Windows
    # 冻结版中 Qt 与 numpy/opencv 原生 DLL 并发初始化导致 QtCore 加载失败。
    try:
        import PySide6.QtCore  # noqa: F401
    except Exception as e:
        log_crash("Qt 核心模块加载失败", e)

    server = threading.Thread(
        target=app.run,
        kwargs={"host": "127.0.0.1", "port": port,
                "debug": False, "use_reloader": False, "threaded": True},
        daemon=True,
    )
    server.start()
    wait_until_ready(port)

    # 优先原生桌面窗口；失败则退回浏览器（便于在没有 PySide6 的开发机上调试）
    try:
        from desktop import open_desktop_window
        qt_app, win = open_desktop_window(
            url, title,
            app_cfg.get("width", 1180),
            app_cfg.get("height", 820),
        )
        qt_app.exec()
    except Exception as e:
        log_crash("桌面窗口启动失败，退回浏览器", e)
        print("PySide6 不可用，退回浏览器打开界面：", e)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
