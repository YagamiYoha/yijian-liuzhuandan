# 项目进度存档（供下次会话继续）

> 更新时间：2026-08-31
> 会话工作目录：/home/armstrong/projects/20260901 一键流转单
> 本文件是给"下次继续"看的存档：记录需求、已做决策、已完成工作、剩余事项和复现命令。
> 详细使用说明见 `README.md`。

---

## ⏸ 上次暂停点（2026-08-31 约 19:20，从这里继续）

**核心程序已 100% 完成并实测通过**，只剩两件收尾小事 + 一件需用户在 Windows 上做的事：

1. 【收尾·可选】界面截图给用户看效果：Chromium 下载未完成（见下），完成后：
   ```bash
   # ① 断点续传下载 Chromium（上次已下到约 53MB / 约 170MB）
   cd "测试/.shot/.chrome-cache/chrome/linux-152.0.7977.54"
   curl -L --retry 8 -C - -o chrome.zip \
     "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/152.0.7977.54/linux64/chrome-linux64.zip"
   unzip -q chrome.zip && rm chrome.zip
   # ② 用 ldd 找出 chrome 缺失的运行库，apt-get download 补（libnss3 已在 /tmp 下过一份）
   ldd chrome-linux64/chrome | grep "not found"
   # ③ 截图
   cd 测试/.shot && LD_LIBRARY_PATH=<解压的库目录> node shot.js ../ui_preview.html ../ui_preview.png 1180 820
   ```
   截图后用 read_image 检查、vision_present 发给用户看界面效果。
