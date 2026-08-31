import { useState, type ReactNode } from 'react'
import { Check } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { TAG_MAX, TAG_NAME_MAX, normalizeTags, tagColor } from '@/lib/todo'

interface TagPickerProps {
  /** 当前已选标签 */
  selected: string[]
  /** 候选标签（调用方传入：预置 ∪ 全库已有） */
  candidates: string[]
  /** 已选集合变化回调 */
  onChange: (next: string[]) => void
  /** 触发按钮（PopoverTrigger asChild 的子元素） */
  children: ReactNode
}

/** 标签选择器：候选 chips 点选 + 新建输入（单任务上限 TAG_MAX 个，超长截断） */
export default function TagPicker({ selected, candidates, onChange, children }: TagPickerProps) {
  const [draft, setDraft] = useState('')
  const full = selected.length >= TAG_MAX
  // 候选 = 调用方候选 ∪ 已选（新建后未保存的标签也要可见可取消）
  const options = [...new Set([...candidates, ...selected])]

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      onChange(selected.filter((t) => t !== name))
    } else if (!full) {
      onChange([...selected, name])
    }
  }

  const createTag = () => {
    if (full) return
    const [name] = normalizeTags([draft])
    if (!name) return
    if (!selected.includes(name)) onChange([...selected, name])
    setDraft('')
  }

  return (
    <Popover>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-3">
        <div className="flex flex-wrap gap-1.5">
          {options.map((name) => {
            const isSelected = selected.includes(name)
            return (
              <button
                key={name}
                type="button"
                disabled={!isSelected && full}
                onClick={() => toggle(name)}
                className={`flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs transition-opacity ${tagColor(name)} ${
                  isSelected
                    ? 'font-semibold'
                    : full
                      ? 'cursor-not-allowed opacity-30'
                      : 'opacity-70 hover:opacity-100'
                }`}
              >
                {isSelected && <Check className="size-3" />}
                {name}
              </button>
            )
          })}
        </div>
        {/* 新建标签：回车提交；与候选重复时直接选中已有项；满 3 个后禁用 */}
        <Input
          value={draft}
          maxLength={TAG_NAME_MAX}
          disabled={full}
          placeholder={full ? '标签已满 3 个' : '新建标签，回车确认'}
          aria-label="新建标签"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              createTag()
            }
          }}
          className="mt-2.5 h-7 w-full border-2 border-border bg-card text-xs"
        />
      </PopoverContent>
    </Popover>
  )
}
