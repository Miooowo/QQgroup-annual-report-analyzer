<template>
  <div class="container">
    <!-- 报告页面 -->
    <div v-if="isReportPage">
      <Report />
    </div>
    
    <!-- 群友分析页面 -->
    <div v-else-if="isPersonalityPage">
      <Personality />
    </div>
    
    <!-- 主应用页面 -->
    <div v-else>
      <!-- 标签页切换 -->
    <div class="tabs">
      <button 
        :class="['tab', { active: activeTab === 'upload' }]" 
        @click="activeTab = 'upload'"
      >
        上传分析
      </button>
      <button 
        :class="['tab', { active: activeTab === 'history' }]" 
        @click="activeTab = 'history'; loadReports()"
      >
        历史记录
      </button>
    </div>

    <!-- 上传分析页面 -->
    <div v-if="activeTab === 'upload'" class="tab-content">
      <!-- 步骤1: 上传文件 -->
      <div v-if="step === 1" class="card">
        <h2>QQ群年度报告分析器</h2>
        <p>上传 qq-chat-exporter 导出的 JSON，系统将自动分析并生成年度报告</p>
        
        <div class="card" style="margin-top: 20px;">
          <h3>选词模式</h3>
          <div class="mode-selector">
            <label class="mode-option">
              <input type="radio" v-model="autoSelect" :value="false" />
              <div class="mode-content">
                <strong>🎯 手动选词</strong>
                <p>从热词列表中自己选择最能代表这一年的词汇</p>
              </div>
            </label>
            <label class="mode-option">
              <input type="radio" v-model="autoSelect" :value="true" />
              <div class="mode-content">
                <strong>🤖 AI自动选词</strong>
                <p>AI自动选择前10个热词并生成报告</p>
              </div>
            </label>
          </div>
        </div>

        <div class="flex" style="margin-top: 20px;">
          <input type="file" accept=".json" @change="onFileChange" />
          <button :disabled="loading || !file" @click="uploadAndAnalyze">
            {{ loading ? '⏳ 分析中...' : '开始分析' }}
          </button>
        </div>
        
        <div v-if="loading" class="progress-info">
          <p>{{ loadingMessage }}</p>
        </div>
      </div>

      <!-- 步骤2: 选择词汇 (仅手动模式) -->
      <div v-if="step === 2" class="card">
        <h2>步骤2: 选择年度热词</h2>
        <div class="info-box">
          <div class="badge">群聊：{{ currentReport.chat_name }}</div>
          <div class="badge">消息数：{{ currentReport.message_count }}</div>
          <div class="badge">可选词数：{{ currentReport.available_words?.length || 0 }}</div>
          <div class="badge success">已选择：{{ selectedWords.length }} 个</div>
        </div>

        <p style="margin-top: 15px;">
          从下面的热词列表中选择最能代表这一年的词汇（<strong style="color: #dc3545;">选择10个</strong>）
        </p>

        <!-- 已选择的关键词展示 -->
        <div v-if="selectedWords.length > 0" class="selected-words-display">
          <h3 style="margin: 0 0 10px 0; font-size: 16px; color: #333;">
            📋 已选择的关键词（{{ selectedWords.length }} / 10）
          </h3>
          <div class="selected-words-list">
            <div 
              v-for="(word, index) in selectedWords" 
              :key="word"
              class="selected-word-tag"
            >
              <span class="selected-word-number">{{ index + 1 }}</span>
              <span class="selected-word-text">{{ word }}</span>
              <button 
                class="remove-word-btn"
                @click.stop="toggleWord(word)"
                title="取消选择"
              >
                ×
              </button>
            </div>
          </div>
        </div>

        <!-- 词汇列表 -->
        <div class="word-list">
          <div 
            v-for="word in paginatedWords" 
            :key="word.word"
            :class="['word-list-item', { selected: isWordSelected(word.word) }]"
            @click="toggleWord(word.word)"
          >
            <div class="word-list-header">
              <div class="word-main-info">
                <span class="word-list-text">{{ word.word }}</span>
                <span class="word-list-freq">出现 {{ word.freq }} 次</span>
              </div>
              <div class="select-indicator">
                {{ isWordSelected(word.word) ? '✓ 已选' : '点击选择' }}
              </div>
            </div>
            
            <div class="word-contributors">
              <strong>使用最多：</strong>
              <span v-for="(contributor, idx) in word.contributors.slice(0, 3)" :key="idx">
                {{ contributor.name }}({{ contributor.count }}次){{ idx < Math.min(2, word.contributors.length - 1) ? '、' : '' }}
              </span>
            </div>
            
            <div class="word-samples" v-if="word.samples && word.samples.length > 0">
              <strong>例句：</strong>
              <div class="sample-item" v-for="(sample, idx) in word.samples.slice(0, 2)" :key="idx">
                "{{ sample }}"
              </div>
            </div>
          </div>
        </div>

        <!-- 分页控制 -->
        <div class="pagination" v-if="currentReport.available_words?.length > wordsPerPage">
          <button 
            :disabled="currentWordPage <= 1" 
            @click="currentWordPage--"
          >
            上一页
          </button>
          <span>第 {{ currentWordPage }} / {{ totalWordPages }} 页</span>
          <button 
            :disabled="currentWordPage >= totalWordPages" 
            @click="currentWordPage++"
          >
            下一页
          </button>
        </div>

        <div class="selected-summary" :class="{ 'warning': selectedWords.length !== 10 }">
          已选择 {{ selectedWords.length }} / 10 个词汇
          <span v-if="selectedWords.length < 10" style="color: #dc3545; margin-left: 10px;">
            （还需选择 {{ 10 - selectedWords.length }} 个）
          </span>
          <span v-else-if="selectedWords.length === 10" style="color: #28a745; margin-left: 10px;">
            ✓ 已满足要求
          </span>
        </div>

        <div class="flex" style="margin-top: 20px;">
          <button @click="step = 1; resetState()">返回</button>
          <button 
            :disabled="selectedWords.length !== 10 || loading" 
            @click="finalizeReport"
            class="primary"
          >
            {{ loading ? '生成中...' : '确认选择并生成报告' }}
          </button>
        </div>
      </div>

      <!-- 步骤3: 生成完成 -->
      <div v-if="step === 3" class="card">
        <h2>✅ 报告生成完成！</h2>
        <div class="success-box">
          <p>{{ finalResult.message || '您的年度报告已成功生成并保存到数据库' }}</p>
          
          <div class="info-box" style="margin-top: 15px;">
            <div class="badge">报告ID：{{ finalResult.report_id }}</div>
          </div>
          
          <div style="margin-top: 20px;">
            <p style="margin-bottom: 10px; font-weight: 500;">🎨 选择模板风格：</p>
            <div class="template-selector">
              <div 
                v-for="template in availableTemplates" 
                :key="template.id"
                :class="['template-option', { selected: selectedTemplate === template.id }]"
                @click="selectedTemplate = template.id"
              >
                <div class="template-name">{{ template.name }}</div>
                <div class="template-desc">{{ template.description }}</div>
              </div>
            </div>
            
            <p style="margin: 15px 0 10px 0; font-weight: 500;">📊 访问您的报告：</p>
            <div class="url-display">
              {{ getTemplateReportUrl(selectedTemplate) }}
            </div>
            <div class="flex" style="margin-top: 15px; gap: 10px;">
              <button @click="openTemplateReport(selectedTemplate)" class="primary">
                🔗 立即查看报告
              </button>
              <button @click="copyTemplateUrl(selectedTemplate)">
                📋 复制链接
              </button>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background: rgba(218, 165, 32, 0.1); border-radius: 8px; border-left: 4px solid #DAA520;">
              <p style="margin: 0 0 10px 0; font-weight: 500; color: #DAA520;">🎭 群友性格锐评</p>
              <p style="margin: 0 0 10px 0; font-size: 14px; color: #666;">查看10位群友的发言风格和用词特点</p>
              <div class="flex" style="gap: 10px;">
                <button @click="openPersonalityReport(finalResult.report_id)" class="primary" style="background: #DAA520; color: #1a1a1a;">
                  🔗 查看群友锐评
                </button>
                <button @click="copyPersonalityUrl(finalResult.report_id)">
                  📋 复制链接
                </button>
              </div>
            </div>
          </div>

          <div class="flex" style="margin-top: 30px;">
            <button @click="step = 1; resetState()">创建新报告</button>
            <button @click="activeTab = 'history'; loadReports()" class="primary">
              查看所有报告
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 历史记录页面 -->
    <div v-if="activeTab === 'history'" class="tab-content">
      <div class="card">
        <div class="history-header">
          <h2>历史报告</h2>
          <button 
            v-if="reports.data && reports.data.length > 0" 
            @click="deleteAllReports" 
            class="danger delete-all-btn"
          >
            🗑️ 一键删除所有
          </button>
        </div>
        
        <div class="search-box">
          <input 
            v-model="searchQuery" 
            placeholder="搜索群聊名称..." 
            @keyup.enter="loadReports()"
          />
          <button @click="loadReports()">搜索</button>
        </div>

        <div v-if="loadingReports" class="loading">加载中...</div>

        <div v-else-if="reports.data && reports.data.length > 0" class="reports-list">
          <div v-for="report in reports.data" :key="report.id" class="report-item">
            <div class="report-header">
              <h3>{{ report.chat_name }}</h3>
              <span class="report-date">{{ formatDate(report.created_at) }}</span>
            </div>
            <div class="report-info">
              <span class="badge">消息数：{{ report.message_count }}</span>
              <span class="badge">报告ID：{{ report.report_id }}</span>
            </div>
            <div class="report-url">
              <code>{{ getReportUrl(report.report_id) }}</code>
            </div>
            <div class="report-actions">
              <button @click="openReport(report.report_id)" class="primary">查看报告</button>
              <button @click="openPersonalityReport(report.report_id)" style="background: #DAA520; color: #1a1a1a;">🎭 群友锐评</button>
              <button @click="copyReportUrl(report.report_id)">复制链接</button>
              <button @click="deleteReport(report.report_id)" class="danger">删除</button>
            </div>
          </div>

          <!-- 分页 -->
          <div class="pagination" v-if="reports.total > reports.page_size">
            <button 
              :disabled="reports.page <= 1" 
              @click="changePage(reports.page - 1)"
            >
              上一页
            </button>
            <span>第 {{ reports.page }} / {{ Math.ceil(reports.total / reports.page_size) }} 页</span>
            <button 
              :disabled="reports.page >= Math.ceil(reports.total / reports.page_size)" 
              @click="changePage(reports.page + 1)"
            >
              下一页
            </button>
          </div>
        </div>

        <div v-else class="empty-state">
          <p>暂无报告记录</p>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import axios from 'axios'
