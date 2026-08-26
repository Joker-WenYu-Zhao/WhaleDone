# 选中转换与生成后设计（P4 / P5）

> **何时读**：P4 = 用户选中稿后生成应用；P5 = 应用生成后追加/重设计页面。

---

## §P4 选中转应用

**唯一前置硬门**：用户在三稿展示之后的**新一轮消息**里明确选定了某稿（产品侧 selectDesign 事件，或口头点名稿号/标题）。

- 这个信号来自**用户主动发的下一条消息**，不是本 skill 去问出来的。
- **禁 `ask_user` 追问"选哪稿"**——三稿交付后正常 finish 即止；用户不点名就永久停在三稿，不进 P4。只交付设计稿不生成应用是合规终态。
- **禁自行代选**——用户跳过、沉默、说"你决定"都不构成选稿授权（问卷的跳过只授权 vibe 决策，不授权替用户选稿转应用）。

有该信号后执行以下步骤。

### 1. 先生成 DESIGN.md

```bash
python3 <skill_dir>/scripts/apply_design_tokens.py --emit-designmd-tokens --html tasks/design/<选中稿>.html
```

- 脚本输出（`tokens` / `custom_tokens` / `fonts` / `section_blueprint` 四段）整体粘入 `/workspace/{app_id}/docs/DESIGN.md` 的 front matter。
- prose 从设计决策提炼——讲 why、讲边界，不复读值。**每条 prose 都要在写 React时被消费**（写不出如何被消费的条目 = 删，不为写而写）。
- 格式严格按 `design-md-spec.md`。
- 品牌 spec 存在时（`tasks/design/brand-spec.md`）作品牌事实输入。

### 2. token 注入必须跑脚本

```bash
python3 <skill_dir>/scripts/apply_design_tokens.py --html tasks/design/<选中稿>.html \
  --index-css src/index.css --tailwind-config tailwind.config.js
```

- 按铺底 schema 全量重建 token 区块 + 自定义 token 注入 + tailwind.config 扩展。
- **禁止手抄 token 进 index.css**。
- 脚本硬失败 → 停止转换、向用户说明，回 P3 补可用稿；绝不手抄兜底。

### 3. sig-CSS、字体与动效迁移

- `SIGNATURE-CSS` 块内的 `sig-` 类由模型拷到应用代码（属创作产物）。
- `@font-face` 的 BOS URL 一并拷贝（可用字体见 `data/fonts.csv`）。
- **CSS 动效**：选中稿 `KEYFRAMES` / `ANIMATIONS` 块的内容拷进 `tailwind.config.js` 的 `theme.extend.keyframes` / `theme.extend.animation`（同名同结构，直接搬）。
  - `intersect:` 变体与 `intersect-once` 在应用侧原生可用（`tailwindcss-intersect` 已在依赖内、`<IntersectObserver/>` 已在 `App.tsx` 挂载），JSX 里类名 1:1 照抄即可。
- **motion 动效**：`MOTION-SCRIPT` 块（预览时用 `inView`/`scroll`/`stagger` 的命令式调用）**不迁移**，改用 `motion/react` 声明式**重写**——`motion@12.23.25` 已在依赖内。这一步靠理解语义重写、不是逐行搬：
  - `animate(el, {opacity:[0,1], y:[40,0]}, {duration})` → `<motion.div initial={{opacity:0,y:40}} whileInView={{opacity:1,y:0}} viewport={{once:true, margin}} transition={{duration}}>`
  - `inView(el, cb, {margin})` 的 margin → `viewport={{margin}}`；`stagger` → 父 `transition={{staggerChildren}}` + 子 `variants`
  - scroll 联动进度 → `useScroll()` + `useTransform()`
- body 末尾三段 `data-preview-only` 脚本（intersect observer / motion import / MOTION-SCRIPT）**都是预览专用，全部不迁移**。
- 自行引入的其他 CDN 动效库（Swiper / lottie 等）要迁成 npm 依赖。

### 3.5 section 组件根元素契约（写代码时读 DESIGN.md）

