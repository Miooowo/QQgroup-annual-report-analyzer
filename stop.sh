#!/bin/bash

echo "========================================"
echo "QQ群年度报告分析器 - 停止脚本"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 停止后端
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    echo "停止后端服务 (PID: $BACKEND_PID)..."
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID
        echo -e "${GREEN}✅ 后端服务已停止${NC}"
    else
        echo -e "${YELLOW}⚠️  后端服务未运行${NC}"
    fi
    rm .backend.pid
else
    echo -e "${YELLOW}⚠️  未找到后端PID文件${NC}"
fi

# 停止前端
if [ -f ".frontend.pid" ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    echo "停止前端服务 (PID: $FRONTEND_PID)..."
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID
        echo -e "${GREEN}✅ 前端服务已停止${NC}"
    else
        echo -e "${YELLOW}⚠️  前端服务未运行${NC}"
    fi
    rm .frontend.pid
else
    echo -e "${YELLOW}⚠️  未找到前端PID文件${NC}"
fi

# 额外检查：杀死可能残留的进程
echo ""
echo "检查并清理可能残留的进程..."

# 查找并杀死Python后端进程
PYTHON_PIDS=$(pgrep -f "python.*backend/app.py")
if [ ! -z "$PYTHON_PIDS" ]; then
    echo "发现残留的后端进程: $PYTHON_PIDS"
    kill $PYTHON_PIDS 2>/dev/null
    echo -e "${GREEN}✅ 已清理残留后端进程${NC}"
fi

# 查找并杀死npm/vite进程
VITE_PIDS=$(pgrep -f "vite")
if [ ! -z "$VITE_PIDS" ]; then
    echo "发现残留的前端进程: $VITE_PIDS"
    kill $VITE_PIDS 2>/dev/null
    echo -e "${GREEN}✅ 已清理残留前端进程${NC}"
fi

echo ""
echo "========================================"
echo -e "${GREEN}🎉 所有服务已停止！${NC}"
echo "========================================"