2. 【收尾·可选】清理：`测试/NotoSansCJKsc-Regular.otf`（16MB 测试字体）、`测试/.shot/`（截图工具链）、`output/` 里带"测试_"和日期戳的测试产物。
3. 【需用户执行·最重要】**Windows 打包**（本机 Linux 无法代做，见 README）：
   能上网的 Windows 机装 Python 3.10/3.11 → 拷整个项目 → 双击 `build_windows.bat` → 把 `dist\一键流转单.exe` + `config.json` + `templates\` 拷进内网。
4. 【打包后验证】PySide6 原生窗口本机无显示环境未实测；若 exe 窗口空白，打包命令加 `--collect-all PySide6` 重试（README FAQ Q4）。
5. 【后续适配】用户提供真实 Word/Excel 模板后：模板内写 `{{key}}` 占位符 + 改 config.json 的 fields/keywords，无需改代码。

## 一、需求（用户已确认）

给公司内网（Windows 10 政府版，**无外网**）做一个小程序，功能：

1. **离线 OCR** 识别图片文字 —— 识别对象是**施工工程铭牌**：中文为主，项目名称含少量英文字母，电话含数字，**印刷体**；
2. 识别结果**自动填入** Word/Excel 模板；
3. 可上传**附件**（图片类直接插入 Word 模板的"附件"位置）；
4. 有前端界面便于操作：上传图片、上传附件、填写/修改表单字段、一键生成文件；
5. **绿色免安装单文件 exe** 部署（内网电脑不装任何东西）。

用户决策记录：
- 部署方式：绿色免安装单文件 exe ✓
- OCR 文字类型：印刷体 ✓
- 界面：**要原生桌面程序窗口**（不要浏览器）→ 采用 PySide6 原生窗口 + 内嵌 HTML 界面（混合方案）
- 模板：暂时没有真实模板 → 先做通用占位符方案 + 生成示例模板

## 二、技术方案（已定，不要推翻）

- 后端：Flask（本地 127.0.0.1 服务，OCR/上传/生成接口）
- 界面：PySide6 原生窗口 + QtWebEngine 加载本地页面（HTML/CSS/JS 全部本地资源，零外网依赖）
- 离线 OCR：RapidOCR（rapidocr_onnxruntime + onnxruntime，模型随包）
- Word 填充：python-docx（占位符 `{{key}}`，正文+表格都支持；图片/附件插入占位符位置）
- Excel 填充：openpyxl
- 打包：PyInstaller onefile（在**能上网的 Windows 打包机**上执行一次，Python 3.10/3.11）
- 内网部署：exe + config.json + templates/ 三样放同一文件夹

## 三、已完成的工作

### 代码文件（全部完成并通过测试）
| 文件 | 状态 |
|---|---|
| `main.py`（入口：Flask 线程 + 原生窗口，无 PySide6 时退回浏览器） | ✅ 已测（浏览器模式） |
| `desktop.py`（PySide6 QWebEngineView 窗口，约 30 行） | ✅ 语法检查过；**GUI 本机无法运行验证**（无显示环境），需在 Windows 上确认 |
| `app.py`（Flask 接口：/api/config、/api/ocr、/api/upload_attachment、/api/generate、文件下载、打开输出目录） | ✅ 接口全部实测通过 |
| `ocr_engine.py`（RapidOCR 封装：惰性加载、线程锁、关键词自动提取字段） | ✅ 真实 OCR 实测通过（中英文） |
| `template_filler.py`（Word/Excel 填充：文本/图片/附件占位符） | ✅ 实测通过 |
| `config.json`（字段/keywords/模板路径/图片宽度，可改） | ✅ |
| `static/`（index.html / style.css / app.js，界面 + 前端逻辑） | ✅ 服务实测通过 |
| `requirements.txt`、`build_windows.bat`（打包脚本） | ✅ 已写，**未在 Windows 实测** |
| `README.md`（打包/部署/自定义/FAQ） | ✅ |
| `测试/self_test.py`（生成示例模板 + 填充/生成链路自测） | ✅ 全部通过 |
| `测试/test_ocr.py`（真实 OCR 冒烟测试） | ✅ 通过（英文 89~92%，中文 80~91%） |
| `测试/make_ui_preview.py`（生成界面预览 HTML） | ✅ 已生成预览，截图待 Chromium 下载完成 |
| `templates/流转单模板.docx`、`templates/台账模板.xlsx`（示例模板，已生成） | ✅ |

### 测试结果记录
1. 自测（填充+生成链路）：全部通过
2. 真实 OCR（英文测试图）：4 行全对，关键词提取 4/4 正确
3. 真实 OCR（中文测试图）：`工程名称/施工单位/联系电话/日期` 全部正确提取（80~91% 置信度）
4. 活服务器端到端：上传图片→OCR→上传附件→生成→Word 内容验证（工程名称已写入、无占位符残留、2 张图片插入）→ 全部通过

## 四、剩余事项（按优先级）

1. **【重要·需用户执行】Windows 打包**：在能上网的 Windows 机上装 Python 3.10/3.11 → 运行 `build_windows.bat`。这一步本机（Linux）无法代做。
2. **【可选】界面截图**：给用户看 UI 效果。Chromium 下载未完成（暂停点约 53MB/170MB，支持断点续传），命令见"暂停点"一节。
3. **【可选】PySide6 桌面窗口实测**：本机无显示环境无法验证 GUI，打包后在 Windows 上确认窗口正常（FAQ 有 QtWebEngine 打包问题的对策：加 `--collect-all PySide6`）。
4. **【可选】套真实模板**：用户拿到真实 Word/Excel 模板后，把占位符 `{{key}}` 放进去、改 config.json 即可，无需改代码。
5. 收尾清理：`测试/.shot/`（截图工具链）、`测试/NotoSansCJKsc-Regular.otf`（测试字体 16MB）、`output/` 中测试产物可删。

## 五、下次继续的操作指引

### 本机开发环境（已建好）
- Python 虚拟环境：`.venv-dev/`（已装 flask、python-docx、openpyxl、rapidocr_onnxruntime 1.2.3、onnxruntime 1.29.0、pillow、playwright 未装成——改用 puppeteer/node）
- Node：系统自带 v22，puppeteer 装在 `测试/.shot/node_modules`，Chromium 缓存 `测试/.shot/.chrome-cache`

### 常用命令
```bash
# 跑自测（生成示例模板 + 填充/生成链路）
.venv-dev/bin/python 测试/self_test.py

# 跑真实 OCR 测试（中英文）
.venv-dev/bin/python 测试/test_ocr.py

# 起本地服务（浏览器模式调试）
.venv-dev/bin/python app.py --web          # 或 main.py

