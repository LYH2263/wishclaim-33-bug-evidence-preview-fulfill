<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" :disabled="locked" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="claim" :disabled="locked">认领锁定</button>
      <button class="ghost" @click="release" :disabled="w.status !== 'claimed'">释放</button>
    </div>

    <!-- claimed：举证表单 + 预览，预览不改 status -->
    <section v-if="w.status === 'claimed'" class="evidence-box">
      <h3 class="serif">核销举证</h3>
      <label class="tag">履约渠道</label>
      <select v-model="form.channel">
        <option value="" disabled>选择渠道…</option>
        <option v-for="ch in channels" :key="ch.key" :value="ch.key">{{ ch.label }}（{{ ch.hint }}）</option>
      </select>
      <input v-model="form.reference" placeholder="凭证号 / 订单号（必填）" />
      <textarea v-model="form.note" rows="2" placeholder="备注（选填）"></textarea>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="ghost" @click="preview">预览举证包</button>
        <button @click="fulfill">提交核销</button>
      </div>

      <!-- 预览区：摘要 + 渠道枚举，persisted=false -->
      <div v-if="previewData" class="preview-box">
        <p class="tag">预览（未写库，状态仍 {{ previewData.status }}）</p>
        <p>举证摘要：<strong>{{ previewData.summary || '（尚不完整）' }}</strong></p>
        <ul class="channel-enum">
          <li v-for="ch in previewData.channels" :key="ch.key"
              :class="{ picked: ch.key === previewData.selected }">
            {{ ch.key }} · {{ ch.label }}
          </li>
        </ul>
        <p v-if="!previewDataReady" class="err">
          还缺：{{ previewData.missing.map(m => missingLabel(m)).join('、') || '有效内容' }}
        </p>
        <p v-else class="tag">举证完整，可以提交核销。</p>
      </div>
    </section>

    <!-- fulfilled：举证区只读钉住，核销后禁止再改 -->
    <section v-else-if="w.evidence_view" class="evidence-box frozen">
      <h3 class="serif">核销举证（已冻结）</h3>
      <p>举证摘要：<strong>{{ w.evidence_summary }}</strong></p>
      <dl class="evidence-dl">
        <div><dt>渠道</dt><dd>{{ w.evidence_view.channel_label }}</dd></div>
        <div><dt>凭证号</dt><dd>{{ w.evidence_view.reference }}</dd></div>
        <div v-if="w.evidence_view.note"><dt>备注</dt><dd>{{ w.evidence_view.note }}</dd></div>
        <div><dt>核销时间</dt><dd>{{ w.evidence_view.fulfilled_at }}</dd></div>
      </dl>
    </section>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const err = ref('')
const channels = ref([])
const form = ref({ channel: '', reference: '', note: '' })
const previewData = ref(null)

const locked = computed(() => w.value.status === 'fulfilled')
const previewDataReady = computed(() => previewData.value?.ready === true)

const MISSING_LABELS = { channel: '履约渠道', reference: '凭证号' }
function missingLabel(k) { return MISSING_LABELS[k] || k }

async function loadChannels() {
  const r = await api('/fulfillment/channels')
  channels.value = r.channels
}

async function load() {
  w.value = await api('/wishes/' + props.id)
  previewData.value = null
}

async function claim() {
  err.value = ''
  try { await api('/wishes/' + props.id + '/claim', { method: 'POST', body: JSON.stringify({ claimer: claimer.value }) }); await load() }
  catch (e) { err.value = e.message }
}
async function release() {
  err.value = ''
  try { await api('/wishes/' + props.id + '/release', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}

async function preview() {
  err.value = ''; previewData.value = null
  try { previewData.value = await api('/wishes/' + props.id + '/fulfill/preview', { method: 'POST', body: JSON.stringify(form.value) }) }
  catch (e) { err.value = e.message }
}

async function fulfill() {
  err.value = ''
  try {
    await api('/wishes/' + props.id + '/fulfill', { method: 'POST', body: JSON.stringify(form.value) })
    await load()
  } catch (e) {
    // 被拒后后端零写入、status 仍 claimed：不 reload，表单与墙卡都保持认领中
    const d = e.payload?.detail
    if (d?.error === 'incomplete_evidence') {
      const names = (d.missing || []).map(missingLabel)
      err.value = names.length
        ? '提交失败，还缺：' + names.join('、')
        : '提交失败：举证不完整'
    } else if (d?.error === 'already_fulfilled') {
      err.value = '已核销并冻结，渠道与凭证不可再改'
    } else {
      err.value = e.message
    }
    // 刷新只读预览以提示缺失项（预览不写库、不改 status）
    await preview()
  }
}

onMounted(async () => { await loadChannels(); await load() })
</script>
