<script setup lang="ts">
import { ref } from 'vue'
const question = ref('')
const answer = ref('')
const sources = ref<{index:number; content:string; similarity:number}[]>([])
const loading = ref(false)

async function ask() {
  if (!question.value.trim() || loading.value) return
  answer.value = ''; sources.value = []; loading.value = true
  try {
    const res = await fetch('http://localhost:8000/chat/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: question.value }),
    })
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const line = frame.replace(/^data: /, '').trim()
        if (!line || line === '[DONE]') continue
        try {
          const d = JSON.parse(line)
          if (d.sources) sources.value = d.sources        // 引用来源事件
          else if (d.token) answer.value += d.token        // 正文流式追加
          else if (d.error) answer.value += '\n[错误] ' + d.error
        } catch { /* 忽略半帧 */ }
      }
    }
  } finally { loading.value = false }
}
</script>

<template>
  <div class="box">
    <h2>售后知识 Copilot</h2>
    <input v-model="question" @keyup.enter="ask" placeholder="输入问题，如：退款多久到账" />
    <button @click="ask" :disabled="loading">{{ loading ? '回答中...' : '提问' }}</button>
    <pre class="answer">{{ answer }}</pre>
    <div v-if="sources.length" class="sources">
      <b>参考资料：</b>
      <div v-for="s in sources" :key="s.index" class="src">
        [{{ s.index }}] (相似度 {{ s.similarity.toFixed(2) }}) {{ s.content.slice(0, 60) }}...
      </div>
    </div>
  </div>
</template>