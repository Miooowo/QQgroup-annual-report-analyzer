#!/bin/bash

echo "========================================"
echo "QQ群年度报告分析器 - 一键启动脚本"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python
echo "[1/8] 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到Python3，请先安装Python 3.8+${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python已安装${NC}"
python3 --version

# 检查Node.js
echo ""
echo "[2/8] 检查Node.js环境..."
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到Node.js，请先安装Node.js${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Node.js已安装${NC}"
node --version

# 检查并配置后端.env文件
echo ""
echo "[3/8] 检查后端配置文件..."
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}⚠️  未找到backend/.env，从示例文件创建...${NC}"
    cp backend/.env.example backend/.env
    echo ""
    echo -e "${YELLOW}⚠️  重要：请编辑 backend/.env 文件配置MySQL数据库信息！${NC}"
    echo "   - MYSQL_HOST（默认：localhost）"
    echo "   - MYSQL_PORT（默认：3306）"
    echo "   - MYSQL_USER（默认：root）"
    echo "   - MYSQL_PASSWORD（必须设置！）"
    echo "   - MYSQL_DATABASE（默认：qq_reports）"
    echo ""
    read -p "是否现在编辑配置文件？(y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} backend/.env
    fi
fi
echo -e "${GREEN}✅ 配置文件已存在${NC}"

# 安装Python依赖
echo ""
echo "[4/8] 安装Python依赖..."
if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "安装后端依赖包..."
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠️  使用清华源安装失败，尝试官方源...${NC}"
    pip install -r backend/requirements.txt
fi
echo -e "${GREEN}✅ Python依赖安装完成${NC}"

# 安装前端依赖
echo ""
echo "[5/8] 安装前端依赖..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖包（这可能需要几分钟）..."
    npm install
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 错误：前端依赖安装失败${NC}"
        cd ..
        exit 1
    fi
fi
cd ..
echo -e "${GREEN}✅ 前端依赖安装完成${NC}"

# 初始化数据库
echo ""
echo "[6/8] 初始化数据库..."
echo -e "${YELLOW}⚠️  请确保MySQL服务已启动！${NC}"
read -p "按Enter键继续初始化数据库，或Ctrl+C取消..."
python3 backend/init_db.py
if [ $? -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  数据库初始化失败！请检查：${NC}"
    echo "   1. MySQL服务是否已启动"
    echo "   2. backend/.env 中的数据库配置是否正确"
    echo "   3. MySQL用户是否有创建数据库的权限"
    echo ""
    read -p "是否继续启动服务？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ 数据库初始化完成${NC}"
fi

# 启动后端
echo ""
echo "[7/8] 启动后端服务..."
source venv/bin/activate
python3 backend/app.py > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid
sleep 3
echo -e "${GREEN}✅ 后端服务已启动（端口：5000，PID：$BACKEND_PID）${NC}"

# 启动前端
echo ""
echo "[8/8] 启动前端服务..."
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../.frontend.pid
cd ..
sleep 3
echo -e "${GREEN}✅ 前端服务已启动（端口：5173，PID：$FRONTEND_PID）${NC}"

echo ""
echo "========================================"
echo "🎉 启动完成！"
echo "========================================"
echo "📱 前端访问地址：http://localhost:5173"
echo "🔧 后端API地址：http://localhost:5000"
echo ""
echo "💡 提示："
echo "   - 使用 ./stop.sh 停止所有服务"
echo "   - 日志文件位于 logs/ 目录"
echo "   - 后端PID：$BACKEND_PID"
echo "   - 前端PID：$FRONTEND_PID"
echo "========================================"
echo ""

# 创建日志目录
mkdir -p logs

echo "按Ctrl+C退出（服务将在后台继续运行）"
echo "或等待10秒后自动退出..."
sleep 10
