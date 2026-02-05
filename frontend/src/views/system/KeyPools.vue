<template>
  <div>
    <div class="page-header">
      <h2>密钥池管理</h2>
      <p>管理AI模型提供商和密钥池配置</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-title">总提供商</div>
        <div class="stat-value">{{ stats.total_providers || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">总密钥池</div>
        <div class="stat-value">{{ stats.total_pools || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">总客户端</div>
        <div class="stat-value">{{ stats.total_clients || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">总容量</div>
        <div class="stat-value">{{ stats.total_capacity || 0 }}</div>
      </div>
    </div>

    <!-- 提供商实时统计 -->
    <div class="section-title" v-if="providerStats && providerStats.length > 0">各提供商实时统计</div>
    <div class="stats-cards" v-if="providerStats && providerStats.length > 0">
      <div class="stat-card" 
           v-for="stat in providerStats" 
           :key="stat.name"
           :class="{ 'warning-border': stat.usage_rate > 90 }"
      >
        <div class="stat-title">{{ stat.display_name }}</div>
        <div class="provider-stat-details">
          <div class="stat-row">
            <span class="label">密钥数:</span>
            <span class="value">{{ stat.total_keys }}</span>
          </div>
          <div class="stat-row">
            <span class="label">剩余数量:</span>
            <span class="value">{{ stat.capacity_display === '∞' ? '∞' : stat.remaining }}</span>
          </div>
          <div class="stat-row">
            <span class="label">使用占比:</span>
            <span class="value" :class="{ 'text-danger': stat.usage_rate > 90 }">
              {{ stat.has_infinite ? '0%' : stat.usage_rate.toFixed(1) + '%' }}
            </span>
          </div>
        </div>
        <div class="warning-text" v-if="stat.usage_rate > 90">
          密钥池即将不够
        </div>
      </div>
    </div>

    <!-- 提供商管理 -->
    <div class="panel">
      <div class="panel-header">
        <h3>提供商管理</h3>
        <el-button type="primary" :icon="Plus" @click="showProviderDialog">新增提供商</el-button>
      </div>
      <div class="panel-body">
        <el-table :data="providers" v-loading="loading">
          <el-table-column prop="name" label="标识符" width="120" />
          <el-table-column prop="display_name" label="显示名称" width="150" />
          <el-table-column prop="base_url" label="基础URL" min-width="200" />
          <el-table-column prop="description" label="描述" min-width="150" />
          <el-table-column prop="priority" label="优先级" width="80" />
          <el-table-column prop="is_active" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showProviderDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除该提供商？" @confirm="deleteProvider(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 密钥池管理 -->
    <div class="panel">
      <div class="panel-header">
        <h3>密钥池管理</h3>
        <div class="panel-actions">
          <el-button type="success" :icon="Plus" @click="showBatchPoolDialog">批量添加</el-button>
          <el-button type="primary" :icon="Plus" @click="showPoolDialog">新增密钥池</el-button>
        </div>
      </div>
      <div class="panel-body">
        <el-table :data="keyPools" v-loading="loading">
          <el-table-column label="提供商" width="120">
            <template #default="{ row }">
              <span v-if="row.provider">{{ row.provider.display_name }}</span>
              <span v-else>未知</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="池名称" width="150" />
          <el-table-column prop="description" label="描述" min-width="150" />
          <el-table-column label="API密钥" min-width="200">
            <template #default="{ row }">
              <span>{{ maskApiKey(row.api_key) }}</span>
              <el-button type="primary" link size="small" @click="showApiKey(row)">查看</el-button>
            </template>
          </el-table-column>
          <el-table-column label="客户端" width="120">
            <template #default="{ row }">
              {{ row.current_clients }}/{{ row.max_clients === -1 ? '∞' : row.max_clients }}
            </template>
          </el-table-column>
          <el-table-column label="使用率" width="100">
            <template #default="{ row }">
              <el-progress
                :percentage="row.max_clients === -1 ? 0 : Math.round((row.current_clients / row.max_clients) * 100)"
                :status="row.max_clients === -1 ? undefined : (row.current_clients >= row.max_clients ? 'exception' : undefined)"
                :stroke-width="8"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column label="占用状态" min-width="250">
            <template #default="{ row }">
              <template v-if="row.active_users && row.active_users.length > 0">
                <el-tag 
                  v-for="user in row.active_users" 
                  :key="user" 
                  size="small" 
                  type="warning" 
                  class="mx-1"
                  style="margin-right: 4px; margin-bottom: 4px;"
                >
                  {{ user }}
                </el-tag>
              </template>
              <el-tag v-else type="success" size="small">空闲</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showPoolDialog(row)">编辑</el-button>
              <el-button type="info" link size="small" @click="viewAllocations(row)">分配记录</el-button>
              <el-popconfirm title="确定删除该密钥池？" @confirm="deletePool(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        
        <!-- 分页组件 -->
        <div class="pagination-container">
          <el-pagination
            v-model:current-page="pagination.currentPage"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="pagination.total"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          />
        </div>
      </div>
    </div>

    <!-- 提供商对话框 -->
    <el-dialog
      v-model="providerDialogVisible"
      :title="isEditingProvider ? '编辑提供商' : '新增提供商'"
      width="600px"
    >
      <el-form :model="providerForm" :rules="providerRules" ref="providerFormRef" label-width="100px">
        <el-form-item label="标识符" prop="name">
          <el-input v-model="providerForm.name" :disabled="isEditingProvider" placeholder="提供商唯一标识符" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="providerForm.display_name" placeholder="显示在界面上的名称" />
        </el-form-item>
        <el-form-item label="基础URL">
          <el-input v-model="providerForm.base_url" placeholder="API基础URL（可选）" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="providerForm.description" type="textarea" placeholder="提供商描述" />
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-input-number v-model="providerForm.priority" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="providerForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProvider">确定</el-button>
      </template>
    </el-dialog>

    <!-- 密钥池对话框 -->
    <el-dialog
      v-model="poolDialogVisible"
      :title="isEditingPool ? '编辑密钥池' : '新增密钥池'"
      width="600px"
    >
      <el-form :model="poolForm" :rules="poolRules" ref="poolFormRef" label-width="100px">
        <el-form-item label="提供商" prop="provider_id">
          <el-select v-model="poolForm.provider_id" placeholder="选择提供商" style="width: 100%">
            <el-option
              v-for="provider in providers"
              :key="provider.id"
              :label="provider.display_name"
              :value="provider.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="池名称" prop="name">
          <el-input v-model="poolForm.name" placeholder="密钥池名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="poolForm.description" type="textarea" placeholder="密钥池描述" />
        </el-form-item>
        <el-form-item label="API密钥" prop="api_key">
          <el-input
            v-model="poolForm.api_key"
            type="password"
            placeholder="API密钥"
            show-password
          />
        </el-form-item>
        <el-form-item label="最大客户端数" prop="max_clients">
          <el-input-number
            v-model="poolForm.max_clients"
            :min="-1"
            placeholder="最大客户端数量，-1表示无限制"
          />
          <div class="form-tip">设置为 -1 表示无限制</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="poolForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="poolDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="savePool">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量添加密钥池对话框 -->
    <el-dialog
      v-model="batchPoolDialogVisible"
      title="批量添加密钥池"
      width="600px"
    >
      <el-form :model="batchPoolForm" :rules="batchPoolRules" ref="batchPoolFormRef" label-width="120px">
        <el-form-item label="提供商" prop="provider_id">
          <el-select v-model="batchPoolForm.provider_id" placeholder="选择提供商" style="width: 100%">
            <el-option
              v-for="provider in providers"
              :key="provider.id"
              :label="provider.display_name"
              :value="provider.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称前缀" prop="name_prefix">
          <el-input v-model="batchPoolForm.name_prefix" placeholder="例如：Provider_Pool" />
          <div class="form-tip">将生成如 Prefix_1, Prefix_2 的名称</div>
        </el-form-item>
        <el-form-item label="API密钥列表" prop="api_keys">
          <el-input
            v-model="batchPoolForm.api_keys_text"
            type="textarea"
            :rows="10"
            placeholder="请输入API密钥，每行一个"
          />
          <div class="form-tip">请每行输入一个API密钥</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="batchPoolForm.description" type="textarea" placeholder="密钥池描述（可选）" />
        </el-form-item>
        <el-form-item label="最大客户端数" prop="max_clients">
          <el-input-number
            v-model="batchPoolForm.max_clients"
            :min="-1"
            placeholder="最大客户端数量，-1表示无限制"
          />
          <div class="form-tip">设置为 -1 表示无限制</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchPoolDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveBatchPool">确定</el-button>
      </template>
    </el-dialog>

    <!-- API密钥查看对话框 -->
    <el-dialog
      v-model="apiKeyDialogVisible"
      title="API密钥"
      width="400px"
    >
      <div>
        <p><strong>密钥：</strong></p>
        <el-input
          v-model="currentApiKey"
          readonly
          type="textarea"
          :rows="3"
        />
      </div>
      <template #footer>
        <el-button @click="apiKeyDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyApiKey">复制</el-button>
      </template>
    </el-dialog>

    <!-- 分配记录对话框 -->
    <el-dialog
      v-model="allocationsDialogVisible"
      title="密钥分配记录"
      width="800px"
    >
      <el-table :data="allocations" v-loading="allocationsLoading">
        <el-table-column prop="client_id" label="客户端ID" width="200" />
        <el-table-column prop="user_id" label="用户ID" width="150" />
        <el-table-column prop="allocated_at" label="分配时间" width="160">
          <template #default="{ row }">{{ formatDate(row.allocated_at) }}</template>
        </el-table-column>
        <el-table-column prop="released_at" label="释放时间" width="160">
          <template #default="{ row }">
            {{ row.released_at ? formatDate(row.released_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '活跃' : '已释放' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="allocationsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/api'

// 响应式数据
const loading = ref(false)
const providers = ref([])
const keyPools = ref([])
const stats = ref({})
const providerStats = ref([])
const pagination = ref({
  currentPage: 1,
  pageSize: 20,
  total: 0
})

// 提供商对话框
const providerDialogVisible = ref(false)
const isEditingProvider = ref(false)
const providerForm = ref({
  name: '',
  display_name: '',
  base_url: '',
  description: '',
  priority: 0,
  is_active: true
})
const providerFormRef = ref()
const providerRules = {
  name: [
    { required: true, message: '请输入提供商标识符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '标识符只能包含字母、数字和下划线', trigger: 'blur' }
  ],
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' }
  ],
  priority: [
    { required: true, message: '请输入优先级', trigger: 'change' }
  ]
}

// 密钥池对话框
const poolDialogVisible = ref(false)
const isEditingPool = ref(false)
const poolForm = ref({
  provider_id: null,
  name: '',
  description: '',
  api_key: '',
  max_clients: -1,
  is_active: true
})
const poolFormRef = ref()
const poolRules = {
  provider_id: [
    { required: true, message: '请选择提供商', trigger: 'change' }
  ],
  name: [
    { required: true, message: '请输入池名称', trigger: 'blur' }
  ],
  api_key: [
    { required: true, message: '请输入API密钥', trigger: 'blur' }
  ],
  max_clients: [
    { required: true, message: '请输入最大客户端数', trigger: 'change' }
  ]
}

// 批量添加密钥池
const batchPoolDialogVisible = ref(false)
const batchPoolForm = ref({
  provider_id: null,
  name_prefix: 'Pool',
  api_keys_text: '',
  description: '',
  max_clients: -1
})
const batchPoolFormRef = ref()
const batchPoolRules = {
  provider_id: [
    { required: true, message: '请选择提供商', trigger: 'change' }
  ],
  name_prefix: [
    { required: true, message: '请输入名称前缀', trigger: 'blur' }
  ],
  api_keys_text: [
    { required: true, message: '请输入API密钥列表', trigger: 'blur' }
  ],
  max_clients: [
    { required: true, message: '请输入最大客户端数', trigger: 'change' }
  ]
}

// API密钥查看
const apiKeyDialogVisible = ref(false)
const currentApiKey = ref('')

// 分配记录
const allocationsDialogVisible = ref(false)
const allocations = ref([])
const allocationsLoading = ref(false)

// 方法
const loadData = async () => {
  loading.value = true
  try {
    const [providersRes, poolsRes, statsRes] = await Promise.all([
      api.keyPools.providers.list(),
      api.keyPools.pools.list({
        page: pagination.value.currentPage,
        page_size: pagination.value.pageSize
      }),
      api.keyPools.stats()
    ])
    providers.value = providersRes
    
    // 处理分页返回格式
    if (poolsRes.items) {
      keyPools.value = poolsRes.items
      pagination.value.total = poolsRes.total
    } else {
      // 兼容旧格式（如果是数组）
      keyPools.value = poolsRes
      pagination.value.total = poolsRes.length
    }
    
    if (statsRes.success && statsRes.data) {
      if (statsRes.data.summary) {
        stats.value = statsRes.data.summary
      }
      if (statsRes.data.provider_stats) {
        providerStats.value = statsRes.data.provider_stats
      }
    } else {
      stats.value = {}
      providerStats.value = []
    }
  } catch (error) {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const handleSizeChange = (val) => {
  pagination.value.pageSize = val
  pagination.value.currentPage = 1
  loadData()
}

const handleCurrentChange = (val) => {
  pagination.value.currentPage = val
  loadData()
}

const showProviderDialog = (provider = null) => {
  isEditingProvider.value = !!provider
  if (provider) {
    providerForm.value = { ...provider }
  } else {
    providerForm.value = {
      name: '',
      display_name: '',
      base_url: '',
      description: '',
      priority: 0,
      is_active: true
    }
  }
  providerDialogVisible.value = true
}

const saveProvider = async () => {
  try {
    await providerFormRef.value.validate()
    if (isEditingProvider.value) {
      await api.keyPools.providers.update(providerForm.value.id, providerForm.value)
      ElMessage.success('提供商更新成功')
    } else {
      await api.keyPools.providers.create(providerForm.value)
      ElMessage.success('提供商创建成功')
    }
    providerDialogVisible.value = false
    loadData()
  } catch (error) {
    if (error.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    }
  }
}

const deleteProvider = async (provider) => {
  try {
    await api.keyPools.providers.delete(provider.id)
    ElMessage.success('提供商删除成功')
    loadData()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const showPoolDialog = (pool = null) => {
  isEditingPool.value = !!pool
  if (pool) {
    poolForm.value = { ...pool }
  } else {
    poolForm.value = {
      provider_id: null,
      name: '',
      description: '',
      api_key: '',
      max_clients: -1,
      is_active: true
    }
  }
  poolDialogVisible.value = true
}

const savePool = async () => {
  try {
    await poolFormRef.value.validate()
    if (isEditingPool.value) {
      await api.keyPools.pools.update(poolForm.value.id, poolForm.value)
      ElMessage.success('密钥池更新成功')
    } else {
      await api.keyPools.pools.create(poolForm.value)
      ElMessage.success('密钥池创建成功')
    }
    poolDialogVisible.value = false
    loadData()
  } catch (error) {
    if (error.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    }
  }
}

const showBatchPoolDialog = () => {
  batchPoolForm.value = {
    provider_id: null,
    name_prefix: 'Pool',
    api_keys_text: '',
    description: '',
    max_clients: -1
  }
  batchPoolDialogVisible.value = true
}

const saveBatchPool = async () => {
  try {
    await batchPoolFormRef.value.validate()
    
    // 处理 API Key 列表
    const apiKeys = batchPoolForm.value.api_keys_text
      .split('\n')
      .map(k => k.trim())
      .filter(k => k.length > 0)
    
    if (apiKeys.length === 0) {
      ElMessage.warning('请输入有效的API密钥')
      return
    }

    const data = {
      provider_id: batchPoolForm.value.provider_id,
      name_prefix: batchPoolForm.value.name_prefix,
      api_keys: apiKeys,
      description: batchPoolForm.value.description,
      max_clients: batchPoolForm.value.max_clients
    }

    await api.keyPools.pools.batchCreate(data)
    ElMessage.success(`成功添加 ${apiKeys.length} 个密钥池`)
    
    batchPoolDialogVisible.value = false
    loadData()
  } catch (error) {
    if (error.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else {
      ElMessage.error('批量添加失败')
    }
  }
}

const deletePool = async (pool) => {
  try {
    await api.keyPools.pools.delete(pool.id)
    ElMessage.success('密钥池删除成功')
    loadData()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const showApiKey = (pool) => {
  currentApiKey.value = pool.api_key
  apiKeyDialogVisible.value = true
}

const copyApiKey = async () => {
  try {
    await navigator.clipboard.writeText(currentApiKey.value)
    ElMessage.success('API密钥已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

const viewAllocations = async (pool) => {
  allocationsLoading.value = true
  try {
    const res = await api.keyPools.allocations.list({ pool_id: pool.id })
    allocations.value = res
    allocationsDialogVisible.value = true
  } catch (error) {
    ElMessage.error('加载分配记录失败')
  } finally {
    allocationsLoading.value = false
  }
}

const maskApiKey = (apiKey) => {
  if (!apiKey) return ''
  if (apiKey.length <= 8) return apiKey
  return apiKey.substring(0, 4) + '*'.repeat(apiKey.length - 8) + apiKey.substring(apiKey.length - 4)
}

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

// 初始化
onMounted(() => {
  loadData()
})
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  color: #1f2937;
}

.page-header p {
  margin: 0;
  color: #6b7280;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid #e5e7eb;
}

.stat-title {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 8px;
}

.section-title {
  font-size: 16px;
  font-weight: bold;
  color: #374151;
  margin-bottom: 15px;
  padding-left: 5px;
  border-left: 4px solid #3b82f6;
}

.provider-stat-details {
  margin-top: 10px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 14px;
}

.stat-row .label {
  color: #6b7280;
}

.stat-row .value {
  font-weight: 500;
  color: #1f2937;
}

.text-danger {
  color: #ef4444;
  font-weight: bold;
}

.warning-border {
  border: 1px solid #ef4444;
  background-color: #fef2f2;
}

.warning-text {
  color: #ef4444;
  font-size: 12px;
  margin-top: 5px;
  text-align: right;
  font-weight: bold;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #1f2937;
}

.panel {
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid #e5e7eb;
  margin-bottom: 20px;
}

.panel-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-actions {
  display: flex;
  gap: 10px;
}

.panel-header h3 {
  margin: 0;
  color: #1f2937;
}

.panel-body {
  padding: 24px;
}

.form-tip {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

/* 修复表格在白色背景下的显示问题 */
.el-table {
  --el-table-text-color: #1f2937 !important;
  --el-table-header-text-color: #4b5563 !important;
  --el-table-row-hover-bg-color: #f3f4f6 !important;
  --el-table-bg-color: #ffffff !important;
  --el-table-tr-bg-color: #ffffff !important;
  --el-table-header-bg-color: #f9fafb !important;
}

.el-table th.el-table__cell {
  background-color: #f9fafb !important;
  color: #374151 !important;
  font-weight: 600;
}
</style>
