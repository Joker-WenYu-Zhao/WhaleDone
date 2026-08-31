/* 鲸鱼待办 · 导入导出（CSV 备份/恢复，纯函数，零第三方依赖） */

import { collectAllDaily, createTask, emptyData, normalizeTags, taskTags, todayStr } from './todo'
import type { TodoData } from './todo'

/* CSV 契约常量（见《任务标签-前端设计文档.md》9.2 字段级对照表：类型,日期,内容,状态,标签） */
export const CSV_HEADER = '类型,日期,内容,状态,标签'
/** 旧版 4 列表头（无标签列，导入时兼容） */
export const CSV_HEADER_LEGACY = '类型,日期,内容,状态'
export const TYPE_DAILY = '每日待办'
export const TYPE_LONGTERM = '长期事项'
export const STATUS_DONE = '已完成'
export const STATUS_PENDING = '待办'
/** 内容长度上限，与添加框 maxLength 一致，超出截断 */
const TEXT_MAX = 200

/** CSV 解析/校验失败（message 面向用户，含行号） */
export class CsvParseError extends Error {}

/** 字段含逗号/引号/换行时用双引号包裹，字段内引号转义为 "" */
function escapeCsvField(value: string): string {
  if (/[",\r\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`
  return value
}

/** TodoData → CSV 文本（含 UTF-8 BOM，Excel 双击打开不乱码；空数据仅表头） */
export function todoToCsv(data: TodoData): string {
  const lines: string[] = [CSV_HEADER]
  const statusOf = (done: boolean) => (done ? STATUS_DONE : STATUS_PENDING)
  for (const { task, date } of collectAllDaily(data)) {
    lines.push(
      [TYPE_DAILY, date ?? '', task.text, statusOf(task.done), taskTags(task).join('|')]
        .map(escapeCsvField)
        .join(','),
    )
  }
  for (const task of data.longterm) {
    lines.push(
      [TYPE_LONGTERM, '', task.text, statusOf(task.done), taskTags(task).join('|')]
        .map(escapeCsvField)
        .join(','),
    )
  }
  return `\uFEFF${lines.join('\r\n')}\r\n`
}

/**
 * 状态机解析 CSV 文本为二维表：
 * 支持双引号包裹的字段（可含逗号、换行、转义引号 ""），自动剥离 BOM。
 */
export function parseCsv(text: string): string[][] {
  const clean = text.replace(/^\uFEFF/, '')
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i]
    if (inQuotes) {
      if (ch === '"') {
        if (clean[i + 1] === '"') {
          field += '"'
          i++
        } else {
          inQuotes = false
        }
      } else {
        field += ch
      }
    } else if (ch === '"') {
      inQuotes = true
    } else if (ch === ',') {
      row.push(field)
      field = ''
    } else if (ch === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (ch !== '\r') {
      field += ch
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  return rows
}

/** 校验 YYYY-MM-DD 且为真实存在的日期（如 2026-02-30 不通过） */
function isValidDate(value: string): boolean {
  const [y, m, d] = value.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d
}

/**
 * CSV 二维表 → TodoData 导入（含全部校验，任一行非法即抛 CsvParseError 并指出行号）：
 * - 表头兼容新旧双格式：5 列新格式（含标签列）或 4 列旧格式均可；空行跳过；0 条有效数据视为空文件
 * - 数据行 4 列 = 无标签，5 列解析标签（| 分隔后逐个规范化）；≥6 列报错
 * - 类型只允许 每日待办/长期事项；每日待办日期必填且合法，长期事项日期必须留空
 * - 状态只允许 已完成/待办，缺省视为待办；内容去空白后必填，超 200 字符截断
 * - Task.id 一律重新生成，不复用文件中的旧 id
 */
export function csvToTodo(rows: string[][]): TodoData {
  if (rows.length === 0) throw new CsvParseError('文件是空的')
  const header = rows[0].map((c) => c.trim()).join(',')
  const isLegacyHeader = header === CSV_HEADER_LEGACY
  if (header !== CSV_HEADER && !isLegacyHeader) {
    throw new CsvParseError('表头不正确，应为「类型,日期,内容,状态,标签」')
  }

  const data = emptyData()
  let count = 0
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i]
    if (row.every((c) => c.trim() === '')) continue
    const lineNo = i + 1
    if (row.length !== 4 && row.length !== 5) {
      throw new CsvParseError(`第 ${lineNo} 行列数不对，应为 4 列或 5 列（类型,日期,内容,状态[,标签]）`)
    }
    if (isLegacyHeader && row.length !== 4) {
      throw new CsvParseError(`第 ${lineNo} 行列数不对，旧格式应为 4 列（类型,日期,内容,状态）`)
    }
    const [type, dateField, textField, statusField] = row.map((c) => c.trim())
    // 第 5 列标签：| 分隔多标签，逐个规范化（非法标签静默规范化，不报错终止）
    const tags = normalizeTags((row[4] ?? '').split('|'))

    let done: boolean
    if (statusField === '' || statusField === STATUS_PENDING) {
      done = false
    } else if (statusField === STATUS_DONE) {
      done = true
    } else {
      throw new CsvParseError(`第 ${lineNo} 行状态值不合法：「${statusField}」，只允许「已完成」或「待办」`)
    }

    const text = textField.slice(0, TEXT_MAX)
    if (!text) throw new CsvParseError(`第 ${lineNo} 行内容为空`)

    if (type === TYPE_DAILY) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dateField) || !isValidDate(dateField)) {
        throw new CsvParseError(`第 ${lineNo} 行日期不合法：「${dateField || '（空）'}」，应为 YYYY-MM-DD`)
      }
      const list = data.daily[dateField] ?? []
      list.push({ ...createTask(text), done, ...(tags.length > 0 ? { tags } : {}) })
      data.daily[dateField] = list
    } else if (type === TYPE_LONGTERM) {
      if (dateField) {
        throw new CsvParseError(`第 ${lineNo} 行为长期事项，日期必须留空`)
      }
      data.longterm.push({ ...createTask(text), done, ...(tags.length > 0 ? { tags } : {}) })
    } else {
      throw new CsvParseError(`第 ${lineNo} 行类型值不合法：「${type || '（空）'}」，只允许「每日待办」或「长期事项」`)
    }
    count++
  }
  if (count === 0) throw new CsvParseError('文件中没有有效数据')
  return data
}

/** 备份文件名：{prefix}-YYYY-MM-DD.csv */
export function buildBackupFilename(prefix: string): string {
  return `${prefix}-${todayStr()}.csv`
}

/** 触发浏览器下载文本文件（落至下载目录） */
export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
