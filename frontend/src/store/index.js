import { create } from 'zustand'

const useStore = create((set) => ({
  currentProject: null,
  projects:       [],
  mode:           'chat',      // 'chat' | 'agent'
  messages:       [],
  isStreaming:     false,
  webSearch:       false,

  setCurrentProject: (name) => set({ currentProject: name }),
  setProjects:       (list) => set({ projects: list }),
  setMode:           (mode) => set({ mode }),
  setIsStreaming:    (val)  => set({ isStreaming: val }),
  toggleWebSearch:   ()    => set((s) => ({ webSearch: !s.webSearch })),

  // 切换对话时同时重置消息列表和流状态，防止 isStreaming 跨对话残留
  setMessages: (msgs) => set({ messages: msgs, isStreaming: false }),

  addMessage: (msg) => set((s) => ({
    messages: [...s.messages, msg],
  })),

  // 流式追加到最后一条 assistant 消息
  updateLastMessage: (chunk) => set((s) => {
    const msgs = [...s.messages]
    if (msgs.length === 0) return {}
    const last = msgs[msgs.length - 1]
    msgs[msgs.length - 1] = { ...last, content: last.content + chunk }
    return { messages: msgs }
  }),
}))

export default useStore