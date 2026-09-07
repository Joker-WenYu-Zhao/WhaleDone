# 欢迎使用你的秒哒应用代码包
秒哒应用链接
    URL:https://www.miaoda.cn/projects/app-dzw9lby2igw1

# 鲸鱼待办 · 卡通待办事项小工具

卡通蓝色系手绘风格的待办事项小工具，支持按日期管理待办任务与长期事项，数据保存在浏览器本地（localStorage），无需后端、无需登录。

## 功能

- **待办 / 长期** 双 Tab：待办按日期绑定，长期事项不绑定日期
- **日期选择器**：默认今天，可切换任意日期，点击日期区域任意位置即可弹出日历，列表即时刷新
- **任务自动编号**（1. 2. 3. …），拖拽换序后自动更新
- **状态切换**：点击任务右侧 ✓ / ○ 按钮在完成 / 待办间切换；完成事项显示为淡绿卡片 + 左缘绿色竖条 + 绿色划线，一眼区分
- **行内编辑**：铅笔图标进入编辑，可改内容与标签，回车保存、Esc 取消（搜索、跨日期查看下同样可用）
- **拖拽排序**：按住把手拖动（搜索、跨日期查看时自动禁用）
- **标签系统**：添加 / 编辑时可给任务打标签（预置「工作 / 个人 / 学习」，也可自建，单任务最多 3 个），同一名标签永远同色；点击标签筛选行可按标签过滤，支持「仅今天 / 全部日期」两种模式（点控件任意位置即在两档间切换）——全部日期模式下跨日期查历史，按日期倒序、同日期内已完成优先，每条显示所属日期
- **关键词搜索**：输入后回车触发，匹配任务内容或标签名，命中片段高亮
- **筛选器**：全部 / 待办 / 已完成，附完成计数
- **批量操作**：勾选多个任务（或筛选行右侧的小全选框）后，列表顶部浮现悬浮工具条——一键迁移到指定日期（长期事项也可迁入某一天转为当日待办，迁移后原位置不再保留）或批量删除（带二次确认弹窗）；搜索、跨日期模式下同样可用
- **导入 / 导出**：CSV 备份与恢复（Excel 打开不乱码）；导出全量数据，导入前自动下载现有数据备份并需二次确认
- **暗色主题**：页头太阳 / 月亮按钮一键切换浅色 / 深色，选择自动记忆，刷新不闪屏
- 任务过多时列表区域内部滚动，窗口大小保持固定
- 所有增删改操作实时保存到 localStorage，刷新不丢数据

## 目录说明

```
├── src/               # ★ React 版主代码（Vite + TypeScript + Tailwind，当前主用版本）
├── public/images/     # 背景图等静态资源（whale-bg.jpg）
├── .github/workflows/ # GitHub Actions 自动部署工作流（deploy.yml）
└── static/            # 早期纯静态版（已停用，仅留档）
```

## 部署（GitHub Actions 自动部署）

当前采用 React 版自动部署：**推送到 `master` 分支即自动构建并发布**，无需手动上传文件。

1. 工作流 `.github/workflows/deploy.yml`：Node 22 环境执行 `npm install` + `npm run build`，产物 `dist/` 通过 `actions/deploy-pages` 发布
2. 部署完成后访问：`https://joker-wenyu-zhao.github.io/WhaleDone/`
3. 也支持在仓库 Actions 页面手动触发（`workflow_dispatch`）

> 注意：`vite.config.ts` 的 `base: '/WhaleDone/'` 与 `App.tsx` 路由的 `basename`（取自 `import.meta.env.BASE_URL`）联动，决定线上资源路径与路由匹配。**若更改仓库名，需同步修改 vite 的 base 配置**，否则会出现资源 404 或地址被重定向的问题。

## 更换背景图

- **React 版（主用）**：替换 `public/images/whale-bg.jpg`（引用写在 `src/index.css` 的 `body` 背景里，暗色主题的遮罩透明度也在这里调节）
- **静态版（留档）**：把图片命名为 `bg.jpg` 放到 `static/` 目录覆盖原文件；配置写在 `styles.css` 开头（`--bg-image: url('bg.jpg')`）
- 不放图片时自动显示 CSS 绘制的海洋渐变兜底背景

## 数据说明

- 数据保存在浏览器 localStorage，按**域名**隔离：用 GitHub Pages 地址访问时，数据就存在那个域名下，安全且互不干扰
- 换浏览器 / 换设备 / 清除浏览器数据后，任务数据不会同步（本地存储特性）

## 技术栈

- **React 版（主用）**：Vite 8、TypeScript、React、Tailwind CSS、shadcn/ui、react-router-dom、motion（拖拽动画）、next-themes（主题）、sonner（Toast 提示）
- 纯静态版（`static/`，已停用留档）：原生 HTML + CSS + JavaScript，零依赖

## 本地开发

### 环境要求

- **Node.js ≥ 20**（项目使用 Vite 8，不支持 Node 14/16）
- 如已安装 nvm，切换版本：`nvm use 22.23.2`

### 首次安装

```bash
# 绕过 PowerShell 执行策略（仅当前窗口生效）
Set-ExecutionPolicy -Scope Process Bypass -Force

# 安装依赖
npm install
```

### 快捷启动（PowerShell 命令 whale，推荐）

已在本机 PowerShell 配置（`C:\Users\admin\Documents\WindowsPowerShell\profile.ps1`）中注册了 `whale` 函数，新开终端直接输入：

```powershell
whale
```

等价于「进入项目目录 + 启动开发服务器」，无需再手动 cd 或绕执行策略。

> 首次配置的完整步骤（其它机器参考）：执行策略改为 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force`（一次性，允许本地脚本运行）；然后在上述 profile.ps1 里添加：
>
> ```powershell
> function whale {
>     Set-Location "<项目目录>"
>     npm run dev
> }
> ```

### 启动开发服务器

```bash
npm run dev
```

启动后访问 `http://localhost:5173/WhaleDone/` 即可预览（已配置 base 路径）。

### 代码检查

```bash
npm run lint
```

### 构建生产版本

```bash
npm run build
```