import { reactive, ref, computed, onMounted } from 'vue'
import Report from './Report.vue'
import Personality from './Personality.vue'

// API基础URL
const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const SITE_URL = window.location.origin

// 状态管理
const activeTab = ref('upload')
const step = ref(1) // 1=上传, 2=选词, 3=完成
const file = ref(null)
const loading = ref(false)
const loadingMessage = ref('')
const loadingReports = ref(false)
const autoSelect = ref(false)  // 是否AI自动选词

// 当前报告数据
const currentReport = ref(null)
const selectedWords = ref([])
const finalResult = ref({})
const aiComments = ref({})
const showAIComments = ref(false)

// 词汇选择分页
const currentWordPage = ref(1)
const wordsPerPage = 10

// 计算分页后的词汇列表
const paginatedWords = computed(() => {
  if (!currentReport.value?.available_words) return []
  const start = (currentWordPage.value - 1) * wordsPerPage
  const end = start + wordsPerPage
  return currentReport.value.available_words.slice(start, end)
})

// 计算总页数
const totalWordPages = computed(() => {
  if (!currentReport.value?.available_words) return 0
  return Math.ceil(currentReport.value.available_words.length / wordsPerPage)
})

// 历史报告
const reports = ref({ data: [], total: 0, page: 1, page_size: 20 })
const searchQuery = ref('')

