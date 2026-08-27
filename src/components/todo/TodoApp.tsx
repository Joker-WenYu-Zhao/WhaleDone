import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import PageMeta from '@/components/common/PageMeta'
import WhaleMark from './WhaleMark'
import TaskItem from './TaskItem'
import {
  FILTERS,
  commitReorder,
  createTask,
  currentList,
  filterTasks,
  loadData,
  saveData,
  todayStr,
} from '@/lib/todo'
import type { FilterKey, TabKey, Task, TodoData } from '@/lib/todo'

export default function TodoApp() {
  const [data, setData] = useState<TodoData>(loadData)
  const [tab, setTab] = useState<TabKey>('daily')
  const [date, setDate] = useState<string>(todayStr())
  const [filter, setFilter] = useState<FilterKey>('all')
  const [input, setInput] = useState('')
  const [shake, setShake] = useState(false)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const dragIdRef = useRef<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 任何数据变化都实时保存
  useEffect(() => {
    saveData(data)
  }, [data])

  const tasks = currentList(data, tab, date)
  const visible = useMemo(() => filterTasks(tasks, filter), [tasks, filter])
  const doneCount = tasks.filter((t) => t.done).length
  const isToday = date === todayStr()

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
    updateList((list) => [...list, createTask(text)])
    setInput('')
    inputRef.current?.focus()
  }

  const toggleTask = (id: string) => {
    updateList((list) => list.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
  }

  const deleteTask = (id: string) => {
    updateList((list) => list.filter((t) => t.id !== id))
  }

  /* 拖拽排序：拖到目标项上时在可见列表内交换，再合并回完整列表 */
  const handleDragStart = (id: string) => {
    dragIdRef.current = id
    setDraggingId(id)
  }

  const handleDragEnter = (id: string) => {
    const fromId = dragIdRef.current
    if (!fromId || fromId === id) return
    updateList((list) => {
      const vis = filterTasks(list, filter)
      const from = vis.findIndex((t) => t.id === fromId)
      const to = vis.findIndex((t) => t.id === id)
      if (from < 0 || to < 0) return list
      const next = [...vis]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return commitReorder(list, next)
    })
  }

  const handleDragEnd = () => {
    dragIdRef.current = null
    setDraggingId(null)
  }

  /* 空状态文案 */
  let emptyMain = ''
  let emptySub = ''
  if (tasks.length === 0) {
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
    <div className="mx-auto w-full max-w-xl px-3 py-4 md:py-6">
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
          <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
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
            <Input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value || todayStr())}
              disabled={tab === 'longterm'}
              aria-label="选择日期"
              className="wobble-sm w-44 shrink-0 border-2 border-border bg-card px-2.5 text-sm"
            />
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

        {/* 筛选器 */}
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
          {tasks.length > 0 && (
            <span className="ml-auto shrink-0 text-xs text-muted-foreground">
              {doneCount}/{tasks.length} 完成
            </span>
          )}
        </div>

        {/* 任务列表（固定窗口内滚动） */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
          {visible.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-8 text-center">
              <WhaleMark className="w-28 -rotate-2 opacity-90" />
              <p className="font-hand text-xl text-foreground">{emptyMain}</p>
              <p className="text-xs text-muted-foreground">{emptySub}</p>
            </div>
          ) : (
            <ol className="flex flex-col gap-2.5">
              {visible.map((task, i) => (
                <TaskItem
                  key={task.id}
                  task={task}
                  index={i + 1}
                  isDragging={draggingId === task.id}
                  onToggle={toggleTask}
                  onDelete={deleteTask}
                  onDragStart={handleDragStart}
                  onDragEnter={handleDragEnter}
                  onDragEnd={handleDragEnd}
                />
              ))}
            </ol>
          )}
        </div>

        {/* 添加任务 */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            addTask()
          }}
          className="flex shrink-0 items-center gap-2 border-t-2 border-dashed border-border/70 bg-card/80 px-4 py-3"
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={200}
            placeholder={tab === 'daily' ? '添加今天的任务…' : '添加长期事项…'}
            aria-label="任务内容"
            className={`wobble-sm min-w-0 flex-1 border-2 border-border bg-card px-3 text-base ${
              shake ? 'shake' : ''
            }`}
          />
          <Button type="submit" className="wobble doodle-shadow press shrink-0 gap-1">
            <Plus className="size-4" />
            添加
          </Button>
        </form>
      </main>
    </div>
  )
}
