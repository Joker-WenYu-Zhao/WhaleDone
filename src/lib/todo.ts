/* 鲸鱼待办 · 数据模型与 localStorage 存取 */

export interface Task {
  id: string
  text: string
  done: boolean
  /** 分类标签（规范化存储：trim、去重、≤TAG_MAX 个、每个 ≤TAG_NAME_MAX 字）；旧数据无此字段 */
  tags?: string[]
}

export interface TodoData {
  /** 按日期存储的待办任务，键为 YYYY-MM-DD */
  daily: Record<string, Task[]>
  /** 不绑定日期的长期事项 */
  longterm: Task[]
}

export type TabKey = 'daily' | 'longterm'
export type FilterKey = 'all' | 'pending' | 'done'

export const STORAGE_KEY = 'whale-todo-v1'

export const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待办' },
  { key: 'done', label: '已完成' },
]

/** 本地日期字符串 YYYY-MM-DD */
export function todayStr(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

export function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function createTask(text: string): Task {
  return { id: newId(), text, done: false }
}

export function emptyData(): TodoData {
  return { daily: {}, longterm: [] }
}

export function loadData(): TodoData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyData()
    const parsed = JSON.parse(raw) as Partial<TodoData>
    return {
      daily: parsed.daily && typeof parsed.daily === 'object' ? parsed.daily : {},
      longterm: Array.isArray(parsed.longterm) ? parsed.longterm : [],
    }
  } catch {
    return emptyData()
  }
}

export function saveData(data: TodoData): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // 隐私模式等存储不可用场景：静默失败，本次会话内仍可正常使用
  }
}

/** 当前 Tab 对应的任务列表 */
export function currentList(data: TodoData, tab: TabKey, date: string): Task[] {
  return tab === 'daily' ? (data.daily[date] ?? []) : data.longterm
}

/** 带所属日期的任务条目（搜索跨日期收集时使用，date 为 null 表示长期事项） */
export interface DatedTask {
  task: Task
  date: string | null
}

/** 收集全部每日待办（按日期升序，同日期内保持原始顺序） */
export function collectAllDaily(data: TodoData): DatedTask[] {
  return Object.keys(data.daily)
    .sort()
    .flatMap((date) => data.daily[date].map((task) => ({ task, date })))
}

/** 关键词过滤：忽略大小写，匹配内容或标签名；关键词空白视为不过滤 */
export function searchDatedTasks(items: DatedTask[], keyword: string): DatedTask[] {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return items
  return items.filter(
    ({ task }) =>
      task.text.toLowerCase().includes(kw) ||
      taskTags(task).some((tag) => tag.toLowerCase().includes(kw)),
  )
}

export function filterTasks(tasks: Task[], filter: FilterKey): Task[] {
  if (filter === 'pending') return tasks.filter((t) => !t.done)
  if (filter === 'done') return tasks.filter((t) => t.done)
  return tasks
}

/**
 * 把可见列表的新顺序合并回完整列表：
 * 筛选状态下隐藏的任务保持原有相对位置，可见任务作为整块插入首个可见位置。
 */
export function commitReorder(all: Task[], visible: Task[]): Task[] {
  const visibleIds = new Set(visible.map((t) => t.id))
  const result: Task[] = []
  let inserted = false
  for (const t of all) {
    if (visibleIds.has(t.id)) {
      if (!inserted) {
        result.push(...visible)
        inserted = true
      }
    } else {
      result.push(t)
    }
  }
  return result
}

/* ===== 标签系统 ===== */

/** 预置标签（候选 = 预置 ∪ 全库已有） */
export const PRESET_TAGS = ['工作', '个人', '学习']
/** 单任务标签数量上限 */
export const TAG_MAX = 3
/** 单个标签名称长度上限 */
export const TAG_NAME_MAX = 10

/** 卡通色板：按标签名哈希取色的 Tailwind 类组合（徽章与筛选 chips 共用；含暗色变体） */
export const TAG_COLORS = [
  'bg-primary/15 text-primary border-primary/40',
  'bg-accent/15 text-accent border-accent/40',
  'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-700',
  'bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-700',
  'bg-pink-100 text-pink-700 border-pink-300 dark:bg-pink-950/60 dark:text-pink-300 dark:border-pink-700',
  'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-700',
]

/** 标签规范化：trim → 截断 → 去空 → 去重 → 截断至 TAG_MAX */
export function normalizeTags(raws: string[]): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  for (const raw of raws) {
    const name = raw.trim().slice(0, TAG_NAME_MAX)
    if (!name || seen.has(name)) continue
    seen.add(name)
    tags.push(name)
    if (tags.length >= TAG_MAX) break
  }
  return tags
}

/** 读取任务标签（旧数据无 tags 字段，兜底为空数组） */
export function taskTags(task: Task): string[] {
  return task.tags ?? []
}

/** 全库收集已使用的标签（daily + longterm），按出现次数降序、名称升序 */
export function collectAllTags(data: TodoData): { name: string; count: number }[] {
  const counts = new Map<string, number>()
  const bump = (tags: string[]) => {
    for (const tag of tags) counts.set(tag, (counts.get(tag) ?? 0) + 1)
  }
  for (const list of Object.values(data.daily)) {
    for (const task of list) bump(taskTags(task))
  }
  for (const task of data.longterm) bump(taskTags(task))
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh'))
}

/** 按标签名哈希从固定色板取色（同一名永远同色，无需用户挑色） */
export function tagColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  return TAG_COLORS[hash % TAG_COLORS.length]
}

/** 标签筛选：tag 为 null 时直通（显示全部） */
export function filterByTag(items: DatedTask[], tag: string | null): DatedTask[] {
  if (!tag) return items
  return items.filter(({ task }) => taskTags(task).includes(tag))
}
