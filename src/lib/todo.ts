/* 鲸鱼待办 · 数据模型与 localStorage 存取 */

export interface Task {
  id: string
  text: string
  done: boolean
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
