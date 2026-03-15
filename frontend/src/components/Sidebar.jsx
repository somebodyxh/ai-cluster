import { useEffect, useState, useCallback } from 'react'
import useStore from '../store'
import { getProjects, createProject, deleteProject, switchProject } from '../api'

export default function Sidebar() {
  const { projects, setProjects, currentProject, setCurrentProject,
          setMessages, mode, setMode } = useStore()
  const [newName,   setNewName]   = useState('')
  const [showForm,  setShowForm]  = useState(false)
  const [loading,   setLoading]   = useState(false)

  // useCallback 防止 useEffect 依赖闭包问题
  const handleSwitch = useCallback(async (name) => {
    const data = await switchProject(name)
    setCurrentProject(name)
    setMessages(data.history || [])   // setMessages 内部会重置 isStreaming
  }, [setCurrentProject, setMessages])

  useEffect(() => {
    getProjects().then(data => {
      setProjects(data.projects)
      if (data.projects.length > 0) {
        // 默认选中最新的（列表末尾）
        handleSwitch(data.projects[data.projects.length - 1])
      }
    })
  }, [handleSwitch, setProjects])

  async function handleCreate() {
    const name = newName.trim() || `对话 ${projects.length + 1}`
    setLoading(true)
    await createProject(name)
    const data = await getProjects()
    setProjects(data.projects)
    setShowForm(false)
    setNewName('')
    setLoading(false)
    await handleSwitch(name)
  }

  async function handleDelete() {
    if (!currentProject) return
    await deleteProject(currentProject)
    const data = await getProjects()
    setProjects(data.projects)
    if (data.projects.length > 0) {
      // 切换到最新的对话
      await handleSwitch(data.projects[data.projects.length - 1])
    } else {
      setCurrentProject(null)
      setMessages([])
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-logo">⚡</span>
        <span className="sidebar-title">AI Cluster</span>
      </div>

      {/* 模式切换 */}
      <div className="mode-row">
        <button
          className={`mode-btn ${mode === 'chat' ? 'active' : ''}`}
          onClick={() => setMode('chat')}
        >
          💬 对话
        </button>
        <button
          className={`mode-btn ${mode === 'agent' ? 'active' : ''}`}
          onClick={() => setMode('agent')}
        >
          ⚡ Agent
        </button>
      </div>

      {/* 设置入口 */}
      <button
        className={`mode-btn ${mode === 'settings' ? 'active' : ''}`}
        style={{ marginTop: 5, width: '100%' }}
        onClick={() => setMode('settings')}
      >
        ⚙️ 配置 &amp; 模型
      </button>

      <div className="sidebar-divider" />

      {/* 新建对话 */}
      {showForm ? (
        <div className="new-form">
          <input
            className="sidebar-input"
            placeholder="输入名称…"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            autoFocus
          />
          <div className="form-btns">
            <button className="btn-primary" onClick={handleCreate} disabled={loading}>
              {loading ? '…' : '创建'}
            </button>
            <button className="btn-ghost" onClick={() => setShowForm(false)}>取消</button>
          </div>
        </div>
      ) : (
        <button className="new-btn" onClick={() => setShowForm(true)}>
          ＋ 新对话
        </button>
      )}

      {/* 对话列表 */}
      <div className="list-label">历史对话</div>
      <div className="project-list">
        {[...projects].reverse().map(name => (
          <button
            key={name}
            className={`project-item ${name === currentProject ? 'active' : ''}`}
            onClick={() => handleSwitch(name)}
            title={name}
          >
            <span className="project-icon">
              {name === currentProject ? '▶' : '○'}
            </span>
            <span className="project-name">
              {name.length > 18 ? name.slice(0, 18) + '…' : name}
            </span>
          </button>
        ))}
      </div>

      <div className="sidebar-spacer" />
      <div className="sidebar-divider" />

      <button className="delete-btn" onClick={handleDelete}>
        ✕ 删除当前对话
      </button>
    </aside>
  )
}