# -*- coding: utf-8 -*-
"""
原生桌面窗口：用 PySide6 + QtWebEngine 把本地界面包进一个真正的程序窗口。

窗口拥有系统原生标题栏、任务栏图标、可最小化/最大化/关闭，
窗口内部渲染本地 HTML 界面（127.0.0.1 的 Flask 服务），不依赖系统浏览器。
"""

import sys


def open_desktop_window(url, title, width, height):
    """
    创建并显示原生窗口，返回 (QApplication, QMainWindow)。

    调用方随后应执行 app.exec() 进入事件循环。
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(title)

    win = QMainWindow()
    win.setWindowTitle(title)
    win.resize(int(width), int(height))

    view = QWebEngineView()
    view.setUrl(QUrl(url))
    win.setCentralWidget(view)
    win.show()

    return app, win
