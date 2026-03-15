import { useState, useEffect } from 'react'
import {
  getPlatformOptions, setPlatformMode,
  getModelConfig, updateModels, getSystemStatus
} from '../api'

export default function SettingsPanel() {
  const [status,       setStatus]       = useState(null)
  const [platformOpts, setPlatformOpts] = useState([])
  const [currentMode,  setCurrentMode]  = useState('')
  const [modelConfig,  setModelConfig]  = useState(null)
  const [updating,     setUpdating]     = useState(false)
  const [toast,        setToast]        = useState(null)
  const [loading,      setLoading]      = useState(true)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const [opts, cfg, sys] = await Promise.all([
        getPlatformOptions(),
        getModelConfig(),
        getSystemStatus(),
      ])
      setPlatformOpts(opts.options || [])
      setCurrentMode(opts.current  || '')
      setModelConfig(cfg)
      setStatus(sys)
    } catch {
      showToast('加载配置失败', 'err')
    }
    setLoading(false)
  }

  async function handleSetPlatform(mode) {
    setCurrentMode(mode)
    const res = await setPlatformMode(mode)
    if (res.ok) showToast(`已切换至 ${res.label}`, 'ok')
    else        showToast(res.error || '切换失败', 'err')
    // 刷新状态
    const sys = await getSystemStatus()
    setStatus(sys)
  }

  async function handleUpdateModels() {
    setUpdating(true)
    const res = await updateModels()
    setUpdating(false)
    if (res.ok) {
      showToast(res.message, 'ok')
      // 稍等一下再刷新，因为后端是后台任务
      setTimeout(async () => {
        const cfg = await getModelConfig()
        setModelConfig(cfg)
      }, 3000)
    } else {
      showToast(res.error || '更新失败', 'err')
    }
  }

  function showToast(msg, type = 'ok') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  if (loading) return (
    <div className="settings-panel">
      <div className="settings-loading">加载中…</div>
    </div>
  )

  const mapping = modelConfig?.default_mapping || {}

  return (
    <div className="settings-panel">
      <div className="settings-content">

        {/* Toast */}
        {toast && (
          <div className={`settings-toast ${toast.type}`}>{toast.msg}</div>
        )}

        {/* 标题 */}
        <div className="settings-title">⚙️ 系统配置</div>

        {/* 系统状态 */}
        {status && (
          <div className="settings-section">
            <div className="section-label">系统状态</div>
            <div className="status-row">
              <span className="status-key">当前平台</span>
              <span className="status-val">{status.platform}</span>
            </div>
            <div className="status-row">
              <span className="status-key">模型更新时间</span>
              <span className="status-val">{status.models_updated}</span>
            </div>
            <div className="status-row">
              <span className="status-key">需要更新</span>
              <span className={`status-val ${status.needs_update ? 'warn' : 'ok'}`}>
                {status.needs_update ? '是' : '否'}
              </span>
            </div>
          </div>
        )}

        {/* 平台切换 */}
        <div className="settings-section">
          <div className="section-label">平台模式</div>
          <div className="platform-options">
            {platformOpts.map(opt => (
              <button
                key={opt.value}
                className={`platform-btn ${currentMode === opt.value ? 'active' : ''}`}
                onClick={() => handleSetPlatform(opt.value)}
              >
                <span className="platform-icon">
                  {opt.value === 'domestic' ? '🇨🇳' :
                   opt.value === 'foreign'  ? '🌍' : '⚖️'}
                </span>
                <span className="platform-label">{opt.label}</span>
                {currentMode === opt.value && <span className="platform-check">✓</span>}
              </button>
            ))}
          </div>
        </div>

        {/* 模型配置 */}
        <div className="settings-section">
          <div className="section-label-row">
            <span className="section-label">当前模型分配</span>
            {modelConfig?.last_update && (
              <span className="section-meta">更新于 {modelConfig.last_update}</span>
            )}
          </div>

          {Object.keys(mapping).length === 0 ? (
            <div className="empty-mapping">暂无模型配置，点击下方按钮更新</div>
          ) : (
            <div className="model-table">
              {Object.entries(mapping).map(([role, model]) => (
                <div key={role} className="model-row">
                  <span className="model-role">
                    {role === 'writer'     ? '✍️ writer'     :
                     role === 'coder'      ? '💻 coder'      :
                     role === 'reasoner'   ? '🧠 reasoner'   :
                     role === 'aggregator' ? '🔗 aggregator' :
                     role === 'searcher'   ? '🌐 searcher'   : role}
                  </span>
                  <span className="model-name">{model}</span>
                </div>
              ))}
            </div>
          )}

          <button
            className={`update-btn ${updating ? 'loading' : ''}`}
            onClick={handleUpdateModels}
            disabled={updating}
          >
            {updating ? '⟳ 更新中…' : '🔄 自动更新模型配置'}
          </button>
          <div className="update-hint">
            更新后台异步执行，完成后约 3 秒自动刷新显示
          </div>
        </div>

      </div>
    </div>
  )
}