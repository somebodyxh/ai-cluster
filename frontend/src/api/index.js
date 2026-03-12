const BASE = 'http://localhost:8000'

// ── 对话管理 ──────────────────────────────────────────────────

export async function getProjects() {
  const res = await fetch(`${BASE}/projects/list`)
  return res.json()
}

export async function createProject(name) {
  const res = await fetch(`${BASE}/projects/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function deleteProject(name) {
  const res = await fetch(`${BASE}/projects/delete/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  return res.json()
}

export async function switchProject(name) {
  const res = await fetch(`${BASE}/projects/switch/${encodeURIComponent(name)}`, {
    method: 'POST',
  })
  return res.json()
}

// ── 普通对话（SSE 流式）──────────────────────────────────────
// 后端用 json.dumps 编码每个 chunk，这里对应用 JSON.parse 解析

export function sendChat(projectName, message, webSearch, onChunk, onDone, onError) {
  fetch(`${BASE}/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_name: projectName, message, web_search: webSearch }),
  })
    .then(res => {
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) { onDone(); return }

          const text  = decoder.decode(value)
          const lines = text.split('\n')

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const chunk = JSON.parse(line.slice(6))   // 后端 json.dumps 编码
              if (chunk === '[DONE]') { onDone(); return }
              if (chunk) onChunk(chunk)
            } catch {
              // 解析失败跳过这行
            }
          }
          read()
        }).catch(onError)
      }
      read()
    })
    .catch(onError)
}

// ── Agent ──────────────────────────────────────────────────────

export async function agentDecompose(projectName, message) {
  const res = await fetch(`${BASE}/agent/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_name: projectName, message }),
  })
  return res.json()
}

export async function getAgentStatus(projectName) {
  const res = await fetch(`${BASE}/agent/status/${encodeURIComponent(projectName)}`)
  return res.json()
}

export async function cancelAgent(projectName) {
  const res = await fetch(`${BASE}/agent/cancel/${encodeURIComponent(projectName)}`, {
    method: 'POST',
  })
  return res.json()
}

// ── 配置 ───────────────────────────────────────────────────────

export async function getPlatformConfig() {
  const res = await fetch(`${BASE}/config/platform/current`)
  return res.json()
}

export async function setPlatformMode(mode) {
  const res = await fetch(`${BASE}/config/platform/set`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  return res.json()
}

export async function getPlatformOptions() {
  const res = await fetch(`${BASE}/config/platform/options`)
  return res.json()
}

export async function getModelConfig() {
  const res = await fetch(`${BASE}/config/models/current`)
  return res.json()
}

export async function updateModels() {
  const res = await fetch(`${BASE}/config/models/update`, { method: 'POST' })
  return res.json()
}

export async function getSystemStatus() {
  const res = await fetch(`${BASE}/config/status`)
  return res.json()
}