// 本地存储的报告ID列表（实现历史记录隔离）
const MY_REPORTS_KEY = 'my_report_ids'

// 模板相关
const availableTemplates = ref([])
const selectedTemplate = ref('classic')

// 加载可用模板列表
const loadTemplates = async () => {
  try {
    const { data } = await axios.get(`${API_BASE}/templates`)
    availableTemplates.value = data.templates || []
    if (availableTemplates.value.length > 0) {
      selectedTemplate.value = availableTemplates.value[0].id
    }
  } catch (err) {
    console.error('加载模板失败:', err)
    // 使用默认模板
    availableTemplates.value = [{
      id: 'classic',
      name: '模板1',
      description: '最初的模板'
    }]
  }
}

// 获取指定模板的报告URL
const getTemplateReportUrl = (templateId) => {
  if (!finalResult.value.report_id) return ''
  return `${SITE_URL}/report/${templateId}/${finalResult.value.report_id}`
}

// 打开指定模板的报告
const openTemplateReport = (templateId) => {
  if (!finalResult.value.report_id) return
  window.open(`/report/${templateId}/${finalResult.value.report_id}`, '_blank')
}

// 复制指定模板的URL
const copyTemplateUrl = async (templateId) => {
  const url = getTemplateReportUrl(templateId)
  try {
    await navigator.clipboard.writeText(url)
    alert('链接已复制到剪贴板')
  } catch (err) {
    prompt('请手动复制链接：', url)
  }
}

