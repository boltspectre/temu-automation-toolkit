@echo off
title IKUN Build Script v3.0
:: ==============================================
:: 1. 关闭快速编辑模式（避免误点暂停脚本）
reg add "HKCU\Console" /v QuickEditMode /t REG_DWORD /d 0 /f > nul 2>&1

:: 2. 设置编码为UTF-8，防止中文字符乱码
chcp 65001 > nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] UTF-8 编码失败，使用系统默认编码
)

:: 3. 启用延迟变量扩展（关键：循环/条件中动态读取变量）
setlocal EnableDelayedExpansion

:: 4. 启用Windows终端ANSI颜色支持
reg add "HKCU\Console" /v VirtualTerminalLevel /t REG_DWORD /d 1 /f > nul 2>&1

:: ==============================================
:: 5. 定义核心路径（统一管理，便于修改）
set "VENV_PATH=.venv"
set "VENV_PYTHON=%VENV_PATH%\Scripts\python.exe"
set "VENV_ACTIVATE=%VENV_PATH%\Scripts\activate.bat"
set "MAIN_SCRIPT=main.py"
set "OUTPUT_DIR=../ikun_dist/ikun_build"
set "ICON_FILE=favicon.ico"

:: 3. 调用本地Python脚本打印Logo（核心修复）
echo.
if exist "%VENV_PYTHON%" (
    :: 使用虚拟环境的Python执行logo脚本
    "%VENV_PYTHON%" lite_modules/print_logo.py
) else (
    :: 备用：无虚拟环境时用系统Python
    python print_logo.py
)
echo.

:: ==============================================
:: 6. 用户选择控制台模式
echo.
echo ==============================================
echo 请选择调试控制台模式:
echo 1. 生产模式-无控制台模式 (windowed application)
echo 2. 调试模式-控制台模式 (with console window)
echo ==============================================

:select_console
set "console_choice="
set /p console_choice="请输入您的选择 (1 或 2): "

:: 去除前后空格
if defined console_choice set "console_choice=%console_choice: =%"

if "%console_choice%"=="1" (
    set "CONSOLE_MODE=disable"
    echo [INFO] 生产模式-无控制台模式 已选择
    goto :console_selected
) else if "%console_choice%"=="2" (
    set "CONSOLE_MODE=force"
    echo [INFO] 调试模式-控制台模式 已选择
    goto :console_selected
) else (
    echo [WARN] 无效，请重新选择
    goto select_console
)
:console_selected
echo ==============================================
echo.

:: ==============================================
echo ==============================================
:: 7. 记录开始时间
for /f "tokens=1-4 delims=:.," %%a in ("%time: =0%") do (
    set /a "start_h=100%%a %% 100"
    set /a "start_m=100%%b %% 100"
    set /a "start_s=100%%c %% 100"
    set /a "start_ms=100%%d %% 100"
    set "start_time_str=%time%"
)
set /a "start_total_sec=start_h*3600 + start_m*60 + start_s"
echo [Start] 打包开始时间: %start_time_str%...
echo ==============================================

:: ==============================================
:: 8. 前置检查（核心）
echo.
echo [1/6] 进行前置检查...

:: 检查主脚本
if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] 主脚本 %MAIN_SCRIPT% 不存在!
    pause
    exit /b 1
)

:: 检查图标文件
if not exist "%ICON_FILE%" (
    echo [ERROR] 图标文件 %ICON_FILE% 不存在!
    pause
    exit /b 1
)

:: 检查虚拟环境
if not exist "%VENV_PATH%" (
    echo [ERROR] 虚拟环境 %VENV_PATH% 不存在!
    pause
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
    echo [ERROR] 虚拟环境激活脚本不存在!
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [ERROR] 虚拟环境 Python 不存在!
    pause
    exit /b 1
)

echo [1/6] 前置检查通过，继续打包 OK

:: ==============================================
:: 9. 清理旧打包文件（避免冲突）
echo.
echo [2/6] 清理旧打包文件...
if exist "%OUTPUT_DIR%" (
    rd /s /q "%OUTPUT_DIR%" > nul 2>&1
    if !errorlevel! neq 0 (
        echo [WARN] 清理旧打包文件失败，请手动删除
        pause
        exit /b 1
    )
)
echo [2/6] 清理旧打包文件完成 OK

:: ==============================================
:: 10. 终止残留进程（关键）
echo.
echo [3/6] 终止残留进程...
taskkill /f /im python.exe > nul 2>&1
taskkill /f /im pythonw.exe > nul 2>&1
taskkill /f /im scons.exe > nul 2>&1
timeout /t 2 /nobreak > nul 2>&1
echo [3/6] 进程清理完成 OK

