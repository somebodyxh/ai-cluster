import { useRef, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import useStore from '../store'
import { sendChat } from '../api'

export default function ChatPanel() {
  const {
    currentProject, messages, addMessage, updateLastMessage,
    isStreaming, setIsStreaming, webSearch, toggleWebSearch,
  } = useStore()

  const [input,          setInput]          = useState('')
  const [error,          setError]          = useState(null)
  const [compressNotice, setCompressNotice] = useState(false)
  const bottomRef   = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 自动撑高 textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [input])

  function handleSend() {
    if (!input.trim() || isStreaming || !currentProject) return
    const userMsg = input.trim()
    setInput('')
    setError(null)
    addMessage({ role: 'user',      content: userMsg })
    addMessage({ role: 'assistant', content: '' })
    setIsStreaming(true)

    sendChat(
      currentProject,
      userMsg,
      webSearch,
      (chunk) => {
        // 拦截特殊信号，不追加到消息气泡
        if (chunk === '[COMPRESSING]') {
          setCompressNotice(true)
          setTimeout(() => setCompressNotice(false), 3000)
          return
        }
        updateLastMessage(chunk)
      },
      () => setIsStreaming(false),
      () => { setIsStreaming(false); setError('网络错误，请重试') },
    )
  }

  return (
    <div className="chat-panel">
      {/* 记忆压缩提示 */}
      {compressNotice && (
        <div className="compress-notice">🧠 记忆已压缩</div>
      )}

      {/* 消息列表 */}
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-hint">开始对话吧</div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`msg-row ${msg.role === 'user' ? 'user' : 'assistant'}`}
          >
            <div className={`bubble ${msg.role}`}>
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {msg.content}
              </ReactMarkdown>
              {/* 流式光标：最后一条 assistant 消息且正在流时显示 */}
              {isStreaming && i === messages.length - 1 && msg.role === 'assistant' && (
                <span className="cursor" />
              )}
            </div>
          </div>
        ))}
        {error && <div className="error-hint">{error}</div>}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="input-area">
        <button
          className={`web-btn ${webSearch ? 'on' : ''}`}
          onClick={toggleWebSearch}
          title={webSearch ? '关闭联网搜索' : '开启联网搜索'}
        >
          🌐
        </button>
        <textarea
          ref={textareaRef}
          className="chat-input"
          placeholder={isStreaming ? '回复中…' : '有什么可以帮你…（Shift+Enter 换行）'}
          value={input}
          disabled={isStreaming}
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
          className={`send-btn ${isStreaming ? 'disabled' : ''}`}
          onClick={handleSend}
          disabled={isStreaming}
        >
          {isStreaming ? '…' : '发送'}
        </button>
      </div>
    </div>
  )
}