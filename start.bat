@echo off
chcp 65001 >nul
echo ========================================
echo QQ群年度报告分析器 - 一键启动脚本
echo ========================================
echo.

:: 检查Python
echo [1/8] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)
echo ✅ Python已安装

:: 检查Node.js
echo.
echo [2/8] 检查Node.js环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到Node.js，请先安装Node.js
    pause
    exit /b 1
)
echo ✅ Node.js已安装

:: 检查并配置后端.env文件
echo.
echo [3/8] 检查后端配置文件...
if not exist "backend\.env" (
    echo ⚠️  未找到backend\.env，从示例文件创建...
    copy "backend\.env.example" "backend\.env" >nul
    echo.
    echo ⚠️  重要：请编辑 backend\.env 文件配置MySQL数据库信息！
    echo    - MYSQL_HOST（默认：localhost）
    echo    - MYSQL_PORT（默认：3306）
    echo    - MYSQL_USER（默认：root）
    echo    - MYSQL_PASSWORD（必须设置！）
    echo    - MYSQL_DATABASE（默认：qq_reports）
    echo.
    echo 是否现在编辑配置文件？(Y/N)
    set /p edit_config=
    if /i "%edit_config%"=="Y" (
        notepad "backend\.env"
    )
)
echo ✅ 配置文件已存在

:: 安装Python依赖
echo.
echo [4/8] 安装Python依赖...
if not exist "venv" (
    echo 创建Python虚拟环境...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo 安装后端依赖包...
pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if errorlevel 1 (
    echo ⚠️  使用清华源安装失败，尝试官方源...
    pip install -r backend\requirements.txt
)
echo ✅ Python依赖安装完成

:: 安装前端依赖
echo.
echo [5/8] 安装前端依赖...
cd frontend
if not exist "node_modules" (
    echo 安装前端依赖包（这可能需要几分钟）...
    call npm install
    if errorlevel 1 (
        echo ❌ 错误：前端依赖安装失败
        cd ..
        pause
        exit /b 1
    )
)
cd ..
echo ✅ 前端依赖安装完成

:: 初始化数据库
echo.
echo [6/8] 初始化数据库...
echo ⚠️  请确保MySQL服务已启动！
echo 按任意键继续初始化数据库，或Ctrl+C取消...
pause >nul
python backend\init_db.py
if errorlevel 1 (
    echo.
    echo ⚠️  数据库初始化失败！请检查：
    echo    1. MySQL服务是否已启动
    echo    2. backend\.env 中的数据库配置是否正确
    echo    3. MySQL用户是否有创建数据库的权限
    echo.
    echo 是否继续启动服务？(Y/N)
    set /p continue=
    if /i not "%continue%"=="Y" (
        pause
        exit /b 1
    )
) else (
    echo ✅ 数据库初始化完成
)

:: 启动后端
echo.
echo [7/8] 启动后端服务...
start "QQ群年度报告-后端" cmd /k "cd /d %CD% && venv\Scripts\activate.bat && python backend\app.py"
timeout /t 3 /nobreak >nul
echo ✅ 后端服务已启动（端口：5000）

:: 启动前端
echo.
echo [8/8] 启动前端服务...
start "QQ群年度报告-前端" cmd /k "cd /d %CD%\frontend && npm run dev"
timeout /t 3 /nobreak >nul
echo ✅ 前端服务已启动（端口：5173）

echo.
echo ========================================
echo 🎉 启动完成！
echo ========================================
echo 📱 前端访问地址：http://localhost:5173
echo 🔧 后端API地址：http://localhost:5000
echo.
echo 💡 提示：
echo    - 两个服务窗口将保持打开状态
echo    - 关闭窗口即停止对应服务
echo    - 按Ctrl+C可停止服务
echo ========================================
echo.
pause
