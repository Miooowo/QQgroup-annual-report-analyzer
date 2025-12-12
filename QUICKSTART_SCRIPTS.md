# 一键启动脚本使用指南

本项目提供了一键启动脚本，可以自动部署环境并启动前后端服务。

## 📋 前置要求

在使用启动脚本之前，请确保已安装以下软件：

1. **Python 3.8+**
   - Windows: 从 [python.org](https://www.python.org/downloads/) 下载安装
   - Mac: `brew install python3`
   - Linux: `sudo apt install python3 python3-venv python3-pip`

2. **Node.js 16+**
   - 从 [nodejs.org](https://nodejs.org/) 下载安装
   - 或使用 nvm 等版本管理工具

3. **MySQL 5.7+ / 8.0+**
   - Windows: 从 [mysql.com](https://dev.mysql.com/downloads/mysql/) 下载安装
   - Mac: `brew install mysql`
   - Linux: `sudo apt install mysql-server`

4. **确保MySQL服务已启动**
   - Windows: 在服务管理器中启动 MySQL 服务
   - Mac: `brew services start mysql`
   - Linux: `sudo systemctl start mysql`

## 🚀 使用方法

### Windows 系统

1. **双击运行启动脚本**
   ```
   start.bat
   ```

2. **首次运行时**
   - 脚本会自动创建 `backend/.env` 配置文件
   - 根据提示编辑数据库配置（特别是 `MYSQL_PASSWORD`）
   - 脚本会自动安装所有依赖
   - 脚本会自动初始化数据库

3. **服务启动后**
   - 会自动打开两个命令行窗口（前端和后端）
   - 前端访问地址：http://localhost:5173
   - 后端API地址：http://localhost:5000

4. **停止服务**
   - 直接关闭两个命令行窗口即可

### Linux / Mac 系统

1. **添加执行权限（仅首次需要）**
   ```bash
   chmod +x start.sh stop.sh
   ```

2. **运行启动脚本**
   ```bash
   ./start.sh
   ```

3. **首次运行时**
   - 脚本会自动创建 `backend/.env` 配置文件
   - 根据提示编辑数据库配置（特别是 `MYSQL_PASSWORD`）
   - 脚本会自动安装所有依赖
   - 脚本会自动初始化数据库

4. **服务启动后**
   - 服务将在后台运行
   - 前端访问地址：http://localhost:5173
   - 后端API地址：http://localhost:5000
   - 日志文件保存在 `logs/` 目录

5. **停止服务**
   ```bash
   ./stop.sh
   ```

## ⚙️ 配置说明

### 必需配置（backend/.env）

在首次运行时，脚本会自动创建 `backend/.env` 文件，你需要编辑以下关键配置：

```env
# MySQL 数据库配置（必需）
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password    # ⚠️ 必须修改！
MYSQL_DATABASE=qq_reports
```

### 可选配置

```env
# OpenAI API（用于AI锐评功能，可选）
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# Flask 配置
FLASK_SECRET_KEY=your_secret_key
FLASK_PORT=5000
DEBUG=false

# CORS 配置
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5000
```

## 📝 启动流程说明

启动脚本会自动执行以下步骤：

1. ✅ 检查 Python 环境
2. ✅ 检查 Node.js 环境
3. ✅ 检查/创建配置文件（backend/.env）
4. ✅ 创建虚拟环境并安装 Python 依赖
5. ✅ 安装前端依赖（npm packages）
6. ✅ 初始化 MySQL 数据库
7. ✅ 启动后端服务（Flask，端口5000）
8. ✅ 启动前端服务（Vite，端口5173）

## 🔍 故障排查

### 问题1：数据库连接失败

**错误信息：** "数据库初始化失败"

**解决方案：**
1. 确认 MySQL 服务已启动
2. 检查 `backend/.env` 中的数据库配置
3. 确认 MySQL 用户有创建数据库的权限
4. 尝试手动连接测试：
   ```bash
   mysql -u root -p
   ```

### 问题2：端口已被占用

**错误信息：** "Address already in use"

**解决方案：**
1. 检查端口5000和5173是否被占用
   - Windows: `netstat -ano | findstr :5000`
   - Linux/Mac: `lsof -i :5000`
2. 停止占用端口的进程或更改配置端口

### 问题3：Python依赖安装失败

**解决方案：**
1. 确认网络连接正常
2. 尝试使用官方源：
   ```bash
   pip install -r backend/requirements.txt
   ```
3. 或手动安装：
   ```bash
   pip install flask flask-cors pymysql python-dotenv
   ```

### 问题4：前端依赖安装失败

**解决方案：**
1. 清理缓存：
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   ```
2. 使用国内镜像：
   ```bash
   npm install --registry=https://registry.npmmirror.com
   ```

## 📁 生成的文件/目录

运行脚本后会生成以下文件和目录：

```
项目根目录/
├── venv/                    # Python虚拟环境
├── frontend/node_modules/   # 前端依赖
├── logs/                    # 日志文件（仅Linux/Mac）
├── .backend.pid             # 后端进程ID（仅Linux/Mac）
├── .frontend.pid            # 前端进程ID（仅Linux/Mac）
└── backend/.env             # 后端配置文件
```

这些文件已添加到 `.gitignore`，不会被提交到Git仓库。

## 🎯 快速测试

启动成功后，可以通过以下方式测试：

1. **访问前端**
   - 打开浏览器访问：http://localhost:5173
   - 应该能看到上传界面

2. **测试后端API**
   ```bash
   curl http://localhost:5000/api/health
   ```
   应该返回：
   ```json
   {"ok": true, "services": {"database": true}}
   ```

## 💡 使用建议

1. **首次使用**
   - 建议先配置好 `backend/.env` 文件
   - 确保 MySQL 服务正常运行
   - 如需使用 AI 功能，配置 OpenAI API Key

2. **日常使用**
   - Windows：直接双击 `start.bat`
   - Linux/Mac：执行 `./start.sh`

3. **开发调试**
   - 查看日志：`logs/backend.log` 和 `logs/frontend.log`
   - 前端热重载：修改代码后自动刷新
   - 后端需要手动重启以应用更改

## 📞 获取帮助

如果遇到问题：
1. 查看本文档的故障排查部分
2. 查看项目的 README.md 和 DEPLOYMENT.md
3. 在 GitHub 提交 Issue
