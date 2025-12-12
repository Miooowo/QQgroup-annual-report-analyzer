<template>
  <div class="report-page-wrapper">
    <!-- 动态加载模板组件 -->
    <component 
      v-if="report && templateComponent" 
      :is="templateComponent"
      :report="report"
      :formatNumber="formatNumber"
      :truncateText="truncateText"
      :getTitleClass="getTitleClass"
      :handleImageError="handleImageError"
      :getHourHeight="getHourHeight"
      :getPeakHour="getPeakHour"
    />
    
    <!-- 模板加载失败提示 -->
    <div v-else-if="report && !templateComponent" class="template-error-container">
      <div class="template-error">
        <h2>⚠️ 模板加载失败</h2>
        <p>无法加载模板文件，请检查模板配置</p>
        <div class="template-info">
          <p>模板ID: <code>{{ currentTemplateId }}</code></p>
          <p>报告ID: <code>{{ currentReportId }}</code></p>
        </div>
        <button @click="loadReport">重新加载</button>
      </div>
    </div>
    
    <!-- 数据加载中 -->
    <div v-else-if="loading" class="loading-container">
      <div class="loading">
        <div class="loading-spinner"></div>
        <p>加载报告数据中...</p>
      </div>
    </div>
    
    <!-- 数据加载错误 -->
    <div v-else-if="error" class="error-container">
      <div class="error-message">
        <h2>❌ 加载失败</h2>
        <p>{{ error }}</p>
      </div>
      <button @click="loadReport">重新加载</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, shallowRef } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const report = ref(null)
const loading = ref(true)
const error = ref(null)
const templateComponent = shallowRef(null)
const currentTemplateId = ref('')
const currentReportId = ref('')

// 获取路由参数（支持 /report/{id} 和 /report/{template}/{id}）
const getRouteParams = () => {
  const path = window.location.pathname
  // 尝试匹配 /report/{template}/{id}
  let match = path.match(/\/report\/([^/]+)\/([^/]+)/)
  if (match) {
    return { templateId: match[1], reportId: match[2] }
  }
  // 尝试匹配 /report/{id}
  match = path.match(/\/report\/([^/]+)/)
  if (match) {
    return { templateId: 'classic', reportId: match[1] }
  }
  return null
}

// 保持向后兼容
const getReportId = () => {
  const params = getRouteParams()
  return params ? params.reportId : null
}

// 动态加载模板组件
const loadTemplate = async (templateId) => {
  try {
    const module = await import(`./templates/${templateId}.vue`)
    templateComponent.value = module.default
  } catch (err) {
    console.warn(`模板 ${templateId} 加载失败，使用默认模板`, err)
    templateComponent.value = null
  }
}

// 加载报告数据
const loadReport = async () => {
  loading.value = true
  error.value = null
  
  try {
    const reportId = getReportId()
    if (!reportId) {
      throw new Error('报告ID不存在')
    }
    
    const { data } = await axios.get(`${API_BASE}/reports/${reportId}`)
    
    if (data.error) {
      throw new Error(data.error)
    }
    
    report.value = data
  } catch (err) {
    error.value = err.message || '加载报告失败'
    console.error('加载报告失败:', err)
  } finally {
    loading.value = false
  }
}

// 格式化数字
const formatNumber = (num) => {
  if (!num) return '0'
  return num.toLocaleString('zh-CN')
}

// 截断文本
const truncateText = (text, maxLength) => {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// 获取标题样式类
const getTitleClass = (chatName) => {
  const length = chatName ? chatName.length : 0
  if (length <= 6) return 'short-title'
  if (length <= 15) return 'medium-title'
  if (length <= 24) return 'long-title'
  return 'ultra-long-title'
}

// 处理图片加载错误
const handleImageError = (e) => {
  e.target.style.display = 'none'
}

// 获取时段高度
const getHourHeight = (hour) => {
  if (!hour) return 0
  const maxHour = Math.max(...Object.values(report.value.statistics?.hourDistribution || {}))
  return maxHour > 0 ? (hour / maxHour) * 100 : 0
}

// 获取最活跃时段
const getPeakHour = () => {
  const hourDistribution = report.value.statistics?.hourDistribution || {}
  let maxHour = 0
  let maxValue = 0
  for (const [hour, value] of Object.entries(hourDistribution)) {
    if (value > maxValue) {
      maxValue = value
      maxHour = parseInt(hour)
    }
  }
  return maxHour
}

// 页面加载时获取数据和加载模板
onMounted(async () => {
  const params = getRouteParams()
  if (params) {
    currentTemplateId.value = params.templateId
    currentReportId.value = params.reportId
    await loadTemplate(params.templateId)
  }
  loadReport()
})
</script>

<style>
/* 导入模板样式 */
@import './report-styles.css';

/* 报告页面包装器 - 居中并设置背景 */
.report-page-wrapper {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0;
  margin: 0;
}

.loading-container, .error-container, .template-error-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  color: #f5f5dc;
  text-align: center;
  padding: 20px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.loading-spinner {
  width: 50px;
  height: 50px;
  border: 4px solid rgba(212, 175, 55, 0.2);
  border-top-color: #d4af37;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading p {
  font-size: 18px;
  color: #d4af37;
  margin: 0;
}

.error-container, .template-error-container {
  gap: 20px;
}

.error-message, .template-error {
  background: rgba(0, 0, 0, 0.5);
  padding: 30px;
  border-radius: 10px;
  border: 2px solid #d4af37;
  max-width: 600px;
}

.error-message h2, .template-error h2 {
  color: #ff6b6b;
  margin: 0 0 15px 0;
  font-size: 24px;
}

.error-message p, .template-error p {
  color: #f5f5dc;
  margin: 10px 0;
  font-size: 16px;
}

.template-info {
  margin: 20px 0;
  padding: 15px;
  background: rgba(212, 175, 55, 0.1);
  border-radius: 5px;
  text-align: left;
}

.template-info p {
  margin: 5px 0;
  font-size: 14px;
}

.template-info code {
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 8px;
  border-radius: 3px;
  color: #d4af37;
  font-family: 'Courier New', monospace;
}

.error-container button, .template-error-container button {
  padding: 12px 30px;
  background: #d4af37;
  color: #000;
  border: none;
  border-radius: 5px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.3s ease;
}

.error-container button:hover, .template-error-container button:hover {
  background: #f0c14b;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(212, 175, 55, 0.3);
}

.error-container button:active, .template-error-container button:active {
  transform: translateY(0);
}
</style>