// 保存报告ID到本地存储
const saveMyReport = (reportId) => {
  try {
    const myReports = JSON.parse(localStorage.getItem(MY_REPORTS_KEY) || '[]')
    if (!myReports.includes(reportId)) {
      myReports.push(reportId)
      localStorage.setItem(MY_REPORTS_KEY, JSON.stringify(myReports))
    }
  } catch (e) {
    console.error('保存报告ID失败:', e)
  }
}

// 获取本地存储的报告ID列表
const getMyReports = () => {
  try {
    return JSON.parse(localStorage.getItem(MY_REPORTS_KEY) || '[]')
  } catch (e) {
    console.error('读取报告ID失败:', e)
    return []
  }
}

// 判断是否为报告页面
const isReportPage = computed(() => {
  return window.location.pathname.startsWith('/report/')
})

// 判断是否为群友分析页面
const isPersonalityPage = computed(() => {
  return window.location.pathname.startsWith('/personality/')
})

// 计算报告URL
const reportUrl = computed(() => {
  if (!finalResult.value.report_id) return ''
  return `${SITE_URL}/report/${finalResult.value.report_id}`
})

// 获取报告URL
const getReportUrl = (reportId) => {
  return `${SITE_URL}/report/${reportId}`
}

// 打开报告
const openReport = (reportId) => {
  window.open(`/report/${reportId}`, '_blank')
}

// 复制报告URL
const copyReportUrl = async (reportId) => {
  const url = getReportUrl(reportId)
  try {
    await navigator.clipboard.writeText(url)
    alert('链接已复制到剪贴板')
  } catch (err) {
    prompt('请手动复制链接：', url)
  }
}

// 获取群友性格锐评URL
const getPersonalityUrl = (reportId) => {
  return `${SITE_URL}/personality/${reportId}`
}

// 打开群友性格锐评页面
const openPersonalityReport = (reportId) => {
  if (!reportId) return
  window.open(`/personality/${reportId}`, '_blank')
}

// 复制群友性格锐评URL
const copyPersonalityUrl = async (reportId) => {
  const url = getPersonalityUrl(reportId)
  try {
    await navigator.clipboard.writeText(url)
    alert('链接已复制到剪贴板')
  } catch (err) {
    prompt('请手动复制链接：', url)
  }
}

// 文件选择
const onFileChange = (e) => {
  const [f] = e.target.files || []
  file.value = f || null
}

// 重置状态
const resetState = () => {
  file.value = null
  currentReport.value = null
  selectedWords.value = []
  finalResult.value = {}
  aiComments.value = {}
  showAIComments.value = false
  loadingMessage.value = ''
  currentWordPage.value = 1
}

