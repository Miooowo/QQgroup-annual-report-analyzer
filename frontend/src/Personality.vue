<template>
  <div class="personality-page-wrapper">
    <!-- 数据加载中 -->
    <div v-if="loading" class="loading-container">
      <div class="loading">
        <div class="loading-spinner"></div>
        <p>加载群友分析中...</p>
      </div>
    </div>
    
    <!-- 数据加载错误 -->
    <div v-else-if="error" class="error-container">
      <div class="error-message">
        <h2>❌ 加载失败</h2>
        <p>{{ error }}</p>
      </div>
      <button @click="loadPersonality">重新加载</button>
    </div>
    
    <!-- 群友分析内容 -->
    <div v-else-if="htmlContent" v-html="htmlContent" class="personality-content" ref="personalityContentRef"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onUnmounted } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

// ========== 数据状态 ==========
const htmlContent = ref('')
const loading = ref(true)
const error = ref(null)
const personalityContentRef = ref(null)
const generatingImage = ref(false)
const imageError = ref('')

// ========== 路由参数解析 ==========
const getReportId = () => {
  const path = window.location.pathname
  // 匹配 /personality/{reportId} 格式
  const match = path.match(/\/personality\/([^/]+)/)
  return match ? match[1] : null
}

// ========== 保存图片函数（使用后端API，与年度报告一致）==========
const saveAsImage = async () => {
  if (generatingImage.value) return
  
  generatingImage.value = true
  imageError.value = ''
  
  const button = document.querySelector('.save-button')
  const originalText = button?.textContent || '💾 保存图片'
  if (button) {
    button.textContent = '⏳ 生成中...'
    button.disabled = true
  }
  
  try {
    const reportId = getReportId()
    if (!reportId) {
      throw new Error('报告ID不存在')
    }
    
    console.log('🖼️ 请求后端生成群友分析图片...')
    
    const { data } = await axios.post(
      `${API_BASE}/reports/${reportId}/personality/image`,
      {
        format: 'for_share',  // 分享版本
        force: false  // 使用缓存
      }
    )
    
    if (data.success) {
      // 自动触发下载
      const chatName = document.querySelector('h1')?.textContent || '群友性格锐评'
      const fileName = `${chatName}_群友性格锐评_${new Date().getTime()}.png`
      const link = document.createElement('a')
      link.href = data.image_url
      link.download = fileName
      link.click()
      
      console.log('✅ 图片生成成功', data.cached ? '(来自缓存)' : '')
    } else {
      throw new Error(data.error || '图片生成失败')
    }
    
  } catch (err) {
    console.error('生成图片失败:', err)
    imageError.value = err.response?.data?.error || err.message || '生成图片失败，请重试'
    alert(imageError.value)
  } finally {
    generatingImage.value = false
    if (button) {
      button.textContent = originalText
      button.disabled = false
    }
  }
}

// ========== 加载群友分析 ==========
const loadPersonality = async () => {
  loading.value = true
  error.value = null
  
  try {
    const reportId = getReportId()
    if (!reportId) {
      throw new Error('报告ID不存在')
    }
    
    console.log('📊 加载群友分析...', reportId)
    
    const { data } = await axios.get(`${API_BASE}/reports/${reportId}/personality`)
    
    if (typeof data === 'string') {
      htmlContent.value = data
      
      // 等待DOM更新后，处理script标签和事件绑定
      await nextTick()
      
      // 检测是否为分享模式（用于截图时隐藏按钮）
      const urlParams = new URLSearchParams(window.location.search)
      const isShareMode = urlParams.get('mode') === 'share'
      
      // 将saveAsImage函数挂载到window对象，以便HTML中的onclick可以访问
      window.saveAsImage = saveAsImage
      
      // 确保所有按钮的onclick都指向window.saveAsImage
      const contentDiv = personalityContentRef.value
      if (contentDiv) {
        // 如果是分享模式，隐藏保存按钮
        if (isShareMode) {
          const saveButtons = contentDiv.querySelectorAll('.save-button')
          saveButtons.forEach(btn => {
            btn.style.display = 'none'
          })
        } else {
          const saveButtons = contentDiv.querySelectorAll('.save-button')
          saveButtons.forEach(btn => {
            btn.onclick = saveAsImage
          })
        }
      }
    } else {
      throw new Error('返回数据格式错误')
    }
    
    console.log('✅ 群友分析加载成功')
  } catch (err) {
    console.error('加载群友分析失败:', err)
    error.value = err.response?.data?.error || err.message || '加载群友分析失败，请重试'
  } finally {
    loading.value = false
  }
}

// ========== 生命周期 ==========
onMounted(() => {
  loadPersonality()
})

onUnmounted(() => {
  // 清理全局函数
  if (window.saveAsImage) {
    delete window.saveAsImage
  }
})
</script>

<style>
/* 群友分析页面包装器 - 居中并设置背景 */
.personality-page-wrapper {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0;
  margin: 0;
}

/* 群友分析内容 */
.personality-content {
  width: 100%;
  max-width: 900px;
  margin: 0 auto;
}

/* ========== 加载状态 ========== */
.loading-container, .error-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  color: #fff;
}

.loading-spinner {
  width: 50px;
  height: 50px;
  border: 4px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-message {
  text-align: center;
  padding: 40px;
  background: rgba(220, 53, 69, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(220, 53, 69, 0.3);
}

.error-message h2 {
  margin: 0 0 10px 0;
  color: #dc3545;
}

.error-message p {
  margin: 0 0 20px 0;
  color: #fff;
}

.error-container button {
  padding: 10px 20px;
  background: #dc3545;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.3s;
}

.error-container button:hover {
  background: #c82333;
}
</style>
