import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import useStore from '../store'
import { agentDecompose, getAgentStatus, cancelAgent } from '../api'

const ROLE_ICON = {
  coder:      '💻',
  reasoner:   '🧠',
  writer:     '✍️',
  aggregator: '🔗',
  searcher:   '🌐',
}

function ResultCard({ result, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const preview = result.content.slice(0, 80).replace(/\n/g, ' ')
  return (
    <div className="result-card">
      <div className="result-header collapsible" onClick={() => setOpen(o => !o)}>
        <span className="result-toggle">{open ? '▾' : '▸'}</span>
        <span>✓ {result.task_id} · {result.model_short}</span>
        {!open && (
          <span className="result-preview">
            {preview}{result.content.length > 80 ? '…' : ''}
          </span>
        )}
      </div>
      {open && (
        <div className="result-body">
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
            {result.content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}

// 历史消息里的 agent 汇总（role=assistant 的消息，纯文字展示）
function HistoryMessage({ msg }) {
  if (msg.role === 'user') {
    return <div className="agent-user-msg">👤 {msg.content}</div>
  }
  return (
    <div className="summary-card" style={{ marginBottom: 8 }}>
      <div className="summary-header">🔗 最终整合</div>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {msg.content}
      </ReactMarkdown>
    </div>
  )
}

export default function AgentPanel() {
  const { currentProject, messages, webSearch, toggleWebSearch } = useStore()

  const [input,     setInput]     = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [tasks,     setTasks]     = useState([])
  const [completed, setCompleted] = useState([])
  const [active,    setActive]    = useState([])
  const [summary,   setSummary]   = useState('')
  const [phase,     setPhase]     = useState(null)
  const [history,   setHistory]   = useState([])   // 当前会话中新完成的任务
  const [error,     setError]     = useState(null)

  const pollRef    = useRef(null)
  const bottomRef  = useRef(null)
  const pendingRef = useRef({ userMsg: '', tasks: [] })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [completed, summary, history, messages])

  useEffect(() => () => clearInterval(pollRef.current), [])

  // ── 切换项目或刷新后，检查后端是否有进行中的任务 ──────────────
  useEffect(() => {
    if (!currentProject) return

    // 重置本地 session 状态
    clearInterval(pollRef.current)
    setHistory([])
    setTasks([])
    setCompleted([])
    setActive([])
    setSummary('')
    setPhase(null)
    setError(null)
    setIsRunning(false)

    // 查一次后端，看看有没有进行中的任务
    getAgentStatus(currentProject).then(status => {
      if (!status || status.done) return

      // 有进行中的任务，恢复状态并继续轮询
      setIsRunning(true)
      setPhase(status.phase)
      setTasks(status.tasks || [])
      setCompleted(status.completed || [])
      setActive(status.active || [])
      if (status.summary_content) setSummary(status.summary_content)

      startPolling(currentProject)
    }).catch(() => {/* 没有任务，静默 */})
  }, [currentProject])

  function startPolling(projectName) {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      let status
      try {
        status = await getAgentStatus(projectName)
      } catch {
        return // 网络抖动跳过
      }

      setCompleted(status.completed || [])
      setActive(status.active || [])
      setPhase(status.phase)

      if (status.phase === 'summary_streaming' || status.phase === 'summary') {
        setSummary(status.summary_content || '')
      }

      if (status.done) {
        clearInterval(pollRef.current)
        setIsRunning(false)

        if (status.error && status.error !== '没有正在运行的Agent任务') {
          setError(status.error)
        } else {
          setHistory(prev => [...prev, {
            userMsg:   pendingRef.current.userMsg,
            tasks:     pendingRef.current.tasks,
            completed: status.completed || [],
            summary:   status.summary_content || '',
          }])
        }

        setTasks([])
        setCompleted([])
        setActive([])
        setSummary('')
        setPhase(null)
      }
    }, 1000)
  }

  async function handleSend() {
    if (!input.trim() || isRunning || !currentProject) return
    const userMsg = input.trim()
    setInput('')
    setError(null)
    setIsRunning(true)
    setTasks([])
    setCompleted([])
    setActive([])
    setSummary('')
    setPhase('decomposing')

    let data
    try {
      data = await agentDecompose(currentProject, userMsg)
    } catch {
      setError('网络错误，任务分解失败')
      setIsRunning(false)
      setPhase(null)
      return
    }

    if (!data.ok) {
      setError(data.error || '任务分解失败')
      setIsRunning(false)
      setPhase(null)
      return
    }

    setTasks(data.tasks)
    setPhase('tasks')
    pendingRef.current = { userMsg, tasks: data.tasks }
    startPolling(currentProject)
  }

  async function handleCancel() {
    clearInterval(pollRef.current)
    try { await cancelAgent(currentProject) } catch {}
    setIsRunning(false)
    setPhase(null)
    setActive([])
  }

  const textareaRef = useRef(null)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [input])

  // proj.history 里的消息（user/assistant 对），刷新或切换后仍可见
  // 过滤掉空消息
  const historyMessages = messages.filter(m => m.content?.trim())

  return (
    <div className="agent-panel">
      <div className="agent-content">

        {/* ① 后端持久化的历史消息（刷新/切换后依然可见）*/}
        {historyMessages.length > 0 && (
          <div className="history-block">
            {historyMessages.map((msg, i) => (
              <HistoryMessage key={i} msg={msg} />
            ))}
          </div>
        )}

        {/* ② 当前会话新完成的任务（含子任务卡片，默认折叠）*/}
        {history.map((h, i) => (
          <div key={i} className="history-block">
            <div className="agent-user-msg">👤 {h.userMsg}</div>
            <div className="task-badges">
              {h.tasks.map(t => (
                <span key={t.task_id} className="task-badge">
                  {ROLE_ICON[t.role] || '⚙️'} {t.task_id} · {t.role}
                </span>
              ))}
            </div>
            {h.completed.map(r => (
              <ResultCard key={r.task_id} result={r} defaultOpen={false} />
            ))}
            {h.summary && (
              <div className="summary-card">
                <div className="summary-header">🔗 最终整合</div>
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {h.summary}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}

        {/* ③ 正在运行中（子任务默认展开，能看实时输出）*/}
        {isRunning && (
          <div className="running-block">
            {phase === 'decomposing' && (
              <div className="status-badge run">⟳ 正在分解任务…</div>
            )}

            {tasks.length > 0 && (
              <div className="plan-box">
                <div className="plan-title">📋 任务计划（共 {tasks.length} 个）</div>
                {tasks.map(t => {
                  const isDone   = completed.find(c => c.task_id === t.task_id)
                  const isActive = active.includes(t.task_id)
                  return (
                    <div key={t.task_id} className="plan-item">
                      <span className="plan-role-icon">{ROLE_ICON[t.role] || '⚙️'}</span>
                      <span className="plan-task-id">{t.task_id}</span>
                      <span className="plan-role-tag">{t.role}</span>
                      {t.depends_on?.length > 0 && (
                        <span className="plan-dep">← {t.depends_on.join(', ')}</span>
                      )}
                      {isActive && <span className="status-badge run sm">运行中</span>}
                      {isDone   && <span className="status-badge ok  sm">✓</span>}
                    </div>
                  )
                })}
              </div>
            )}

            {completed.map(r => (
              <ResultCard key={r.task_id} result={r} defaultOpen={true} />
            ))}

            {(phase === 'summary_streaming' || phase === 'summary') && (
              <div className="summary-card">
                <div className="summary-header">🔗 整合结果 ⟳</div>
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {summary}
                </ReactMarkdown>
                <span className="cursor" />
              </div>
            )}
          </div>
        )}

        {error && <div className="error-hint">{error}</div>}

        {/* 空状态 */}
        {!isRunning && historyMessages.length === 0 && history.length === 0 && (
          <div className="empty-hint">发起一个复杂任务，Agent 集群自动拆解并行执行</div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="input-area">
        {isRunning ? (
          <button className="cancel-btn" onClick={handleCancel}>⏹ 停止</button>
        ) : (
          <button
            className={`web-btn ${webSearch ? 'on' : ''}`}
            onClick={toggleWebSearch}
            title={webSearch ? '关闭联网搜索' : '开启联网搜索'}
          >
            🌐
          </button>
        )}

        <textarea
          ref={textareaRef}
          className="chat-input"
          placeholder={isRunning ? '任务进行中…' : '描述一个复杂任务，Agent 集群自动拆解并行执行…'}
          value={input}
          disabled={isRunning}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          rows={1}
        />

        <button
          className={`send-btn ${isRunning ? 'disabled' : ''}`}
          onClick={handleSend}
          disabled={isRunning}
        >
          {isRunning ? '…' : '执行'}
        </button>
      </div>
    </div>
  )
}