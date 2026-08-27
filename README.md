# 欢迎使用你的秒哒应用代码包
秒哒应用链接
    URL:https://www.miaoda.cn/projects/app-dzw9lby2igw1

# 鲸鱼待办 · 卡通待办事项小工具

卡通蓝色系手绘风格的待办事项小工具，支持按日期管理待办任务与长期事项，数据保存在浏览器本地（localStorage），无需后端、无需登录。

## 功能

- **待办 / 长期** 双 Tab：待办按日期绑定，长期事项不绑定日期
- **日期选择器**：默认今天，可切换任意日期，列表即时刷新
- **任务自动编号**（1. 2. 3. …），拖拽换序后自动更新
- **勾选完成 / 待办**、**删除任务**、**拖拽排序**（按住把手拖动）
- **筛选器**：全部 / 待办 / 已完成，附完成计数
- 任务过多时列表区域内部滚动，窗口大小保持固定
- 所有增删改操作实时保存到 localStorage，刷新不丢数据

## 目录说明

```
├── static/            # ★ 纯静态版（上传 GitHub Pages 用）
│   ├── index.html     # 页面结构
│   ├── styles.css     # 卡通蓝色系样式（背景图配置在文件开头）
│   ├── app.js         # 功能逻辑（localStorage + 拖拽排序）
│   ├── bg.jpg         # 鲸鱼卡通背景图（直接替换同名文件即可换背景）
│   └── whale.svg      # 网站图标
├── src/               # React 版本（Vite + TypeScript + Tailwind）
└── public/images/     # React 版背景图（whale-bg.jpg）
```

## 部署到 GitHub Pages（推荐使用 static 目录）

1. 新建一个 GitHub 仓库（例如 `whale-todo`）
2. 把 `static/` 目录里的**全部文件**（index.html、styles.css、app.js、bg.jpg、whale.svg）上传到仓库根目录
3. 仓库 Settings → Pages → Build and deployment → Source 选择 `Deploy from a branch`，分支选 `main`、目录选 `/ (root)`，保存
4. 稍等片刻，通过 `https://<用户名>.github.io/<仓库名>/` 即可访问

> 也可以直接把本仓库整体上传，然后只把 `static/` 里的文件复制到仓库根目录或 `docs/` 目录（Pages Source 选 main 分支 `/docs`）。

## 更换背景图

- **静态版**：把你的图片命名为 `bg.jpg`，放到 `static/` 目录覆盖原文件即可；配置写在 `styles.css` 开头（`--bg-image: url('bg.jpg')`）
- **React 版**：替换 `public/images/whale-bg.jpg`（引用写在 `src/index.css` 的 `body` 背景里）
- 不放图片时自动显示 CSS 绘制的海洋渐变兜底背景

## 数据说明

- 数据保存在浏览器 localStorage，按**域名**隔离：用 GitHub Pages 地址访问时，数据就存在那个域名下，安全且互不干扰
- 换浏览器 / 换设备 / 清除浏览器数据后，任务数据不会同步（本地存储特性）

## 技术栈

- 纯静态版：原生 HTML + CSS + JavaScript，零依赖，直接打开 `index.html` 也能用
- React 版：Vite、TypeScript、React、Tailwind CSS、shadcn/ui

## 本地开发

```
# Node.js ≥ 20
pnpm install
npm run lint   # 代码检查
```
