@echo off
chcp 65001 >nul
echo ========================================================
echo   一键流转单生成工具 - Windows 目录版打包脚本
echo   请在【能上网】的 Windows 电脑上运行（只需运行一次）
echo   建议 Python 3.10 / 3.11（64 位），并已加入 PATH
echo ========================================================
echo.

cd /d "%~dp0"

REM ---------- 1. 创建虚拟环境 ----------
echo [1/4] 创建虚拟环境...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

REM ---------- 2. 安装依赖 ----------
echo [2/4] 安装依赖（首次较慢，请耐心等待，约 10~20 分钟）...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM ---------- 3. 打包 ----------
echo [3/4] 开始打包目录版（约 5~10 分钟）...
pyinstaller --noconfirm --clean 一键流转单.spec

REM ---------- 4. 组装部署目录（config/templates 放在 exe 旁边）----------
echo [4/4] 组装部署文件...
if not exist dist\一键流转单 mkdir dist\一键流转单
copy /Y config.json dist\一键流转单\config.json >nul
copy /Y 使用说明.txt dist\一键流转单\使用说明.txt >nul
if exist dist\一键流转单\templates rmdir /S /Q dist\一键流转单\templates
xcopy /E /I /Y templates dist\一键流转单\templates >nul
if not exist dist\一键流转单\uploads mkdir dist\一键流转单\uploads
if not exist dist\一键流转单\output  mkdir dist\一键流转单\output

echo.
echo ========================================================
echo   打包完成！部署内容在 dist\一键流转单 文件夹：
echo     1. dist\一键流转单\一键流转单.exe
echo     2. dist\一键流转单\config.json
echo     3. dist\一键流转单\使用说明.txt
echo     4. dist\一键流转单\templates 文件夹（含 Word/Excel 模板）
echo   把整个 dist\一键流转单 文件夹拷到内网电脑，双击 exe 即可使用。
echo ========================================================
pause