:: ==============================================
:: 11. 激活虚拟环境
echo.
echo [4/6] 激活虚拟环境...
call "%VENV_ACTIVATE%"
if !errorlevel! neq 0 (
    echo [ERROR] 激活虚拟环境失败!
    echo [HINT] 请尝试重新创建虚拟环境: python -m venv %VENV_PATH%
    pause
    exit /b 1
)
echo [4/6] 虚拟环境激活成功 OK

:: ==============================================
:: 12. 检查Nuitka
echo.
echo [5/6] 检查 Nuitka 是否安装...
"%VENV_PYTHON%" -m nuitka --version > nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Nuitka 未安装在虚拟环境中!
    echo 安装 Nuitka...
    "%VENV_PYTHON%" -m pip install nuitka==2.8.10 --no-cache-dir
    if !errorlevel! neq 0 (
        echo [ERROR] Nuitka 安装失败!
        pause
        exit /b 1
    )
)
echo [5/6] Nuitka 安装检查通过 OK

:: ==============================================
:: 13. 执行 Nuitka 打包命令
echo.
echo [6/6] 开始 Nuitka 打包命令...
echo 这可能需要 30-60 minutes, 请等待...
echo.

python -m nuitka ^
--standalone ^
--output-dir="%OUTPUT_DIR%" ^
--job=4 ^
--windows-uac-admin ^
--output-filename=ikun联盟.exe ^
--windows-console-mode=%CONSOLE_MODE% ^
--remove-output ^
--show-scons ^
--windows-icon-from-ico="%ICON_FILE%" ^
--enable-plugin=pyqt5 ^
--include-package=pandas ^
--include-package=qasync ^
--include-package=playwright ^
--include-package-data=playwright ^
--include-data-files=gui/img/*=gui/img/ ^
--include-data-files=favicon.ico=favicon.ico ^
--include-package=fastapi ^
--include-package=uvicorn ^
--include-package=uvicorn.protocols ^
--include-package=starlette ^
--include-package=pydantic ^
--include-package=anyio ^
--nofollow-import-to=pytest ^
--nofollow-import-to=unittest ^
--nofollow-import-to=setuptools ^
--nofollow-import-to=pip ^
--nofollow-import-to=tkinter ^
--nofollow-import-to=distutils ^
--nofollow-import-to=pydoc ^
--nofollow-import-to=doctest ^
--nofollow-import-to=torch ^
--nofollow-import-to=torch._dynamo ^
--nofollow-import-to=torch._inductor ^
--nofollow-import-to=functorch ^
"%MAIN_SCRIPT%"




:: ==============================================
:: 14. 检查打包结果
if errorlevel 1 (
    echo.
    echo ==============================================
    echo [ERROR] 打包失败，错误码: %errorlevel%
    echo ==============================================
    echo.
    echo 可能的原因:
    echo 1. 磁盘空间不足
    echo 2. 防病毒软件阻止打包
    echo 3. 权限问题
    echo 4. 虚拟环境损坏了
    echo.
    echo 尝试以管理员身份运行或临时禁用防病毒软件
    echo ==============================================
    pause
    exit /b 1
)

echo.
echo ==============================================
echo [SUCCESS] 打包成功!
echo 输出: %OUTPUT_DIR%\ikun联盟.exe
echo ==============================================

:: 15. 记录结束时间
for /f "tokens=1-4 delims=:.," %%a in ("%time: =0%") do (
    set /a "end_h=100%%a %% 100"
    set /a "end_m=100%%b %% 100"
    set /a "end_s=100%%c %% 100"
    set /a "end_ms=100%%d %% 100"
    set "end_time_str=%time%"
)
set /a "end_total_sec=end_h*3600 + end_m*60 + end_s"

:: 16. 计算耗时
set /a "elapsed_sec=end_total_sec - start_total_sec"
if %elapsed_sec% lss 0 (
    set /a "elapsed_sec=elapsed_sec + 24*3600"
)
set /a "elapsed_h=elapsed_sec / 3600"
set /a "elapsed_m=(elapsed_sec %% 3600) / 60"
set /a "elapsed_s=elapsed_sec %% 60"

set /a "elapsed_ms=end_ms - start_ms"
if %elapsed_ms% lss 0 (
    set /a "elapsed_ms=elapsed_ms + 100"
    set /a "elapsed_s=elapsed_s - 1"
)

echo ==============================================
echo [End] 打包完成时间: %end_time_str%
echo 总耗时: !elapsed_h!h !elapsed_m!m !elapsed_s!.!elapsed_ms!s
echo ==============================================
echo.
pause