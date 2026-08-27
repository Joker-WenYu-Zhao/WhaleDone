import { useState } from 'react'
import { Checkbox } from '@/components/ui/checkbox'
import { GripVertical, Trash2 } from 'lucide-react'
import type { Task } from '@/lib/todo'

interface TaskItemProps {
  task: Task
  /** 列表中显示的序号（按筛选后的顺序自动生成） */
  index: number
  isDragging: boolean
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  onDragStart: (id: string) => void
  onDragEnter: (id: string) => void
  onDragEnd: () => void
}

export default function TaskItem({
  task,
  index,
  isDragging,
  onToggle,
  onDelete,
  onDragStart,
  onDragEnter,
  onDragEnd,
}: TaskItemProps) {
  // 仅在按住拖拽把手时允许整行拖动
  const [dragEnabled, setDragEnabled] = useState(false)

  return (
    <li
      draggable={dragEnabled}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        onDragStart(task.id)
      }}
      onDragEnter={() => onDragEnter(task.id)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => e.preventDefault()}
      onDragEnd={() => {
        setDragEnabled(false)
        onDragEnd()
      }}
      className={`wobble-sm doodle-shadow-sm flex items-center gap-2 border-2 border-border bg-card px-2.5 py-1.5 transition-opacity ${
        isDragging ? 'opacity-50' : ''
      }`}
    >
      {/* 自动编号 */}
      <span aria-hidden="true" className="w-6 shrink-0 text-center font-hand text-lg leading-none text-primary">
        {index}.
      </span>

      {/* 勾选框 */}
      <Checkbox
        checked={task.done}
        onCheckedChange={() => onToggle(task.id)}
        aria-label={task.done ? '标记为待办' : '标记为已完成'}
        className="h-5 w-5 wobble-sm border-2 border-border data-[state=checked]:border-primary"
      />

      {/* 任务内容 */}
      <span
        className={`min-w-0 flex-1 break-words text-sm leading-relaxed ${
          task.done ? 'task-done-text text-muted-foreground' : 'text-foreground'
        }`}
      >
        {task.text}
      </span>

      {/* 拖拽把手 */}
      <button
        type="button"
        aria-label="拖动调整顺序"
        title="拖动调整顺序"
        onMouseDown={() => setDragEnabled(true)}
        onMouseUp={() => setDragEnabled(false)}
        className="flex size-10 shrink-0 cursor-grab touch-none items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground active:cursor-grabbing"
      >
        <GripVertical className="size-5" />
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
    </li>
  )
}