DESIGN.md front matter 的 `section_blueprint` 是每个 section 根元素的 class契约（由脚本从选中 html 提取，禁手抄）。写每个 section 组件时：

- 根元素**必须**是 `<section>`，并保留 `id="X"`（与 blueprint 的 key 对应）——它既是 nav `href="#X"` 的锚点目标，也是脚本识别 section 的依据。丢了 → 单页 nav 全失效跳页顶。
- 根元素 `className` **必须包含** `section_blueprint[X]` 列出的全部 class；可以叠加更多（响应式变体/hover 态），但不能缺。
- 这是编码时的**输入约束**，不是转换完了再挑错——写 `HeroSection.tsx` 前先读 blueprint.hero，直接写到根 `<section>` 上，杜绝"看 HTML 手抄漏 class"。

**首页视觉组件写完先跑一次 §6 check_design_md.py，别等全部业务页面写完才第一次跑**——此时改动范围小，报错好定位；业务页面写完后再跑一次完整校验收尾。

### 4. 资产迁移

| 场景 | 处理 |
|---|---|
| 远程 https URL | 原样沿用，不下载 |
| 本地 `tasks/design/assets/` 图片 | 全拷到 `public/images/design/`（同名） |
| React 代码引用路径 | `/images/design/<name>` |
| 路径 rewrite | html 里的 `/workspace/<app-id>/tasks/design/assets/x.jpg` → React 里的 `/images/design/x.jpg` |
| DESIGN.md 资产表 | 登记 `/images/design/<name>` 与远程 URL |

- **`tasks/design/` 不打包，React 代码禁引用其下任何文件。**

### 5. 双基准

- **视觉基准 = 选中 HTML**：像素级还原；禁加原型没有的视觉元素。
- **功能基准 = PRD**：验收点一个不少。
  - 稿没画的功能在 DESIGN.md token 体系内延展设计，不得砍功能。

### 6. 转换后自查

```bash
python3 <skill_dir>/scripts/check_design_md.py docs/DESIGN.md \
  --index-css src/index.css --src src/
```

- 逐 `id` 对照设计稿源码，核对结构 / token / 文案。
- `--src` 校验 `section_blueprint`：每个 section 组件根元素的 className 是否覆盖 blueprint 列出的全部 class。报 warn = section 顶层视觉类丢失（背景/文字/边框），**视为必须修**（除非有意重设计且已同步更新 DESIGN.md）。

---

## §P5 生成后设计（应用已生成）

### 1. 必须先读现有体系

- 读 `docs/DESIGN.md` + `src/index.css`，新稿 token 与组件风格从中派生。
- **一致性硬约束**：不引入 DESIGN.md 之外的新主色/新字体。
  - 除非用户明确要求换风格（属重设计，转换时须同步更新 DESIGN.md）。

### 2. route 由文件名承载

- 命名 `tasks/design/{route-name}-{n}.html`（如 `/profile` 页 → `profile-1.html`），不另行申报。

### 3. 素材优先复用

- 优先复用应用内已有素材（`public/images/design/`）+ 已选中稿素材。
- 应用内图片在新稿中复用时：同名拷到 `tasks/design/assets/`，html 里以完整绝对路径 `/workspace/<app-id>/tasks/design/assets/<name>` 引用。
- 转换时按同名幂等迁回，不产生重复文件。

### 4. 同 P3 纪律

- 每稿新建文件（不覆盖旧稿）；stamp 写 title + skeleton + sig；交付前跑自检脚本。
- **每轮仅交付 1 稿**，交付后结束本轮并询问是否继续。

### 5. 设计变更必须同轮维护 DESIGN.md

- 无论改动来自设计侧还是应用侧，同一轮对话内更新对应 tokens / prose。

### 6. 交付形式

- 设计方案一律以 `tasks/design/{route-name}-{n}.html` 新稿交付。
- **禁止直接改应用代码来"呈现方案"**（如把多方案塞进同一 React 页面切换）。
- 改应用代码只发生在：P4 选中转换，或用户明确要求修 bug / 改功能时。
