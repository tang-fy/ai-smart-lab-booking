<template>
  <div>
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div style="font-size: 16px; font-weight: bold">AI智能助手</div>
          <el-tag size="small" type="info">可查规则 / 查实验室 / 帮你预约</el-tag>
        </div>
      </template>
      <div
        ref="listRef"
        style="
          height: 480px;
          overflow-y: auto;
          padding: 8px 4px;
          background-color: #fafafa;
          border-radius: 6px;
        "
      >
        <div
          v-for="(item, index) in messages"
          :key="index"
          :style="{
            display: 'flex',
            justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
            marginBottom: '12px'
          }"
        >
          <div
            :style="{
              maxWidth: '70%',
              padding: '10px 12px',
              borderRadius: '8px',
              backgroundColor: item.role === 'user' ? '#409eff' : '#fff',
              color: item.role === 'user' ? '#fff' : '#333',
              lineHeight: '1.6',
              boxShadow: '0 1px 2px rgba(0, 0, 0, 0.06)'
            }"
          >
            <div
              v-if="item.role === 'assistant' && item.status"
              style="display: flex; align-items: center; gap: 6px; color: #909399; margin-bottom: 6px"
            >
              <el-icon class="is-loading"><Loading /></el-icon>
              {{ item.status }}
            </div>
            <div v-if="item.steps && item.steps.length" style="margin-bottom: 8px">
              <div
                v-for="(step, stepIndex) in item.steps"
                :key="stepIndex"
                style="font-size: 12px; color: #909399; margin-bottom: 4px"
              >
                <div style="display: flex; align-items: center; gap: 6px">
                  <el-icon v-if="step.status === 'running'" class="is-loading"><Loading /></el-icon>
                  <el-icon v-else color="#67c23a"><CircleCheck /></el-icon>
                  <span>{{ step.label }}</span>
                </div>
                <div
                  v-if="step.preview"
                  style="
                    margin-top: 4px;
                    padding: 6px 8px;
                    background-color: #f5f7fa;
                    border-radius: 4px;
                    color: #666;
                    word-break: break-all;
                  "
                >
                  {{ step.preview }}
                </div>
              </div>
            </div>
            <div v-html="parseMarkdown(item.content)"></div>
          </div>
        </div>
      </div>

      <div style="margin-top: 12px; display: flex; gap: 8px; align-items: flex-end">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          placeholder="问问实验室规则、开放时间，或说「帮我预约明天下午的实验室」..."
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.stop
        ></el-input>
        <el-button type="primary" @click="handleSend" :loading="loading">发送</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { chatStreamApi } from '@/api/ai'
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Loading } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify' // 过滤危险的 HTML，防止 XSS 攻击

const messages = ref([
  {
    role: 'assistant',
    content:
      '你好，我是实验室预约助手。可以问我规则和开放实验室，也可以说「帮我预约明天下午的实验室」，确认后我会帮你提交。',
    steps: []
  }
])
const input = ref('')
const loading = ref(false)
const listRef = ref()

const scrollToBottom = () => {
  nextTick(() => {
    const elem = listRef.value
    if (elem) elem.scrollTop = elem.scrollHeight
  })
}

const handleSend = async () => {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  const assistant = reactiveMessage()
  messages.value.push(assistant)
  loading.value = true
  scrollToBottom()

  const history = messages.value
    .filter((item) => item.content && item.content.trim())
    .map((item) => ({ role: item.role, content: item.content }))

  try {
    await chatStreamApi({ messages: history }, (event) => {
      const current = messages.value[messages.value.length - 1]
      switch (event.type) {
        case 'status':
          current.status = event.message || ''
          break
        case 'tool_start':
          current.steps.push({
            label: event.label || event.name,
            preview: '',
            status: 'running'
          })
          break
        case 'tool_end': {
          const label = event.label || event.name
          const step = [...current.steps]
            .reverse()
            .find((item) => item.label === label && item.status === 'running')
          if (step) {
            step.status = 'done'
            step.preview = event.preview || ''
          }
          break
        }
        case 'token':
          current.status = ''
          current.content += event.content || ''
          break
        case 'error':
          current.status = ''
          current.content = current.content || event.message || '对话失败，请稍后重试'
          ElMessage.error(event.message || '对话失败，请稍后重试')
          break
        case 'done':
          current.status = ''
          break
      }
      scrollToBottom()
    })
  } catch (error) {
    const current = messages.value[messages.value.length - 1]
    current.content = current.content || error?.message || '网络异常，请稍后重试'
    ElMessage.error(error?.message || '网络异常，请稍后重试')
  } finally {
    const current = messages.value[messages.value.length - 1]
    current.status = ''
    loading.value = false
    scrollToBottom()
  }
}

const reactiveMessage = () => ({
  role: 'assistant',
  content: '',
  status: '正在思考…',
  steps: []
})

// 将 markdown 字符串转换为安全的 HTML 字符串
const parseMarkdown = (text) => {
  if (!text) return ''
  marked.setOptions({ breaks: true }) // 把 \n 转换成 <br>
  const rawHtml = marked.parse(text)
  return DOMPurify.sanitize(rawHtml)
}
</script>