# 界面截图（等 Chromium 就绪后）
cd 测试/.shot && LD_LIBRARY_PATH=<运行库目录> node shot.js ../ui_preview.html ../ui_preview.png 1180 820
```

### 网络与代理注意事项（本机环境特性）
- pip 装大包用清华镜像最快：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ ...`
- 直连 pypi/npm 偶发中断；`apt-get download` 可用（免 root）；sudo 被禁（no-new-privileges）；文件沙箱只允许写工作区（npm/pip 缓存要指到工作区内）
- Python 3.14 太新：rapidocr 只能装到 1.2.3（API 相同，仅测试用）。**Windows 打包机务必用 Python 3.10/3.11**，requirements.txt 会装新版（PP-OCRv4 模型）

## 六、给用户交付时的话术要点（下次总结用）

- 方案：PySide6 原生窗口（桌面程序观感）+ 内嵌网页界面 + Flask 后端 + RapidOCR 离线识别 + PyInstaller 单文件 exe
- 本机已实测：填充链路、真实 OCR（中英文）、活服务器端到端全部通过
- 打包必须在能上网的 Windows 上做一次；之后内网拷贝 exe + config.json + templates/ 三样即可
- 真实模板到手后：模板里写 `{{key}}` 占位符 + 改 config.json 即可适配，不用改代码

## 七、会话突发问题记录（2026-08-31 追加）

- 现象：用户在 Web GUI 里点不开 `项目进度.md`，刷新页面后整页变灰，找不到文件打开方式。
- 排查：文件本身完好（UTF-8，8577 字节）；GUI 服务 200、所有前端资源 200、会话日志无服务端报错；GUI 客户端 bundle 中未找到"暂停置灰"逻辑。
- 结论：疑似 GUI 客户端侧的文件打开/渲染问题（可能涉及中文文件名或客户端状态）。**对策：存档内容直接贴进会话对话里展示**；另建了 `PROGRESS.md`（英文文件名副本）供点击；并用 dsh_im_return_file 发过附件。
- 遗留：若 GUI 文件打开持续异常，可尝试强刷（Ctrl+F5）/无痕窗口重开 http://127.0.0.1:3081；本机 Chromium 下载完成后可自行截 GUI 页面确认"灰色"形态。
- 根因已定位（追加）：开发机是 WSL2（宿主 Windows，主机名 DESKTOP-RQ0BBKO，内核 microsoft-standard-WSL2）。
  GUI"打开文件"在 WSL 下走 wslpath + powershell.exe，但 `/etc/environment` 把 PATH 写死为
  /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin，
  不含 /mnt/c/Windows/System32 等 Windows 目录 → spawn powershell.exe ENOENT。
  文件本身完好，powershell.exe 实际存在于 /mnt/c/Windows/System32/WindowsPowerShell/v1.0/。
- 立即可用方案：用户在 Windows 资源管理器粘贴
  \\wsl.localhost\Ubuntu\home\armstrong\projects\20260901 一键流转单 即可浏览/打开全部项目文件。
- 彻底修复（需 root + 重启服务，用户有空时做）：sudo 编辑 /etc/environment，PATH 追加
  :/mnt/c/Windows/System32:/mnt/c/Windows，然后重启 dsh web（会话可续）。我的沙箱只读系统目录、
  无 root，且不能重启 GUI 服务（会断开会话），故只能由用户执行。
- 灰色页面：settings.yaml 记录 ui-theme.preference: dark（深色主题），疑为灰色观感来源；GUI 有主题切换（bloom-theme 插件在 web profile 里被 disabled）。
- 补充确认（同日）：界面里"路径显示为灰色"= 界面检测到本机(WSL)原生打开文件功能不可用后，
  把所有路径统一渲染为灰色只读样式（不提供打开按钮）。文件数据无异常，UNC 路径可正常打开。
  dsh web 无法在沙箱内启动（~/.dsh 只读），重启需用户在 WSL 终端操作。
- 修复执行（2026-08-31，用户授予 full access 后）：
  1) 无法改 /etc/environment（root 所有，无 sudo 密码）；沙箱解除后仍是普通用户。
  2) 服务 PATH 目录（/usr/local/bin 等）全部 root 所有，无法放 powershell.exe 桥接脚本。
  3) 采用"带修复 PATH 重启服务"方案：创建 /home/armstrong/.dsh/restart-web.sh，
     杀死旧服务后以 PATH+=Windows目录 重新启动 `node /usr/local/bin/dsh web --port 3081 --no-open`，
     经 setsid 独立后台执行（杀旧服务不影响重启脚本本身）。
  4) 已在 ~/.bashrc 追加 /mnt/c/Windows/System32 等目录到 PATH（用户终端也可用 powershell.exe）。
  5) 注意：重启会断开 GUI 约几秒，会话数据在磁盘上不丢；重启日志 ~/.dsh/web-restart.log。

