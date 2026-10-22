import request from '@/utils/request'
import { getToken } from '@/utils/auth'

export function chatApi(data) {
  return request({
    url: '/api/ai/chat',
    method: 'post',
    data,
    timeout: 60000
  })
}

/**
 * 流式对话（SSE）
 * @param {Object} data 请求体 { messages: [{ role, content }] }
 * @param {(event: Object) => void} onEvent 每收到一帧就回调一次
 */
export async function chatStreamApi(data, onEvent) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(`${baseURL}/api/ai/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken() || ''}`
    },
    body: JSON.stringify(data)
  })

  if (!response.ok) {
    let message = `请求失败(${response.status})`
    try {
      const err = await response.json()
      message = err?.message || message
    } catch {
      // 忽略解析失败
    }
    throw new Error(message)
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('text/event-stream')) {
    let message = '服务端没有返回流式数据'
    try {
      const res = await response.json()
      message = res?.message || message
    } catch {
      // 忽略解析失败
    }
    throw new Error(message)
  }

  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index = buffer.indexOf('\n\n')
    while (index !== -1) {
      const frame = buffer.slice(0, index).trim()
      buffer = buffer.slice(index + 2)
      if (frame.startsWith('data:')) {
        const raw = frame.slice(5).trim()
        if (raw) {
          try {
            onEvent(JSON.parse(raw))
          } catch {
            // 忽略不完整/非法帧
          }
        }
      }
      index = buffer.indexOf('\n\n')
    }
  }
}
