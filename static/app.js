/* 鲸鱼待办 · 应用逻辑
   数据保存在浏览器 localStorage（按域名隔离）：
   - daily:  按日期（YYYY-MM-DD）存储的待办任务
   - longterm: 不绑定日期的长期事项
*/

'use strict'

var STORAGE_KEY = 'whale-todo-v1'

/* ---------- 状态 ---------- */
var state = {
  tab: 'daily',        // 'daily' | 'longterm'
  date: todayStr(),    // YYYY-MM-DD
  filter: 'all',       // 'all' | 'pending' | 'done'
  draggingId: null,
}

/* ---------- DOM ---------- */
var el = {
  tabs: document.querySelectorAll('.tab'),
  datePicker: document.getElementById('datePicker'),
  todayBtn: document.getElementById('todayBtn'),
  chips: document.querySelectorAll('.chip'),
  countBadge: document.getElementById('countBadge'),
  taskList: document.getElementById('taskList'),
  taskScroll: document.getElementById('taskScroll'),
  emptyState: document.getElementById('emptyState'),
  emptyMain: document.getElementById('emptyMain'),
  emptySub: document.getElementById('emptySub'),
  addForm: document.getElementById('addForm'),
  taskInput: document.getElementById('taskInput'),
}

/* ---------- 工具函数 ---------- */

function todayStr() {
  var d = new Date()
  var m = String(d.getMonth() + 1).padStart(2, '0')
  var day = String(d.getDate()).padStart(2, '0')
  return d.getFullYear() + '-' + m + '-' + day
}

