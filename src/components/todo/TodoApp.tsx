import { useEffect, useMemo, useRef, useState } from 'react'
import { Reorder } from 'motion/react'
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
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const dateRef = useRef<HTMLInputElement>(null)

  // 任何数据变化都实时保存
  useEffect(() => {
    saveData(data)
  }, [data])

  // 添加框高度随内容自适应（上限 120px，超出内部滚动）
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [input])

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

  const editTask = (id: string, text: string) => {
    updateList((list) => list.map((t) => (t.id === id ? { ...t, text } : t)))
  }

  /** 点击日期输入框任意位置都弹出日历（showPicker 不支持时静默降级为原生交互） */
  const openDatePicker = () => {
    try {
      dateRef.current?.showPicker()
    } catch {
      // 部分浏览器在非用户手势或不支持时抛错，忽略即可
    }
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
            {/* 日期选择：透明原生 input 接收点击（点击任意位置弹日历），上层纯展示避免选中高亮 */}
            <div className="group relative w-44 shrink-0">
              <Input
                ref={dateRef}
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value || todayStr())}
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
            <>
            {/* Reorder 拖拽：拖动时本体实时移动，其余项动画让位；筛选状态下由 commitReorder 把隐藏任务按原位插回 */}
            <Reorder.Group
              as="ol"
              axis="y"
              values={visible}
              onReorder={(nextVisible) => updateList((list) => commitReorder(list, nextVisible))}
              className="flex flex-col gap-2.5"
            >
              {visible.map((task, i) => (
                <TaskItem
                  key={task.id}
                  task={task}
                  index={i + 1}
                  onToggle={toggleTask}
                  onDelete={deleteTask}
                  onEdit={editTask}
                />
              ))}
            </Reorder.Group>
            </>
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
          <Button type="submit" className="wobble doodle-shadow press shrink-0 gap-1">
            <Plus className="size-4" />
            添加
          </Button>
        </form>
      </main>
    </div>
  )
}
