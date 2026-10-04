<template>
  <div class="wall">
    <h1 class="serif">已完成</h1>
    <!-- 只有 fulfilled 才会出现在这里，且每行钉同一来源的举证摘要 -->
    <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
      <h3>{{ w.title }}</h3>
      <p>{{ w.claimer }}</p>
      <p class="tag">举证：{{ w.summary || '（无摘要）' }}</p>
      <p class="tag">核销时间 {{ w.fulfilled_at || '—' }}</p>
    </article>
    <p v-if="!rows.length" class="tag">还没有已核销的愿望。</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await api('/done') })
</script>