function newId() {
  if (window.crypto && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return Date.now() + '-' + Math.random().toString(36).slice(2, 9)
}

function emptyData() {
  return { daily: {}, longterm: [] }
}

function loadData() {
  try {
    var raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyData()
    var parsed = JSON.parse(raw)
    return {
      daily: parsed && typeof parsed.daily === 'object' ? parsed.daily : {},
      longterm: Array.isArray(parsed.longterm) ? parsed.longterm : [],
    }
  } catch (e) {
    return emptyData()
  }
}

/* 数据变化实时保存；隐私模式等存储失败时静默降级（本次会话内仍可用） */
function saveData(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch (e) {
    /* 存储不可用，忽略 */
  }
}

/** 当前 Tab 对应的任务列表 */
function currentList(data) {
  return state.tab === 'daily' ? data.daily[state.date] || [] : data.longterm
}

/** 筛选后的可见列表 */
function filterTasks(tasks) {
  if (state.filter === 'pending') return tasks.filter(function (t) { return !t.done })
  if (state.filter === 'done') return tasks.filter(function (t) { return t.done })
  return tasks
}

/** 更新当前列表（待办按日期写入，长期直接写数组） */
function updateList(updater) {
  var data = loadData()
  if (state.tab === 'daily') {
    data.daily[state.date] = updater(data.daily[state.date] || [])
  } else {
    data.longterm = updater(data.longterm)
  }
  saveData(data)
  render()
}

/** 筛选状态下拖拽换序：把可见列表的新顺序合并回完整列表 */
function commitReorder(all, visible) {
  var visibleIds = {}
  visible.forEach(function (t) { visibleIds[t.id] = true })
  var result = []
  var inserted = false
  all.forEach(function (t) {
    if (visibleIds[t.id]) {
      if (!inserted) {
        result = result.concat(visible)
        inserted = true
      }
    } else {
      result.push(t)
    }
  })
  return result
}

/* ---------- 渲染 ---------- */

function render() {
  var data = loadData()
  var tasks = currentList(data)
  var visible = filterTasks(tasks)
  var doneCount = tasks.filter(function (t) { return t.done }).length

  /* Tab 激活态 */
  el.tabs.forEach(function (btn) {
    var active = btn.dataset.tab === state.tab
    btn.classList.toggle('is-active', active)
    btn.setAttribute('aria-selected', String(active))
  })

  /* 日期控件（长期 Tab 下禁用） */
  el.datePicker.disabled = state.tab === 'longterm'
  el.todayBtn.hidden = !(state.tab === 'daily' && state.date !== todayStr())

  /* 筛选激活态 */
  el.chips.forEach(function (chip) {
    var active = chip.dataset.filter === state.filter
    chip.classList.toggle('is-active', active)
    chip.setAttribute('aria-pressed', String(active))
  })

  /* 完成计数 */
  if (tasks.length > 0) {
    el.countBadge.hidden = false
    el.countBadge.textContent = doneCount + '/' + tasks.length + ' 完成'
  } else {
    el.countBadge.hidden = true
  }

  /* 输入框占位文案 */
  el.taskInput.placeholder = state.tab === 'daily' ? '添加今天的任务…' : '添加长期事项…'

  /* 空状态 */
  if (visible.length === 0) {
    el.taskList.hidden = true
    el.emptyState.hidden = false
    if (tasks.length === 0) {
      if (state.tab === 'daily') {
        el.emptyMain.textContent = '这一天还是一片平静的海面'
        el.emptySub.textContent = '在下面写下第一条任务吧'
      } else {
        el.emptyMain.textContent = '还没有长期事项'
        el.emptySub.textContent = '把想慢慢完成的事记在这里'
      }
    } else if (state.filter === 'pending') {
      el.emptyMain.textContent = '全部完成啦！'
      el.emptySub.textContent = '鲸鱼娘替你开心～'
    } else {
      el.emptyMain.textContent = '还没有已完成的任务'
      el.emptySub.textContent = '勾掉一条试试吧'
    }
  } else {
    el.taskList.hidden = false
    el.emptyState.hidden = true
  }

  /* 任务条目 */
  el.taskList.innerHTML = ''
  visible.forEach(function (task, i) {
    el.taskList.appendChild(createItem(task, i + 1))
  })
}

/** 创建一条任务 DOM */
function createItem(task, num) {
  var li = document.createElement('li')
  li.className = 'task-item' + (task.done ? ' is-done' : '')
  li.dataset.id = task.id
  if (state.draggingId === task.id) li.classList.add('is-dragging')

  /* 仅按住把手时允许拖动整行 */
  var handleEnabled = false

  /* 编号 */
  var numEl = document.createElement('span')
  numEl.className = 'task-num'
  numEl.setAttribute('aria-hidden', 'true')
  numEl.textContent = num + '.'
  li.appendChild(numEl)

  /* 勾选框 */
  var check = document.createElement('input')
  check.type = 'checkbox'
  check.className = 'task-check'
  check.checked = task.done
  check.setAttribute('aria-label', task.done ? '标记为待办' : '标记为已完成')
  check.addEventListener('change', function () {
    updateList(function (list) {
      return list.map(function (t) {
        return t.id === task.id ? { id: t.id, text: t.text, done: !t.done } : t
      })
    })
  })
  li.appendChild(check)

  /* 任务文字 */
  var text = document.createElement('span')
  text.className = 'task-text'
  text.textContent = task.text
  li.appendChild(text)

  /* 拖拽把手 */
  var handle = document.createElement('button')
  handle.type = 'button'
  handle.className = 'task-handle'
  handle.title = '拖动调整顺序'
  handle.setAttribute('aria-label', '拖动调整顺序')
  handle.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
    '<circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/>' +
    '<circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/></svg>'
  handle.addEventListener('mousedown', function () { handleEnabled = true })
  handle.addEventListener('mouseup', function () { handleEnabled = false })
  li.appendChild(handle)

  /* 删除按钮 */
  var del = document.createElement('button')
  del.type = 'button'
  del.className = 'task-del'
  del.title = '删除任务'
  del.setAttribute('aria-label', '删除任务')
  del.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
    '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' +
    '<path d="M10 11v6"/><path d="M14 11v6"/></svg>'
  del.addEventListener('click', function () {
    updateList(function (list) {
      return list.filter(function (t) { return t.id !== task.id })
    })
  })
  li.appendChild(del)

  /* 拖拽排序事件 */
  li.addEventListener('dragstart', function (e) {
    if (!handleEnabled) {
      e.preventDefault()
      return
    }
    e.dataTransfer.effectAllowed = 'move'
    state.draggingId = task.id
    render()
  })
  li.addEventListener('dragenter', function () {
    if (!state.draggingId || state.draggingId === task.id) return
    var fromId = state.draggingId
    updateList(function (list) {
      var vis = filterTasks(list)
      var from = vis.findIndex(function (t) { return t.id === fromId })
      var to = vis.findIndex(function (t) { return t.id === task.id })
      if (from < 0 || to < 0) return list
      var next = vis.slice()
      next.splice(from, 1)
      next.splice(to, 0, vis[from])
      return commitReorder(list, next)
    })
  })
  li.addEventListener('dragover', function (e) { e.preventDefault() })
  li.addEventListener('drop', function (e) { e.preventDefault() })
  li.addEventListener('dragend', function () {
    handleEnabled = false
    state.draggingId = null
    render()
  })

  return li
}

/* ---------- 事件绑定 ---------- */

el.tabs.forEach(function (btn) {
  btn.addEventListener('click', function () {
    state.tab = btn.dataset.tab
    render()
  })
})

el.datePicker.value = state.date
el.datePicker.addEventListener('change', function () {
  state.date = el.datePicker.value || todayStr()
  render()
})

el.todayBtn.addEventListener('click', function () {
  state.date = todayStr()
  el.datePicker.value = state.date
  render()
})

el.chips.forEach(function (chip) {
  chip.addEventListener('click', function () {
    state.filter = chip.dataset.filter
    render()
  })
})

el.addForm.addEventListener('submit', function (e) {
  e.preventDefault()
  var text = el.taskInput.value.trim()
  if (!text) {
    /* 空输入：抖动提示并聚焦 */
    el.taskInput.classList.remove('shake')
    void el.taskInput.offsetWidth
    el.taskInput.classList.add('shake')
    el.taskInput.focus()
    return
  }
  var task = { id: newId(), text: text, done: false }
  updateList(function (list) { return list.concat([task]) })
  el.taskInput.value = ''
  el.taskInput.focus()
  /* 新任务滚入视野 */
  requestAnimationFrame(function () {
    el.taskScroll.scrollTop = el.taskScroll.scrollHeight
  })
})

/* ---------- 启动 ---------- */
render()