## 八、打包 exe 进展（2026-08-31 深夜，重要）

- **exe 已成功产出**：`C:\Users\armstrong\form_tool\dist\一键流转单.exe`（302MB，Python 3.12 + PyInstaller 6.22.2）。详见 `打包与排查记录.md`。
- **部署要求**：exe 同目录必须有 config.json + templates\（已加入 build_windows.bat 自动复制）。
- **❌ 未解决问题**：exe 基础接口正常（/、/api/config 200），但 **POST /api/ocr 导致 exe 崩溃退出**（502 后进程消失）。下次继续的排查方向和已加的日志/faulthandler 见 `打包与排查记录.md` 第三节。
- 源码已改进（待重打包生效）：main.py 友好报错+faulthandler+崩溃日志；app.py OCR 异常写日志；build_windows.bat 自动组装 dist。
- 测试图：`测试/_ocr_test.png`。

## 九、✅ 打包 exe 全链路验证通过（2026-08-31 深夜追加）

- 第二次构建后完整实测：OCR（中文4字段）→ 附件上传 → 生成 Word/Excel → 内容验证全通过，exe 稳定。
- 之前的"OCR 导致 exe 崩溃"是误判：原因是测试脚本走了系统代理（urllib 读 http_proxy），代理对 localhost 返回 502。用 curl --noproxy 直连正常。
- 结论：**exe 已可用**。部署 = 拷贝 `C:\Users\armstrong\form_tool\dist\` 整个文件夹到内网电脑。
- 下次任务：①（可选）再跑一次完整测试确认稳定性；② 套真实模板；③ 交付使用说明。

## 十、✅ 真实铭牌自动填写功能完成（2026-08-31 深夜）

- 用户提供真实施工铭牌照片（红框内容：工程名称/建设地址/建设单位/监理单位/施工单位/设计单位/工程类别/建筑面积/开竣工日期/项目经理/文明施工专管员/电话/手机）。
- **config.json 字段重写**为铭牌对应字段（19 个，含 requires_digit 标记电话/手机类字段）。
- **ocr_engine.auto_extract 算法升级**：支持表格型铭牌——标签与值分行时用【坐标几何】定位（同行右侧：y重叠≥55%后取水平最近；否则正下方最近），标签位精确匹配优先、同关键词多字段自动错开、数字校验。
- **实测**：打包 exe 上传真实铭牌照片 → 15/15 字段全部正确提取（李志强/15502188920/021-56174211 等）。
- 示例模板已更新（流转单模板.docx 10 行表格 + 台账模板.xlsx 15 列），含全部新字段占位符。
- 界面预览图已用真实数据重新生成（测试/ui_preview.png）。
- 待办：真实内网部署前，可让用户确认最终字段清单/模板样式；套真实流转单模板。

## 十一、明天要做的事（用户预告 2026-09-01）

用户明天会提供：
1. **多个施工铭牌样本**（用于进一步验证/调优 OCR 提取，特别是不同排版）；
2. **公司真实的 Word/Excel 模板**（流转单/台账模板，含公司需要的字段）；
3. **UI 界面需按模板实际需要调整**（表单字段、标签、布局等）。

明天的工作流（按此执行）：
1. 拿到真实模板 → 按模板需要的字段**调整 config.json 的 fields**（增删字段、改标签、改 keywords）；
2. 在真实模板里**放好 {{key}} 占位符**（正文/表格/单元格都支持）；
3. 用多个铭牌样本**回归测试提取算法**（若排版差异大，微调 ocr_engine 的几何阈值）；
4. 视需要调整 **static/index.html 的界面文案/分区**（目前表单字段由 config.json 动态生成，改 config 即改界面）；
5. 重新打包 exe → 组装 dist → 端到端验证 → 交付。

当前基线（已就绪）：
- exe 已重建（含坐标提取算法 + 新 config + 新模板），位于 C:\Users\armstrong\form_tool\dist\；
- 打包与排查记录.md、PROGRESS.md 与 项目进度.md 同步最新；
- 测试素材：测试/真实铭牌照片.jpg、测试/_ocr_test.png、测试/真实铭牌_OCR结果.json。

## 十二、✅ 2026-09-01 字段修正与启动优化

- 工程信息界面移除“设计单位”和“建筑面积”。
- 工程类别改为纯手动四选一：工地/空地/堆场/手动输入，不参与 OCR 自动填充。
- 开工/竣工日期只接受明确日期格式并统一为 `YYYY-MM-DD`；未识别到时保持空白。
- 项目经理/负责人改为角色专用识别，过滤“姓名/手机”等表头；没有可靠姓名或联系方式时保持空白。只有明确“负责人”而没有项目经理时，才把负责人转入项目经理。
- `python-docx` 改为生成文件时按需加载，减少程序启动阶段的依赖初始化。
- Windows 默认封装改为 PyInstaller `onedir` 目录版，避免单文件 exe 每次启动解压完整 Qt/OCR 运行库；新的部署入口为 `dist\\一键流转单\\一键流转单.exe`。
- 用 `G:\\20260901\\IMG_20240402_093434.jpg` 回归验证：项目经理识别为“孟祥耀”，项目经理联系方式/日期/工程类别均保持空白；Word 生成测试通过且成品无底色标记。
- 已生成 Windows 目录版发布包：`outputs\\一键流转单-目录版-修正版.zip`（ZIP 约 297 MB，解压后约 704 MB）。

## 十三、✅ 2026-09-01 真实试用问题修正与最新封装

- Word 第 3 项改为按完整标签“3.该工程施工变情况”定位，施工变情可以正常写入；线路名称、工程名称、建设单位、施工单位等冒号后的自动值设为非粗体；成品继续清除模板底色。
- Word 日期后的铭牌图片和附件图片按正文可用宽度等比例放大，并限制在页面正文区域内。
- Excel 按设备主人选择人员工作表；不存在时复制“万羿辉”人员表的格式和第 1-3 行表头后新建，不复制历史记录；危险源描述改取“危险点排摸”。
- 项目经理识别增强：支持角色标签拆分成多个 OCR 框；同时兼容项目经理/负责人及联系方式分流，无可靠姓名或电话时保持空白。
- 危险点排摸框固定为与普通字段一致的高度；新增 `使用说明.txt`，崩溃日志增加时间、故障位置、程序目录、运行模式、系统、异常类型、详细堆栈和反馈提示。
- 最新目录版已完成冻结程序接口回归：`outputs\\一键流转单-目录版-最新修正版.zip`，ZIP 约 297 MB；解压后运行整个“一键流转单”文件夹中的 exe。

## 十四、✅ 2026-09-02 斜拍铭牌与相邻面板 OCR 修正

- 用 `G:\\20260901\\IMG_20241124_084024.jpg` 复现了工程名称被右侧“上海”覆盖、项目经理误识别为“属地劳动”的问题。
- OCR 增加主铭牌边界检测：当照片同时包含相邻告示栏/铭牌时，依据“工程名称”主值和旁栏字段组排除旁板内容。
- OCR 增加透视斜拍同行判断：不再只依赖 y 轴框重叠，支持照片中右侧文字整体向上偏移的表格；项目经理/电话改按“姓名/电话”行的坐标关系匹配。
- 新照片回归结果：工程名称为“宝山区杨行镇川社区BSP0-0401单元05B-05地块（“城中村”改造项目一杨行镇老集镇）征收安置房项目”；项目经理为“薛东 / 15861384650”；项目经理2为“方友根 / 15800685496”；开工日期为 `2024-07-28`，竣工日期为 `2026-12-31`。
- 旧样本、无坐标兼容用例、OCR 冒烟测试和 `/api/ocr` 接口均通过；Windows 目录版已重新构建并用新照片验证通过。
- 最新可直接解压使用的发布包为 `outputs\\一键流转单-目录版-20260902-OCR修正版.zip`，ZIP 完整性检查通过且不含测试上传照片。
