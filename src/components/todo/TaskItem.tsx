import { useEffect, useRef, useState } from 'react'
import { Reorder, useDragControls } from 'motion/react'
import { Checkbox } from '@/components/ui/checkbox'
import { Check, GripVertical, Pencil, Trash2, X } from 'lucide-react'
import type { Task } from '@/lib/todo'

interface TaskItemProps {
  task: Task
  /** 列表中显示的序号（按筛选后的顺序自动生成） */
  index: number
  /** 所属日期标记（如 08-15）；仅搜索命中其他日期任务时传入，替代序号展示 */
  dateLabel?: string | null
  /** 搜索关键词，非空时内容中的命中片段高亮 */
  highlight?: string
  /** 搜索生效时禁用拖拽（隐藏把手） */
  dragDisabled?: boolean
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  onEdit: (id: string, text: string) => void
}

/** 把文本按关键词切分并高亮命中片段（大小写不敏感） */
function HighlightedText({ text, keyword }: { text: string; keyword: string }) {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return text
  const parts: { text: string; hit: boolean }[] = []
  let rest = text
  while (rest.length > 0) {
    const idx = rest.toLowerCase().indexOf(kw)
    if (idx < 0) {
      parts.push({ text: rest, hit: false })
      break
    }
    if (idx > 0) parts.push({ text: rest.slice(0, idx), hit: false })
    parts.push({ text: rest.slice(idx, idx + kw.length), hit: true })
    rest = rest.slice(idx + kw.length)
  }
  return (
    <>
      {parts.map((p, i) =>
        p.hit ? (
          <mark key={i} className="rounded-sm bg-yellow-200 px-0.5 text-foreground">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  )
}

export default function TaskItem({
  task,
  index,
  dateLabel,
  highlight,
  dragDisabled,
  onToggle,
  onDelete,
  onEdit,
}: TaskItemProps) {
  // Reorder 拖拽控制器：只有按住把手才启动拖动，不影响勾选和文本选择
  const controls = useDragControls()
  // 行内编辑状态：进入编辑时把当前文本拷贝到草稿，保存才写回
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const editRef = useRef<HTMLTextAreaElement>(null)

  const startEdit = () => {
    setDraft(task.text)
    setEditing(true)
  }

  const cancelEdit = () => {
    setEditing(false)
    setDraft('')
  }

  const saveEdit = () => {
    const text = draft.trim()
    if (!text) {
      // 空内容不允许保存，聚焦回去提示
      editRef.current?.focus()
      return
    }
    onEdit(task.id, text)
    setEditing(false)
    setDraft('')
  }

  // 编辑框高度随内容自适应（上限 120px，超出内部滚动）
  useEffect(() => {
    const el = editRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [draft])

  return (
    <Reorder.Item
      value={task}
      dragListener={false}
      dragControls={controls}
      whileDrag={{ scale: 1.04, rotate: 1 }}
      className="wobble-sm doodle-shadow-sm relative z-10 flex items-center gap-2 border-2 border-border bg-card px-2.5 py-1.5"
    >
      {/* 序号 / 所属日期标记（搜索命中其他日期任务时） */}
      {dateLabel ? (
        <span title={`所属日期：${dateLabel}`} className="w-11 shrink-0 text-center font-hand text-xs leading-none text-muted-foreground">
          {dateLabel}
        </span>
      ) : (
        <span aria-hidden="true" className="w-6 shrink-0 text-center font-hand text-lg leading-none text-primary">
          {index}.
        </span>
      )}

      {/* 勾选框 */}
      <Checkbox
        checked={task.done}
        onCheckedChange={() => onToggle(task.id)}
        aria-label={task.done ? '标记为待办' : '标记为已完成'}
        className="h-5 w-5 wobble-sm border-2 border-border data-[state=checked]:border-primary"
      />

      {editing ? (
        <>
          {/* 编辑中的输入框：回车保存、Shift+回车换行、Esc 取消 */}
          <textarea
            ref={editRef}
            value={draft}
            autoFocus
            rows={1}
            maxLength={200}
            aria-label="编辑任务内容"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                saveEdit()
              }
              if (e.key === 'Escape') cancelEdit()
            }}
            className="wobble-sm min-w-0 flex-1 resize-none overflow-y-auto rounded-lg border-2 border-primary bg-card px-2 py-1 text-sm leading-relaxed text-foreground outline-none"
          />

          {/* 取消编辑 */}
          <button
            type="button"
            aria-label="取消编辑"
            title="取消编辑"
            onClick={cancelEdit}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground active:scale-90"
          >
            <X className="size-5" />
          </button>

          {/* 保存修改 */}
          <button
            type="button"
            aria-label="保存修改"
            title="保存修改"
            onClick={saveEdit}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl text-primary hover:bg-primary/15 active:scale-90"
          >
            <Check className="size-5" />
          </button>
        </>
      ) : (
        <>
          {/* 任务内容（完整展示，过长自动换行，保留手动换行；搜索命中片段高亮） */}
          <span
            className={`min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-relaxed ${
              task.done ? 'task-done-text text-muted-foreground' : 'text-foreground'
            }`}
          >
            {highlight ? <HighlightedText text={task.text} keyword={highlight} /> : task.text}
          </span>

          {/* 拖拽把手（搜索生效时隐藏，避免跨日期排序错乱） */}
          {!dragDisabled && (
            <button
              type="button"
              aria-label="拖动调整顺序"
              title="拖动调整顺序"
              onPointerDown={(e) => controls.start(e)}
              className="flex size-10 shrink-0 cursor-grab touch-none items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground active:cursor-grabbing"
            >
              <GripVertical className="size-5" />
            </button>
          )}

          {/* 编辑 */}
          <button
            type="button"
            aria-label="编辑任务"
            title="编辑任务"
            onClick={startEdit}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl text-primary hover:bg-primary/15 active:scale-90"
          >
            <Pencil className="size-5" />
          </button>

          {/* 删除 */}
          <button
            type="button"
            aria-label="删除任务"
            title="删除任务"
            onClick={() => onDelete(task.id)}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl text-accent hover:bg-accent/15 active:scale-90"
          >
            <Trash2 className="size-5" />
          </button>
        </>
      )}
    </Reorder.Item>
  )
}