// 计算动态超时时间
const calculateTimeout = (fileSize, useAI) => {
  // 基础超时: 60秒
  const baseTimeout = 60
  
  // 文件大小因素: 每MB增加0.5秒
  const fileSizeMB = fileSize / (1024 * 1024)
  const fileSizeTimeout = Math.ceil(fileSizeMB * 0.5)
  
  // AI因素: 使用AI额外增加90秒（选词+评论需要更多时间）
  const aiTimeout = useAI ? 90 : 0
  
  // 计算总超时时间（秒）
  let totalTimeout = baseTimeout + fileSizeTimeout + aiTimeout
  
  // 设置最小值120秒，最大值600秒（10分钟）
  totalTimeout = Math.max(120, Math.min(totalTimeout, 600))
  
  return totalTimeout * 1000 // 转换为毫秒
}

// 步骤1-3: 上传并分析
const uploadAndAnalyze = async () => {
  if (!file.value) return
  loading.value = true
  
  // 计算动态超时时间
  const timeoutMs = calculateTimeout(file.value.size, autoSelect.value)
  const timeoutSeconds = Math.ceil(timeoutMs / 1000)
  
  loadingMessage.value = autoSelect.value 
    ? `正在上传并分析，AI将自动选词并生成报告...\n（预计最多需要 ${timeoutSeconds} 秒）` 
    : `正在上传并分析，请稍候...\n（预计最多需要 ${timeoutSeconds} 秒）`
  
  console.log(`📊 文件大小: ${(file.value.size / (1024 * 1024)).toFixed(2)} MB`)
  console.log(`🤖 使用AI: ${autoSelect.value ? '是' : '否'}`)
  console.log(`⏱️ 超时设置: ${timeoutSeconds} 秒`)
  
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('auto_select', autoSelect.value ? 'true' : 'false')
    
    const { data } = await axios.post(`${API_BASE}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: timeoutMs
    })
    
    if (data.error) throw new Error(data.error)
    
    // AI自动模式：直接显示结果
    if (autoSelect.value && data.success) {
      finalResult.value = data
      // 保存到本地存储
      saveMyReport(data.report_id)
      // 加载AI评论
      try {
        const detailRes = await axios.get(`${API_BASE}/reports/${data.report_id}`)
        aiComments.value = detailRes.data.ai_comments || {}
        showAIComments.value = true
      } catch (e) {
        console.error('加载AI评论失败:', e)
      }
      step.value = 3
    } else {
      // 手动模式：进入选词页面
      currentReport.value = data
      step.value = 2
    }
  } catch (err) {
    const respErr = err?.response?.data?.error
    const msg = respErr ? `分析失败: ${respErr}` : `分析失败: ${err.message || '未知错误'}`
    alert(msg)
  } finally {
    loading.value = false
    loadingMessage.value = ''
  }
}

// 词汇选择
const isWordSelected = (word) => {
  return selectedWords.value.includes(word)
}

const toggleWord = (word) => {
  const index = selectedWords.value.indexOf(word)
  if (index > -1) {
    selectedWords.value.splice(index, 1)
  } else {
    // 限制最多选择10个词
    if (selectedWords.value.length >= 10) {
      alert('最多只能选择10个词汇')
      return
    }
    selectedWords.value.push(word)
  }
}

// 步骤4-6: 最终化报告（手动选词后）
const finalizeReport = async () => {
  if (selectedWords.value.length !== 10) {
    alert('必须选择正好10个词汇才能继续')
    return
  }
  
  loading.value = true
  
  // finalize阶段主要是AI评论生成，设置固定超时180秒（3分钟）
  const finalizeTimeout = 180 * 1000
  console.log('⏱️ Finalize超时设置: 180 秒（AI评论生成）')
  
  try {
    // 按词频排序选中的词（从高到低）
    const wordFreqMap = {}
    currentReport.value.available_words.forEach(w => {
      wordFreqMap[w.word] = w.freq
    })
    const sortedWords = [...selectedWords.value].sort((a, b) => {
      return (wordFreqMap[b] || 0) - (wordFreqMap[a] || 0)
    })
    
    const { data } = await axios.post(`${API_BASE}/finalize`, {
      report_id: currentReport.value.report_id,
      selected_words: sortedWords,
      oss_key: currentReport.value.oss_key
    }, {
      timeout: finalizeTimeout
    })
    
    if (data.error) throw new Error(data.error)
    
    finalResult.value = data
    // 保存到本地存储
    saveMyReport(data.report_id)
    
    // 加载AI评论
    try {
      const detailRes = await axios.get(`${API_BASE}/reports/${data.report_id}`)
      aiComments.value = detailRes.data.ai_comments || {}
      showAIComments.value = true
    } catch (e) {
      console.error('加载AI评论失败:', e)
    }
    
    step.value = 3
  } catch (err) {
    const respErr = err?.response?.data?.error
    const msg = respErr ? `生成失败: ${respErr}` : `生成失败: ${err.message || '未知错误'}`
    alert(msg)
  } finally {
    loading.value = false
  }
}

// 加载报告列表（只显示本地存储的报告）
const loadReports = async (page = 1) => {
  loadingReports.value = true
  try {
    const myReportIds = getMyReports()
    
    // 如果没有本地报告，直接返回空
    if (myReportIds.length === 0) {
      reports.value = { data: [], total: 0, page: 1, page_size: 20 }
      return
    }
    
    // 获取更多报告以便过滤（因为要从中筛选出本地的）
    const params = { page: 1, page_size: 100 }
    if (searchQuery.value) {
      params.chat_name = searchQuery.value
    }
    
    const { data } = await axios.get(`${API_BASE}/reports`, { params })
    
    // 只保留localStorage中的报告
    const filteredData = data.data.filter(report => 
      myReportIds.includes(report.report_id)
    )
    
    // 更新为过滤后的数据（不使用服务器端分页，因为是本地过滤）
    reports.value = {
      data: filteredData,
      total: filteredData.length,
      page: 1,
      page_size: filteredData.length || 20
    }
  } catch (err) {
    alert('加载失败: ' + (err.message || '未知错误'))
  } finally {
    loadingReports.value = false
  }
}

// 分页
const changePage = (page) => {
  loadReports(page)
}

// 删除报告
const deleteReport = async (reportId) => {
  if (!confirm('确定要删除这个报告吗？此操作不可恢复！')) return
  
  try {
    await axios.delete(`${API_BASE}/reports/${reportId}`)
    
    // 从localStorage中移除该报告ID
    const myReports = getMyReports()
    const filtered = myReports.filter(id => id !== reportId)
    localStorage.setItem(MY_REPORTS_KEY, JSON.stringify(filtered))
    
    alert('删除成功')
    loadReports(reports.value.page)
  } catch (err) {
    alert('删除失败: ' + (err.message || '未知错误'))
  }
}

// 一键删除所有报告
const deleteAllReports = async () => {
  const reportCount = reports.value.data?.length || 0
  if (reportCount === 0) {
    alert('没有可删除的报告')
    return
  }
  
  const confirmMsg = `确定要删除所有 ${reportCount} 个报告吗？\n\n此操作不可恢复！\n\n请输入"删除所有"以确认：`
  const userInput = prompt(confirmMsg)
  
  if (userInput !== '删除所有') {
    if (userInput !== null) {
      alert('输入不正确，已取消删除')
    }
    return
  }
  
  // 再次确认
  if (!confirm(`最后确认：真的要删除所有 ${reportCount} 个报告吗？\n此操作将永久删除所有报告数据！`)) {
    return
  }
  
  const myReports = getMyReports()
  if (myReports.length === 0) {
    alert('没有可删除的报告')
    return
  }
  
  let successCount = 0
  let failCount = 0
  const totalCount = myReports.length
  
  // 显示进度提示
  const progressMsg = document.createElement('div')
  progressMsg.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); z-index: 10000; text-align: center;'
  progressMsg.innerHTML = `<p>正在删除报告...</p><p>已完成: 0 / ${totalCount}</p>`
  document.body.appendChild(progressMsg)
  
  try {
    // 批量删除
    for (let i = 0; i < myReports.length; i++) {
      const reportId = myReports[i]
      try {
        await axios.delete(`${API_BASE}/reports/${reportId}`)
        successCount++
        progressMsg.innerHTML = `<p>正在删除报告...</p><p>已完成: ${i + 1} / ${totalCount}</p>`
      } catch (err) {
        console.error(`删除报告 ${reportId} 失败:`, err)
        failCount++
      }
    }
    
    // 清空localStorage
    localStorage.removeItem(MY_REPORTS_KEY)
    
    // 移除进度提示
    document.body.removeChild(progressMsg)
    
    // 显示结果
    if (failCount === 0) {
      alert(`✅ 成功删除所有 ${successCount} 个报告`)
    } else {
      alert(`⚠️ 删除完成：成功 ${successCount} 个，失败 ${failCount} 个`)
    }
    
    // 重新加载列表
    loadReports()
  } catch (err) {
    document.body.removeChild(progressMsg)
    alert('批量删除过程中发生错误: ' + (err.message || '未知错误'))
  }
}

// 格式化日期
const formatDate = (dateStr) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 页面加载时初始化
onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  border-bottom: 2px solid #e0e0e0;
}

.tab {
  padding: 10px 20px;
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  font-size: 16px;
  color: #666;
  transition: all 0.3s;
}

.tab:hover {
  color: #007bff;
}

.tab.active {
  color: #007bff;
  border-bottom-color: #007bff;
}

.tab-content {
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.mode-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  margin-top: 10px;
}

.mode-option {
  display: flex;
  align-items: flex-start;
  padding: 15px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: white;
}

.mode-option:hover {
  border-color: #007bff;
  background: #f8f9fa;
}

.mode-option input[type="radio"] {
  margin-right: 10px;
  margin-top: 2px;
}

.mode-option input[type="radio"]:checked + .mode-content {
  color: #007bff;
}

.mode-content p {
  margin: 5px 0 0 0;
  font-size: 14px;
  color: #666;
}

.progress-info {
  margin-top: 15px;
  padding: 15px;
  background: #e7f3ff;
  border-radius: 8px;
  text-align: center;
  color: #0056b3;
}

.info-box {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* 新的列表样式 */
.word-list {
  margin-top: 15px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.word-list-item {
  padding: 15px;
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.word-list-item:hover {
  border-color: #007bff;
  box-shadow: 0 2px 12px rgba(0,123,255,0.15);
}

.word-list-item.selected {
  background: #e7f3ff;
  border-color: #007bff;
}

.word-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.word-main-info {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.word-list-text {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.word-list-freq {
  font-size: 14px;
  color: #666;
}

.select-indicator {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  background: #f8f9fa;
  color: #666;
}

.word-list-item.selected .select-indicator {
  background: #007bff;
  color: white;
}

.word-contributors {
  margin-bottom: 8px;
  font-size: 14px;
  color: #555;
}

.word-contributors strong {
  color: #333;
  margin-right: 5px;
}

.word-samples {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e9ecef;
}

.word-samples strong {
  display: block;
  margin-bottom: 6px;
  color: #333;
  font-size: 14px;
}

.sample-item {
  margin: 4px 0;
  padding: 6px 10px;
  background: #f8f9fa;
  border-left: 3px solid #dee2e6;
  border-radius: 4px;
  font-size: 13px;
  color: #555;
  line-height: 1.5;
}

.badge.success {
  background: #28a745;
  color: white;
}

/* 保留旧的网格样式以备用 */
.word-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin-top: 15px;
  max-height: 400px;
  overflow-y: auto;
  padding: 10px;
  background: #f9f9f9;
  border-radius: 8px;
}

.word-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.word-item:hover {
  border-color: #007bff;
  box-shadow: 0 2px 8px rgba(0,123,255,0.2);
}

.word-item.selected {
  background: #007bff;
  color: white;
  border-color: #0056b3;
}

.word-text {
  font-weight: 500;
}

.word-freq {
  font-size: 12px;
  opacity: 0.7;
}

/* 已选择的关键词展示区域 */
.selected-words-display {
  margin-top: 20px;
  margin-bottom: 15px;
  padding: 15px;
  background: linear-gradient(135deg, #e7f3ff 0%, #f0f8ff 100%);
  border: 2px solid #007bff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,123,255,0.1);
}

.selected-words-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.selected-word-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: white;
  border: 2px solid #007bff;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  color: #0056b3;
  transition: all 0.2s;
  box-shadow: 0 1px 3px rgba(0,123,255,0.2);
}

.selected-word-tag:hover {
  background: #007bff;
  color: white;
  transform: translateY(-2px);
  box-shadow: 0 3px 8px rgba(0,123,255,0.3);
}

.selected-word-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: #007bff;
  color: white;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.selected-word-tag:hover .selected-word-number {
  background: white;
  color: #007bff;
}

.selected-word-text {
  flex: 1;
  min-width: 0;
}

.remove-word-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: #dc3545;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.remove-word-btn:hover {
  background: #dc3545;
  color: white;
  transform: scale(1.1);
}

.selected-summary {
  margin-top: 15px;
  padding: 10px;
  background: #e7f3ff;
  border-radius: 6px;
  text-align: center;
  font-weight: 500;
  color: #0056b3;
}

.selected-summary.warning {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffeaa7;
}

.success-box {
  padding: 20px;
  background: #d4edda;
  border: 1px solid #c3e6cb;
  border-radius: 8px;
}

.url-display {
  padding: 12px 15px;
  background: white;
  border: 1px solid #c3e6cb;
  border-radius: 6px;
  font-family: monospace;
  font-size: 14px;
  color: #0056b3;
  word-break: break-all;
}

.ai-comments-section {
  margin-top: 25px;
  padding-top: 20px;
  border-top: 2px solid #c3e6cb;
}

.ai-comments-section h3 {
  margin: 0 0 15px 0;
  color: #155724;
}

.ai-comment-box {
  background: white;
  padding: 15px;
  border-radius: 8px;
  border: 1px solid #c3e6cb;
}

.comment-section {
  margin-bottom: 15px;
}

.comment-section:last-child {
  margin-bottom: 0;
}

.comment-section h4 {
  margin: 0 0 10px 0;
  font-size: 16px;
  color: #155724;
}

.comment-section p {
  margin: 5px 0;
  line-height: 1.6;
}

.comment-section ul {
  margin: 5px 0;
  padding-left: 20px;
}

.comment-section li {
  margin: 5px 0;
  line-height: 1.6;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.history-header h2 {
  margin: 0;
}

.delete-all-btn {
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 6px;
  transition: all 0.3s;
}

.delete-all-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(220, 53, 69, 0.3);
}

.search-box {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.search-box input {
  flex: 1;
}

.reports-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.report-item {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.report-header h3 {
  margin: 0;
  color: #333;
}

.report-date {
  color: #666;
  font-size: 14px;
}

.report-info {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.report-url {
  margin: 10px 0;
  padding: 10px;
  background: white;
  border-radius: 4px;
  border: 1px solid #dee2e6;
}

.report-url code {
  font-size: 13px;
  color: #007bff;
  word-break: break-all;
}

.report-actions {
  display: flex;
  gap: 10px;
  margin-top: 15px;
}

.report-actions button {
  padding: 8px 16px;
  font-size: 14px;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #999;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #666;
}

button.primary {
  background: #007bff;
  color: white;
}

button.primary:hover:not(:disabled) {
  background: #0056b3;
}

button.danger {
  background: #dc3545;
  color: white;
}

button.danger:hover:not(:disabled) {
  background: #c82333;
}

/* 模板选择器样式 */
.template-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
  margin-top: 10px;
}

.template-option {
  padding: 15px;
  background: white;
  border: 2px solid #c3e6cb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.template-option:hover {
  border-color: #28a745;
  box-shadow: 0 2px 12px rgba(40,167,69,0.2);
}

.template-option.selected {
  background: #d4edda;
  border-color: #28a745;
  box-shadow: 0 3px 15px rgba(40,167,69,0.3);
}

.template-name {
  font-size: 16px;
  font-weight: 600;
  color: #155724;
  margin-bottom: 5px;
}

.template-desc {
  font-size: 14px;
  color: #666;
}
</style>
