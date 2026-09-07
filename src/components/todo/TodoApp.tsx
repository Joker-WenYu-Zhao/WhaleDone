import { Download, Moon, MoveRight, Plus, Sun, Tag, Trash2, Upload, X } from 'lucide-react'
import { AnimatePresence, motion, Reorder } from 'motion/react'
import { useTheme } from 'next-themes'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import PageMeta from '@/components/common/PageMeta'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  buildBackupFilename,
  csvToTodo,
  downloadTextFile,
  parseCsv,
  todoToCsv,
} from '@/lib/backup'
import type { DatedTask, FilterKey, TabKey, Task, TodoData } from '@/lib/todo'
import {
  collectAllDaily,
  collectAllTags,
  commitReorder,
  createTask,
  currentList,
  FILTERS,
  filterByTag,
  filterTasks,
  loadData,
  migrateTasks,
  normalizeTags,
  PRESET_TAGS,
  removeTasks,
  saveData,
  searchDatedTasks,
  tagColor,
  todayStr,
} from '@/lib/todo'
import TagPicker from './TagPicker'
import TaskItem from './TaskItem'
import WhaleMark from './WhaleMark'

export default function TodoApp() {
  const [data, setData] = useState<TodoData>(loadData)
  const [tab, setTab] = useState<TabKey>('daily')
  const [date, setDate] = useState<string>(todayStr())
  const [filter, setFilter] = useState<FilterKey>('all')
  const [input, setInput] = useState('')
  const [shake, setShake] = useState(false)
  // 搜索：输入值（打字不过滤）与已提交关键词（回车才生效）分离
  const [searchInput, setSearchInput] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const dateRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  // 导入：校验通过的待导入数据，非 null 时弹二次确认框
  const [pendingImport, setPendingImport] = useState<TodoData | null>(null)
  // 标签：筛选条选中项（null = 不过滤）与添加栏草稿标签
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [draftTags, setDraftTags] = useState<string[]>([])
  // 批量迁移：选中任务 id 集合与目标日期弹窗（单步确认）
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [migrateOpen, setMigrateOpen] = useState(false)
  const [migrateDate, setMigrateDate] = useState(todayStr())
  // 批量删除二次确认弹窗（风险操作，与迁移弹窗同风格）
  const [deleteOpen, setDeleteOpen] = useState(false)
  // 标签筛选作用域：仅今天（当前日期 ∩ 标签）/ 全部日期（跨日期历史查询）
  const [tagScope, setTagScope] = useState<'today' | 'all'>('today')
  // 主题：二态切换（浅色/深色），next-themes 负责持久化与 <html> 类名
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  // 任何数据变化都实时保存
  useEffect(() => {
    saveData(data)
  }, [data])

  // 列表上下文变化（切日期/Tab、状态筛选、标签筛选、搜索）时清空批量选择；取消标签后作用域回归「仅今天」并置灰
  useEffect(() => {
    setSelectedIds([])
    if (!activeTag) setTagScope('today')
  }, [tab, date, activeTag, filter, searchKeyword, tagScope])

  // 添加框高度随内容自适应（上限 120px，超出内部滚动）
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [input])

  const tasks = currentList(data, tab, date)
  const doneCount = tasks.filter((t) => t.done).length
  const isToday = date === todayStr()
  const isSearchMode = searchKeyword.trim() !== ''
  /** 标签历史模式：每日 Tab + 非搜索 + 作用域「全部日期」+ 已选标签时，跨全部日期查该标签的每日待办 */
  const isTagHistory = tab === 'daily' && !isSearchMode && tagScope === 'all' && activeTag !== null

  /** 全库已使用的标签（筛选条数据源）与候选标签（预置 ∪ 全库，选择器数据源） */
  const usedTags = useMemo(() => collectAllTags(data), [data])
  const tagCandidates = useMemo(
    () => [...new Set([...PRESET_TAGS, ...usedTags.map(({ name }) => name)])],
    [usedTags],
  )

  /**
   * 列表渲染项：关键词 / 状态 / 标签三层条件取交集。
   * 非搜索模式数据源为当前日期列表；搜索模式为全 Tab 范围内的命中结果。
   */
  const listItems = useMemo<DatedTask[]>(() => {
    let source: DatedTask[]
    if (isSearchMode) {
      const all =
        tab === 'daily'
          ? collectAllDaily(data)
          : data.longterm.map((task) => ({ task, date: null as string | null }))
      source = searchDatedTasks(all, searchKeyword)
    } else if (isTagHistory) {
      // 标签历史模式：跨全部日期收集每日待办，按日期倒序、同日期内已完成优先；标签过滤由末尾 filterByTag 统一处理
      source = collectAllDaily(data).sort((a, b) => {
        if (a.date !== b.date) return (b.date ?? '').localeCompare(a.date ?? '')
        return Number(b.task.done) - Number(a.task.done)
      })
    } else {
      source = tasks.map((task) => ({ task, date: null }))
    }
    const filtered =
      filter === 'pending'
        ? source.filter(({ task }) => !task.done)
        : filter === 'done'
          ? source.filter(({ task }) => task.done)
          : source
    return filterByTag(filtered, activeTag)
  }, [isSearchMode, isTagHistory, tasks, tab, data, searchKeyword, filter, activeTag])

  // 列表内容变化后剔除已不存在的选中项（如手动删除了选中的任务）
  useEffect(() => {
    setSelectedIds((prev) => {
      const ids = new Set(listItems.map(({ task }) => task.id))
      const next = prev.filter((id) => ids.has(id))
      return next.length === prev.length ? prev : next
    })
  }, [listItems])

  /** 清空搜索：恢复按当前 Tab + 状态筛选的正常查询，不抢焦点 */
  const resetSearch = () => {
    setSearchInput('')
    setSearchKeyword('')
  }

  /** 切换大 Tab：一切查询条件回归默认（搜索/标签/作用域/状态筛选），日期选择保留不动 */
  const handleTabChange = (next: string) => {
    setTab(next as TabKey)
    setSearchInput('')
    setSearchKeyword('')
    setActiveTag(null)
    setTagScope('today')
    setFilter('all')
  }

  /** 回车提交搜索：把输入框当前值作为生效关键词 */
  const submitSearch = () => {
    setSearchKeyword(searchInput)
  }

  /** 更新当前 Tab 对应的列表（待办按日期、长期为独立列表） */
  const updateList = (updater: (list: Task[]) => Task[]) => {
    setData((prev) => {
      if (tab === 'daily') {
        const list = prev.daily[date] ?? []
        return { ...prev, daily: { ...prev.daily, [date]: updater(list) } }
      }
      return { ...prev, longterm: updater(prev.longterm) }
    })
  }

  const triggerShake = () => {
    setShake(true)
    window.setTimeout(() => setShake(false), 420)
    inputRef.current?.focus()
  }

  const addTask = () => {
    const text = input.trim()
    if (!text) {
      triggerShake()
      return
    }
    updateList((list) => [
      ...list,
      { ...createTask(text), ...(draftTags.length > 0 ? { tags: draftTags } : {}) },
    ])
    setInput('')
    setDraftTags([])
    inputRef.current?.focus()
  }

  const toggleTask = (id: string) => {
    // 搜索 / 标签历史模式下列表跨日期展示，必须全库按 ID 定位，否则非当天事项操作无效
    if (isSearchMode || isTagHistory) {
      mutateTaskById(id, (t) => ({ ...t, done: !t.done }))
      return
    }
    updateList((list) => list.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
  }

  const deleteTask = (id: string) => {
    if (isSearchMode || isTagHistory) {
      removeTaskById(id)
      return
    }
    updateList((list) => list.filter((t) => t.id !== id))
  }

  /** 编辑保存：tags 可选，undefined 保持原标签，数组（含空）覆盖（normalizeTags 负责规范化） */
  const editTask = (id: string, text: string, tags?: string[]) => {
    const applyTags = (t: Task): Task => ({
      ...t,
      text,
      ...(tags === undefined ? {} : { tags: normalizeTags(tags) }),
    })
    if (isSearchMode || isTagHistory) {
      mutateTaskById(id, applyTags)
      return
    }
    updateList((list) => list.map((t) => (t.id === id ? applyTags(t) : t)))
  }

  /** 按 id 在全量数据中修改任务（搜索 / 标签历史模式下命中项可能来自其他日期） */
  const mutateTaskById = (id: string, mutate: (t: Task) => Task) => {
    setData((prev) => {
      for (const key of Object.keys(prev.daily)) {
        if (prev.daily[key].some((t) => t.id === id)) {
          return {
            ...prev,
            daily: { ...prev.daily, [key]: prev.daily[key].map((t) => (t.id === id ? mutate(t) : t)) },
          }
        }
      }
      return { ...prev, longterm: prev.longterm.map((t) => (t.id === id ? mutate(t) : t)) }
    })
  }

  /** 按 id 在全量数据中删除任务 */
  const removeTaskById = (id: string) => {
    setData((prev) => {
      const daily = { ...prev.daily }
      for (const key of Object.keys(daily)) {
        if (daily[key].some((t) => t.id === id)) {
          daily[key] = daily[key].filter((t) => t.id !== id)
          return { ...prev, daily }
        }
      }
      return { ...prev, longterm: prev.longterm.filter((t) => t.id !== id) }
    })
  }

  /* ===== 批量迁移 ===== */

  /** 批量选择全模式开放（迁移/删除按任务 ID 全库操作，与视图无关）；跨日期视图仅禁拖拽 */
  const batchEnabled = true
  /** 全选 = 当前可见列表全部命中选中集合（派生，不单独存状态） */
  const allSelected =
    batchEnabled && listItems.length > 0 && listItems.every(({ task }) => selectedIds.includes(task.id))

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  /** 全选/取消全选当前列表（仅作用于当前筛选条件下的可见项） */
  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? [] : listItems.map(({ task }) => task.id))
  }

  /** 打开迁移弹窗：目标日期每次重置为今天 */
  const openMigrate = () => {
    setMigrateDate(todayStr())
    setMigrateOpen(true)
  }

  /** 执行迁移：写回数据、清空选中、Toast 反馈（长期事项迁入日期即转为当日待办） */
  const confirmMigrate = () => {
    const count = selectedIds.length
    setData((prev) => migrateTasks(prev, selectedIds, migrateDate))
    setSelectedIds([])
    setMigrateOpen(false)
    toast.success(`已成功迁移 ${count} 项待办至 ${migrateDate}`)
  }

  /** 打开批量删除确认弹窗（破坏性操作，二次确认后执行） */
  const openBatchDelete = () => {
    setDeleteOpen(true)
  }

  /** 执行批量删除：写回数据、清空选中、关弹窗、Toast 反馈 */
  const confirmBatchDelete = () => {
    const count = selectedIds.length
    setData((prev) => removeTasks(prev, selectedIds))
    setSelectedIds([])
    setDeleteOpen(false)
    toast.success(`已删除 ${count} 项待办`)
  }

  /** 点击日期输入框任意位置都弹出日历（showPicker 不支持时静默降级为原生交互） */
  const openDatePicker = () => {
    try {
      dateRef.current?.showPicker()
    } catch {
      // 部分浏览器在非用户手势或不支持时抛错，忽略即可
    }
  }

  /** 导出：内存数据转 CSV 下载（无破坏性，空数据仍导出仅表头文件） */
  const handleExport = () => {
    downloadTextFile(buildBackupFilename('鲸鱼待办备份'), todoToCsv(data))
    const hasData = Object.keys(data.daily).length > 0 || data.longterm.length > 0
    if (hasData) {
      toast.success('导出成功，文件已保存到下载目录')
    } else {
      toast.info('当前没有数据，已导出仅含表头的空文件')
    }
  }

  /** 导入：选文件 → 解析校验 → 全部通过后自动备份现有数据 → 弹二次确认 */
  const handleImportFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const imported = csvToTodo(parseCsv(String(reader.result)))
        // 解析与校验全部通过才备份现有数据（解析阶段失败时现有数据零风险）
        downloadTextFile(buildBackupFilename('待办事项备份数据'), todoToCsv(data))
        setPendingImport(imported)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '文件内容无法识别，请检查是否为本工具导出的 CSV')
      }
    }
    reader.onerror = () => toast.error('文件读取失败，请重试')
    reader.readAsText(file, 'utf-8')
  }

  /** 确认导入：覆盖写入（localStorage 由现有 useEffect 自动同步） */
  const confirmImport = () => {
    if (!pendingImport) return
    const count =
      Object.values(pendingImport.daily).reduce((n, list) => n + list.length, 0) +
      pendingImport.longterm.length
    setData(pendingImport)
    setPendingImport(null)
    toast.success(`导入成功，共 ${count} 条事项`)
  }

  /** 待导入数据条数（确认弹窗文案用） */
  const pendingImportCount = pendingImport
    ? Object.values(pendingImport.daily).reduce((n, list) => n + list.length, 0) +
      pendingImport.longterm.length
    : 0

  /* 空状态文案：搜索无命中时显示专属提示 */
  let emptyMain = ''
  let emptySub = ''
  if (isSearchMode && listItems.length === 0) {
    emptyMain = '没有找到相关事项'
    emptySub = '换个关键词试试吧'
  } else if (isTagHistory && listItems.length === 0) {
    emptyMain = '所有日期里都没有带这个标签的事项'
    emptySub = '换个标签或切回「仅今天」试试'
  } else if (activeTag && listItems.length === 0) {
    emptyMain = '这个标签下还没有事项'
    emptySub = '换个标签或清掉筛选试试'
  } else if (tasks.length === 0) {
    if (tab === 'daily') {
      emptyMain = '这一天还是一片平静的海面'
      emptySub = '在下面写下第一条任务吧'
    } else {
      emptyMain = '还没有长期事项'
      emptySub = '把想慢慢完成的事记在这里'
    }
  } else if (filter === 'pending') {
    emptyMain = '全部完成啦！'
    emptySub = '鲸鱼娘替你开心～'
  } else {
    emptyMain = '还没有已完成的任务'
    emptySub = '勾掉一条试试吧'
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center px-3 py-4 md:py-6">
      <PageMeta title="鲸鱼待办 · 卡通待办事项小工具" description="卡通蓝色系待办小工具：按日期与长期事项管理任务，支持勾选、拖拽排序与筛选，数据保存在本地浏览器。" />

      <main className="app-shell wobble-lg paper-dots doodle-shadow flex flex-col overflow-hidden border-2 border-border">
        {/* 标题 */}
        <header className="flex items-center gap-3 px-4 pb-3 pt-4">
          <WhaleMark className="w-16 shrink-0 -rotate-3" />
          <div className="min-w-0 flex-1">
            <h1 className="font-hand text-2xl leading-snug text-foreground">鲸鱼待办</h1>
            <p className="text-xs text-muted-foreground">今天的浪花，一条一条清掉</p>
          </div>
        </header>

        {/* Tab + 日期选择 */}
        <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
          <Tabs value={tab} onValueChange={handleTabChange}>
            <TabsList className="wobble-sm doodle-shadow-sm h-auto gap-1.5 border-2 border-border bg-card p-1">
              <TabsTrigger
                value="daily"
                className="wobble-sm px-4 py-1.5 text-sm font-medium transition-transform data-[state=active]:scale-105 data-[state=active]:font-semibold data-[state=active]:!bg-primary data-[state=active]:!text-primary-foreground"
              >
                待办
              </TabsTrigger>
              <TabsTrigger
                value="longterm"
                className="wobble-sm px-4 py-1.5 text-sm font-medium transition-transform data-[state=active]:scale-105 data-[state=active]:font-semibold data-[state=active]:!bg-primary data-[state=active]:!text-primary-foreground"
              >
                长期
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
            {/* 主题切换：太阳/月亮图标，二态切换，与导入/导出按钮风格一致 */}
            <button
              type="button"
              onClick={() => setTheme(isDark ? 'light' : 'dark')}
              title={isDark ? '切换到浅色主题' : '切换到深色主题'}
              aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
              className="wobble-sm flex size-8 shrink-0 items-center justify-center rounded-md border-2 border-border bg-card text-primary transition-transform hover:bg-muted active:translate-y-0.5"
            >
              {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
            {/* 导入/导出：位于日期选择控件左侧 */}
            <button
              type="button"
              onClick={handleExport}
              title="导出数据"
              aria-label="导出数据"
              className="wobble-sm flex size-8 shrink-0 items-center justify-center rounded-md border-2 border-border bg-card text-primary transition-transform hover:bg-muted active:translate-y-0.5"
            >
              <Download className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              title="导入数据"
              aria-label="导入数据"
              className="wobble-sm flex size-8 shrink-0 items-center justify-center rounded-md border-2 border-border bg-card text-accent transition-transform hover:bg-muted active:translate-y-0.5"
            >
              <Upload className="size-4" />
            </button>
            {/* 隐藏的文件选择框：只接受 .csv，读取后重置 value 以支持重复选择同一文件 */}
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleImportFile(file)
                e.target.value = ''
              }}
            />

            {/* 日期选择：透明原生 input 接收点击（点击任意位置弹日历），上层纯展示避免选中高亮 */}
            <div className="group relative w-44 shrink-0">
              <Input
                ref={dateRef}
                type="date"
                value={date}
                onChange={(e) => {
                  setDate(e.target.value || todayStr())
                  // 切换日期自动清空搜索状态
                  resetSearch()
                }}
                onClick={openDatePicker}
                disabled={tab === 'longterm'}
                aria-label="选择日期"
                className="wobble-sm w-full cursor-pointer opacity-0"
              />
              <span
                aria-hidden="true"
                className={`wobble-sm pointer-events-none absolute inset-0 flex items-center justify-center rounded-md border-2 bg-card px-2.5 text-sm transition-colors ${
                  tab === 'longterm'
                    ? 'border-border text-muted-foreground'
                    : 'border-border text-foreground group-focus-within:border-primary'
                }`}
              >
                {date}
              </span>
            </div>
            {tab === 'daily' && !isToday && (
              <Button
                variant="ghost"
                onClick={() => setDate(todayStr())}
                className="wobble-sm shrink-0 border-2 border-border bg-card px-3 text-xs font-medium text-primary hover:bg-muted"
              >
                回今天
              </Button>
            )}
          </div>
        </div>

          {/* 筛选器 + 搜索框 */}
        <div className="flex items-center gap-1.5 px-4 pb-3">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={`wobble-sm border-2 px-3 py-1 text-xs font-medium transition-transform active:translate-y-0.5 ${
                filter === f.key
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-card text-foreground hover:bg-muted'
              }`}
            >
              {f.label}
            </button>
          ))}
          {!isSearchMode && tasks.length > 0 && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {doneCount}/{tasks.length} 完成
            </span>
          )}
          {isSearchMode && (
            <span className="shrink-0 text-xs text-muted-foreground">找到 {listItems.length} 项</span>
          )}

          {/* 方案 B：极小全选框常驻（实心=全选，蓝描边=部分选中），批量操作收进列表内悬浮工具条 */}
          {batchEnabled && listItems.length > 0 && (
            <Checkbox
              checked={allSelected ? true : selectedIds.length > 0 ? 'indeterminate' : false}
              onCheckedChange={toggleSelectAll}
              aria-label="全选 / 取消全选"
              title="全选 / 取消全选"
              className="size-4 shrink-0"
            />
          )}

          {/* 搜索框：回车触发查询，× 清空并自动查询一次（恢复全部） */}
          <div className="relative ml-auto w-36 shrink-0">
            <Input
              ref={searchRef}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitSearch()
              }}
              placeholder="搜索事项…"
              aria-label="搜索事项"
              maxLength={50}
              className="wobble-sm h-8 w-full border-2 border-border bg-card pr-8 text-xs"
            />
            {searchInput && (
              <button
                type="button"
                aria-label="清空搜索"
                title="清空搜索"
                onClick={() => resetSearch()}
                className="absolute right-1.5 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* 标签筛选行：标签 chips（小胶囊流式排列，宽度随文字自适应）+ 作用域分段控件（选中标签后才可切换） */}
        {usedTags.length > 0 && (
          <div className="flex items-start gap-2 px-4 pb-3">
            <span className="shrink-0 pt-1 text-xs text-muted-foreground">标签</span>
                <div className="flex flex-1 flex-wrap gap-1.5">
                  {usedTags.map(({ name, count }) => (
                    <button
                      key={name}
                      type="button"
                      aria-pressed={activeTag === name}
                      title={`筛选标签「${name}」，再点一次取消`}
                      onClick={() => setActiveTag(activeTag === name ? null : name)}
                      className={`wobble-sm rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-transform active:translate-y-0.5 ${tagColor(name)} ${
                        activeTag === name
                          ? 'font-semibold ring-2 ring-primary/40'
                          : 'opacity-75 hover:opacity-100'
                      }`}
                    >
                      {name}
                      <span className="ml-1 opacity-60">{count}</span>
                    </button>
                  ))}
                </div>
                {tab === 'daily' && (
                  <button
                    type="button"
                    aria-pressed={tagScope === 'all'}
                    aria-label="标签筛选范围"
                    disabled={isSearchMode || activeTag === null}
                    title={
                      activeTag === null
                        ? '先选中一个标签后才能切换查询范围'
                        : '点击在「仅今天 / 全部日期」之间切换'
                    }
                    onClick={() => setTagScope(tagScope === 'today' ? 'all' : 'today')}
                    className="wobble-sm flex shrink-0 items-center rounded-full border-2 border-border bg-card p-0.5 transition-transform active:translate-y-0.5 disabled:pointer-events-none disabled:opacity-50"
                  >
                    {/* 整块可点：点任意处即在两档间切换，当前生效档高亮 */}
                    <span
                      className={`rounded-full px-2 py-1 text-[10px] font-medium transition-colors ${
                        tagScope === 'today'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground'
                      }`}
                    >
                      仅今天
                    </span>
                    <span
                      className={`rounded-full px-2 py-1 text-[10px] font-medium transition-colors ${
                        tagScope === 'all'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground'
                      }`}
                    >
                      全部日期
                    </span>
                  </button>
                )}
          </div>
        )}

        {/* 任务列表（固定窗口内滚动）：外框 relative 承载悬浮工具条；工具条绝对定位不占文档流，出现/消失任务零位移 */}
        <div className="relative min-h-0 flex-1">
          {/* 方案 B：选中即浮现的悬浮工具条（浮层吸顶，✕ 一键清空；外层不拦截点击，仅本体可交互） */}
          <AnimatePresence>
            {batchEnabled && selectedIds.length > 0 && listItems.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.94 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.94 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="pointer-events-none absolute inset-x-0 top-1.5 z-20 flex justify-center"
              >
                <div className="pointer-events-auto flex items-center gap-0.5 rounded-full border border-border bg-card/95 px-1.5 py-1 shadow-lg backdrop-blur">
                <span className="pl-2 pr-1 text-xs font-semibold">已选 {selectedIds.length} 项</span>
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  className="rounded-full px-2.5 py-1 text-xs font-semibold text-foreground transition-colors hover:bg-muted"
                >
                  {allSelected ? '取消全选' : '全选'}
                </button>
                <button
                  type="button"
                  onClick={openMigrate}
                  className="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold text-primary transition-colors hover:bg-muted"
                >
                  <MoveRight className="size-3.5" />
                  迁移
                </button>
                <button
                  type="button"
                  onClick={openBatchDelete}
                  title="删除选中项"
                  aria-label="删除选中项"
                  className="rounded-full p-1.5 text-accent transition-colors hover:bg-muted"
                >
                  <Trash2 className="size-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedIds([])}
                  title="清空选择"
                  aria-label="清空选择"
                  className="rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-muted"
                >
                  <X className="size-3.5" />
                </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div className="h-full overflow-y-auto px-4 pb-2">
          {listItems.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-8 text-center">
              <WhaleMark className="w-28 -rotate-2 opacity-90" />
              <p className="font-hand text-xl text-foreground">{emptyMain}</p>
              <p className="text-xs text-muted-foreground">{emptySub}</p>
            </div>
          ) : (
            <>
            {/* Reorder 拖拽：拖动时本体实时移动，其余项动画让位；筛选状态下由 commitReorder 把隐藏任务按原位插回 */}
            <Reorder.Group
              as="ol"
              axis="y"
              values={listItems.map((item) => item.task)}
              onReorder={(nextVisible) => updateList((list) => commitReorder(list, nextVisible))}
              className="flex flex-col gap-2.5"
            >
              {listItems.map((item, i) => (
                <TaskItem
                  key={item.task.id}
                  task={item.task}
                  index={i + 1}
                  dateLabel={
                    isTagHistory
                      ? item.date
                        ? item.date.slice(5)
                        : null
                      : item.date && item.date !== date
                        ? item.date.slice(5)
                        : null
                  }
                  highlight={isSearchMode ? searchKeyword : undefined}
                  dragDisabled={isSearchMode || isTagHistory}
                  selectable={batchEnabled}
                  selected={selectedIds.includes(item.task.id)}
                  onToggleSelect={toggleSelect}
                  tagCandidates={tagCandidates}
                  onToggle={toggleTask}
                  onDelete={deleteTask}
                  onEdit={editTask}
                />
              ))}
            </Reorder.Group>
            </>
          )}
          </div>
        </div>

        {/* 添加任务 */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            addTask()
          }}
          className="flex shrink-0 flex-col gap-1.5 border-t-2 border-dashed border-border/70 bg-card/80 px-4 py-3"
        >
          {/* 待添加任务的已选标签（可点 × 移除），随任务一并保存 */}
          {draftTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              {draftTags.map((tag) => (
                <span
                  key={tag}
                  className={`flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] leading-none ${tagColor(tag)}`}
                >
                  {tag}
                  <button
                    type="button"
                    aria-label={`移除标签 ${tag}`}
                    title={`移除标签 ${tag}`}
                    onClick={() => setDraftTags(draftTags.filter((t) => t !== tag))}
                    className="rounded-full p-0.5 hover:bg-foreground/10"
                  >
                    <X className="size-2.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            {/* 输入框：回车提交、Shift+回车换行，高度随内容自适应 */}
            <textarea
              ref={inputRef}
              value={input}
              rows={1}
              maxLength={200}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  addTask()
                }
              }}
              placeholder={tab === 'daily' ? '添加今天的任务…' : '添加长期事项…'}
              aria-label="任务内容"
              className={`wobble-sm min-w-0 flex-1 resize-none overflow-y-auto rounded-lg border-2 border-border bg-card px-3 py-2 text-base leading-relaxed outline-none ${
                shake ? 'shake' : ''
              }`}
            />
            {/* 标签选择器：为待添加任务选标签 */}
            <TagPicker selected={draftTags} candidates={tagCandidates} onChange={setDraftTags}>
              <button
                type="button"
                aria-label="选择标签"
                title="选择标签"
                className={`wobble-sm flex size-10 shrink-0 items-center justify-center rounded-xl transition-colors ${
                  draftTags.length > 0
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:bg-muted hover:text-primary'
                }`}
              >
                <Tag className="size-5" />
              </button>
            </TagPicker>
            <Button type="submit" className="wobble doodle-shadow press shrink-0 gap-1">
              <Plus className="size-4" />
              添加
            </Button>
          </div>
        </form>

        {/* 导入二次确认弹窗（受控：open 由 pendingImport 驱动） */}
        <AlertDialog
          open={pendingImport !== null}
          onOpenChange={(open) => {
            if (!open) setPendingImport(null)
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认导入并覆盖现有数据？</AlertDialogTitle>
              <AlertDialogDescription>
                将清空本地全部数据并导入文件中的 {pendingImportCount} 条事项；原数据已自动备份到下载目录。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction onClick={confirmImport}>确认导入</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* 迁移弹窗：选择目标日期（默认今天），确认后单步执行 */}
        <AlertDialog open={migrateOpen} onOpenChange={setMigrateOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>迁移选中的 {selectedIds.length} 项待办</AlertDialogTitle>
              <AlertDialogDescription>
                选择目标日期，迁移后原位置（原日期或长期列表）将不再保留这些事项。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <Input
              type="date"
              value={migrateDate}
              onChange={(e) => setMigrateDate(e.target.value || todayStr())}
              aria-label="目标日期"
              className="wobble-sm w-full cursor-pointer"
            />
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction onClick={confirmMigrate}>确认迁移</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* 批量删除二次确认：与迁移弹窗同风格，确认按钮样式也保持一致 */}
        <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>删除选中的 {selectedIds.length} 项待办</AlertDialogTitle>
              <AlertDialogDescription>
                删除后无法恢复，将从原日期或长期列表中移除这些事项。如有需要可先导出 CSV 备份。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction onClick={confirmBatchDelete}>确认删除</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </main>
    </div>
  )
}
