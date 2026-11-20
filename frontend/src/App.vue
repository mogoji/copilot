<script setup lang="ts">
import { ref } from 'vue'
const question = ref('')
const answer = ref('')
const loading = ref(false)

async function ask() {
  if (!question.value.trim() || loading.value) return
  answer.value = ''
  loading.value = true
  try {
    const res = await fetch('http://localhost:8000/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
        if (!frame.startsWith('data: ')) continue
        const data = frame.slice(6)
        if (data === '[DONE]') { loading.value = false; return }
        const obj = JSON.parse(data)
        if (obj.token) answer.value += obj.token
      }
    }
  } catch (e) {
    answer.value = '出错：' + String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <h2>售后知识 Copilot · Day1</h2>
  <input v-model="question" placeholder="输入问题，回车发送" @keyup.enter="ask" />
  <button @click="ask" :disabled="loading">{{ loading ? '生成中…' : '发送' }}</button>
  <div class="answer">{{ answer }}</div>
</template>

<style scoped>
input { width: 60%; padding: 8px; }
button { padding: 8px 16px; margin-left: 8px; }
.answer { margin-top: 16px; white-space: pre-wrap; line-height: 1.7; }
</style>