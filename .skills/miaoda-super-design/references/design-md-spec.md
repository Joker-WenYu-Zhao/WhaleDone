# DESIGN.md 规范

## 生命周期（何时生成、何时维护）

- **只在「选中 html 生成应用」时（P4）generate**：落盘 `/workspace/{app_id}/docs/DESIGN.md`。**HTML 设计阶段（P1/P2/P3）绝不生成、绝不维护——此阶段唯一事实源是 html 本身。**
- **生成之后，任何设计变更必须同轮维护**：改应用视觉、新 tab 页稿选中转换、某页重设计——同轮更新对应 token/prose。
- **用户上传品牌 design spec 是最高优先输入**：已是本模板格式 → 校验后直接落盘采用；其他形式 → 走 `asset-direction.md §0` 提取规范化，向用户确认后落盘。
- **多选生成时**：tokens 取首页 route 的选中稿；其余选中页在同一 token 体系下转换，冲突以首页为准并向用户说明。

## 模板骨架

front matter 分两段来源：**上半段模型手写，下半段脚本原样粘贴**。

```md
---
# ── 以下 3 项模型手写 ──
name: <stamp title>              # 与 manifest title 一致
source_draft: 4                   # 生成来源的设计稿 id
fonts:                            # 取自选中稿 FONT-FACE 块的 @font-face，来源 search_fonts.py
  heading: "Noto Serif SC"
  body: "Inter"

# ── 以下整块 = apply_design_tokens.py --emit-designmd-tokens 的 stdout，原样粘贴 ──
tokens:                           # key = index.css 变量名；value = HSL 裸三元组
  radius: "0.5rem"
  background: "0 0% 100%"
  foreground: "222 47% 11%"
  primary: "221 83% 45%"
  primary-foreground: "0 0% 100%"
  # ……仅设计决策核心集（≈18 个）；未列出的 = 规则推导或铺底默认，不复读
  # 稿件含 .dark {} 分支时脚本会追加 dark-<name> 前缀键（如 dark-background）
custom_tokens:                    # 该设计注册的自定义 token；无则脚本不输出此段
  brand-gold: "43 96% 56%"
section_blueprint:                # key = section 的 id，value = 根元素必需 class
  hero: "bg-background text-foreground"
  menu: "bg-foreground text-primary-foreground border-b-2 border-foreground"
  # ……编码时 React <section> 根元素 className 必须包含这些 class，缺 = 视觉基线丢失
---

## Overview        # 气质定位 + signature element（1 段，说 why）
## Colors          # 60-30-10 分布用法、主色使用边界、暗色策略
## Typography      # 字体（可用字体库 data/fonts.csv 内的款 + @font-face BOS URL）、字阶（5 级内）、字重、行高约定
## Layout          # 栅格/间距节奏、断点（只有 md）、导航模式
## Components      # ≤8 个关键组件的 token 用法（button-primary / card / input…含 hover 态）
## Do's and Don'ts # 本设计系统的禁忌（如禁渐变文字、每 section 一处 bg-primary）
```

脚本输出的 `tokens` / `custom_tokens` / `section_blueprint` 是连续 stdout，整块贴在 front matter 末尾即可，不要把手写字段插进中间。

## 硬规则

1. **tokens / custom_tokens / section_blueprint 段由脚本生成**：`python3 <skill_dir>/scripts/apply_design_tokens.py --emit-designmd-tokens --html tasks/design/<选中稿>.html` 的 stdout 整块粘入 front matter——三者出自同一次解析，一致性由构造保证。**禁止手抄这三段**。
2. **name / source_draft / fonts 三项模型手写**：不走脚本。
   - `name` 与 manifest title 一致
   - `source_draft` 记来源稿 id，可追溯
   - `fonts.heading` / `fonts.body` 从选中稿 FONT-FACE 块的 `@font-face` 里抽 family 名；字体必须来自 `data/fonts.csv`，由 `search_fonts.py` 检索
3. **章节固定顺序，可省略不可乱序**：Overview → Colors → Typography → Layout → Components → Do's and Don'ts。
4. **prose 讲 why 不复读值**：token 值在 front matter，正文写用法边界与理由。**每条 prose 都必须在写 React 时被消费**——写不出如何被消费 = 删。
5. **section_blueprint 是编码期强约束**：React 各 section 组件的根元素`<section id="X" className="...">` 必须保留 `id`（同时是 nav 锚点目标）且 className **包含** blueprint[X] 列出的全部 class（可以叠加更多，但不能缺）。这是 HTML→React 迁移时防 section 顶层视觉类丢失、防 nav 锚点丢失的关键契约。
6. 写完/改完自查：`python3 <skill_dir>/scripts/check_design_md.py docs/DESIGN.md --index-css src/index.css --src src/`——校验 front matter 与 index.css 逐变量一致、HSL 合法、章节顺序、AA 对比度、`section_blueprint` 与 React 代码一致。

## 与编码期规则的衔接

编码期 system prompt 规定「DESIGN.md is the single source of truth」并强制语义token 类——本模板的 front matter 就是那个 truth 的机器可读层：改设计 = 改 front matter token（经脚本）+ 改 prose 边界，代码只消费 `bg-primary` 等语义类，永不感知具体 HSL 值。**section_blueprint 把 section 根元素的类契约同样机器化**——写每个 section 组件时直接读 blueprint[X]，避免"看着 HTML 手抄"漏 class。
