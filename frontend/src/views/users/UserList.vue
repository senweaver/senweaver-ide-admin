<template>
  <div>
    <div class="page-header">
      <div style="display: flex; align-items: center; gap: 20px;">
        <div>
          <h2>用户列表</h2>
          <p>管理系统用户</p>
        </div>
        <div style="background-color: #fef0f0; border: 1px solid #fde2e2; border-radius: 4px; padding: 10px 15px; color: #f56c6c; display: flex; flex-direction: column; gap: 5px;">
          <div style="font-weight: bold; font-size: 14px; display: flex; align-items: center; gap: 5px;">
            <el-icon><Warning /></el-icon> 客户端验证说明：客户端连接需验证合法性
          </div>
          <div style="font-size: 13px;">
             当前动态密钥：
            <span style="font-weight: bold; font-size: 15px; background-color: #fff; padding: 2px 8px; border-radius: 4px; border: 1px solid #fde2e2;">b90FdAe53B74fCbE2B917</span>
          </div>
        </div>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <div class="filter-bar">
          <el-input v-model="filters.keyword" placeholder="搜索用户名/邮箱" style="width: 220px" clearable @clear="loadData">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadData">
            <el-option label="正常" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
          <el-select v-model="filters.vip" placeholder="VIP" clearable style="width: 120px" @change="loadData">
            <el-option label="VIP用户" :value="true" />
            <el-option label="普通用户" :value="false" />
          </el-select>
          <el-button type="primary" :icon="Search" @click="loadData">搜索</el-button>
        </div>

        <el-table :data="users" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="nickname" label="用户名" width="250" />
          <el-table-column prop="email" label="邮箱" width="200" />
          <el-table-column prop="balance" label="余额" width="120">
            <template #default="{ row }">
              <span style="color: var(--primary-color); font-weight: 600;">¥{{ row.balance?.toFixed(2) || '0.00' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_vip" label="VIP" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.is_vip" type="warning">VIP</el-tag>
              <el-tag v-else type="info">普通</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="在线" width="80" align="center">
            <template #default="{ row }">
              <el-tooltip v-if="row.is_online" effect="dark" placement="top">
                <template #content>
                  <div>IP: {{ row.online_info?.ip }}</div>
                  <div>客户端: {{ row.online_info?.client_id }}</div>
                  <div>连接时间: {{ formatDate(row.online_info?.connected_at) }}</div>
                </template>
                <div style="display: inline-block; width: 10px; height: 10px; background: #67C23A; border-radius: 50%;"></div>
              </el-tooltip>
              <div v-else style="display: inline-block; width: 10px; height: 10px; background: #909399; border-radius: 50%; opacity: 0.3;"></div>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
                {{ row.status === 'active' ? '正常' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="模型权限" width="200">
            <template #default="{ row }">
              <div style="display: flex; flex-direction: column; gap: 4px;">
                <div style="display: flex; gap: 8px; align-items: center;">
                  <el-tag v-if="modelAccessMap[row.user_id] && modelAccessMap[row.user_id].enabled" type="success">可用</el-tag>
                  <el-tag v-else-if="modelAccessMap[row.user_id]" type="danger">禁用</el-tag>
                  <el-tag v-else type="info">未知</el-tag>
                  <span style="color: var(--text-color-secondary);">
                    {{ modelAccessMap[row.user_id] ? `${modelAccessMap[row.user_id].used}/${modelAccessMap[row.user_id].limit}` : '-' }}
                  </span>
                </div>
                <div v-if="modelAccessMap[row.user_id]" style="font-size: 12px; color: #909399;">
                  累计: {{ modelAccessMap[row.user_id].used_total || 0 }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="重置周期" width="120">
             <template #default="{ row }">
               <div v-if="modelAccessMap[row.user_id]">
                 <div>{{ modelAccessMap[row.user_id].reset_days || 30 }}天</div>
                 <div v-if="modelAccessMap[row.user_id].last_reset_time" style="font-size: 12px; color: #909399;" :title="formatDate(modelAccessMap[row.user_id].last_reset_time)">
                   上次: {{ formatDate(modelAccessMap[row.user_id].last_reset_time).split(' ')[0] }}
                 </div>
               </div>
               <div v-else>-</div>
             </template>
          </el-table-column>
          <el-table-column prop="created_at" label="注册时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="400" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showRecharge(row)">充值</el-button>
              <el-button type="primary" link size="small" @click="showEdit(row)">编辑</el-button>
              <el-button :type="row.status === 'active' ? 'danger' : 'success'" link size="small" @click="toggleUser(row)">
                {{ row.status === 'active' ? '禁用' : '启用' }}
              </el-button>
              <el-button type="warning" link size="small" @click="openModelAccess(row)">模型权限</el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
          <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size" :total="pagination.total"
            :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" />
        </div>
      </div>
    </div>

    <el-dialog v-model="rechargeDialog.visible" title="用户充值" width="400px">
      <el-form :model="rechargeDialog.form" label-width="80px">
        <el-form-item label="用户">{{ rechargeDialog.user?.nickname }}</el-form-item>
        <el-form-item label="充值金额">
          <el-input-number v-model="rechargeDialog.form.amount" :min="1" :max="10000" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="rechargeDialog.form.remark" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rechargeDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="rechargeDialog.loading" @click="doRecharge">确认充值</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="modelAccessDialog.visible" title="模型权限" width="520px">
      <el-form :model="modelAccessDialog.form" label-width="100px">
        <el-form-item label="用户">
          <div style="display: flex; gap: 8px; align-items: center;">
            <template v-if="modelAccessDialog.user?.nickname && modelAccessDialog.user.nickname !== modelAccessDialog.user.user_id">
              <span>{{ modelAccessDialog.user.nickname }}</span>
              <span style="color: var(--text-color-secondary);">({{ modelAccessDialog.user.user_id }})</span>
            </template>
            <span v-else>{{ modelAccessDialog.user?.user_id }}</span>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="modelAccessDialog.form.enabled" />
        </el-form-item>
        <el-form-item label="使用次数">
          <div style="display: flex; gap: 8px; align-items: center;">
            <span>{{ modelAccessDialog.form.used }}</span>
            <span style="color: var(--text-color-secondary);">/</span>
            <el-input-number v-model="modelAccessDialog.form.usage_limit" :min="0" :max="100000000" />
          </div>
        </el-form-item>
        <el-form-item label="重置已用">
          <el-switch v-model="modelAccessDialog.form.reset_used" />
        </el-form-item>
        <el-form-item v-if="!modelAccessDialog.form.enabled" label="禁用原因">
          <el-input v-model="modelAccessDialog.form.reason" placeholder="可选，例如 manual_disable" />
        </el-form-item>
        <el-form-item v-if="modelAccessDialog.form.disabled_reason" label="当前原因">
          <span style="color: var(--text-color-secondary);">{{ modelAccessDialog.form.disabled_reason }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelAccessDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="modelAccessDialog.loading" @click="saveModelAccess">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const users = ref([])
const modelAccessMap = reactive({})
const filters = reactive({ keyword: '', status: '', vip: '' })
const pagination = reactive({ page: 1, size: 10, total: 0 })
const ws = ref(null)

const rechargeDialog = reactive({
  visible: false,
  loading: false,
  user: null,
  form: { amount: 100, remark: '' }
})

const modelAccessDialog = reactive({
  visible: false,
  loading: false,
  user: null,
  form: {
    enabled: true,
    used: 0,
    usage_limit: 1000,
    reset_used: false,
    reason: '',
    disabled_reason: ''
  }
})

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'

const normalizeModelAccess = (res) => res?.data ?? res

const loadModelAccessForUsers = async (list) => {
  const tasks = (list || [])
    .filter(u => u?.user_id)
    .map(async (u) => {
      try {
        const res = await api.users.getModelAccess(u.user_id)
        modelAccessMap[u.user_id] = normalizeModelAccess(res)
      } catch (e) {}
    })
  await Promise.allSettled(tasks)
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.users.list({ ...filters, page: pagination.page, size: pagination.size })
    users.value = res.items || []
    pagination.total = res.total || 0
    await loadModelAccessForUsers(users.value)
  } catch (e) {}
  loading.value = false
}

const showRecharge = (user) => {
  rechargeDialog.user = user
  rechargeDialog.form = { amount: 100, remark: '' }
  rechargeDialog.visible = true
}

const doRecharge = async () => {
  rechargeDialog.loading = true
  try {
    await api.users.recharge(rechargeDialog.user.id, rechargeDialog.form)
    ElMessage.success('充值成功')
    rechargeDialog.visible = false
    loadData()
  } catch (e) {}
  rechargeDialog.loading = false
}

const showEdit = (user) => {
  ElMessage.info('编辑功能开发中')
}

const toggleUser = async (user) => {
  const action = user.status === 'active' ? '禁用' : '启用'
  const userLabel = user.nickname || user.user_id || user.email || ''
  await ElMessageBox.confirm(`确定要${action}用户 ${userLabel} 吗？`, '提示', { type: 'warning' })
  try {
    await api.users.toggle(user.id)
    ElMessage.success(`${action}成功`)
    loadData()
  } catch (e) {}
}

const deleteUser = async (user) => {
  if (!user) return
  console.log('Attempting to delete user:', user)
  const userLabel = user.nickname || user.user_id || user.email || '该用户'
  try {
    await ElMessageBox.confirm(`确定要删除用户 ${userLabel} 吗？此操作不可恢复！`, '警告', { 
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'error' 
    })
    
    await api.users.delete(user.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('删除失败:', e)
      ElMessage.error(e.response?.data?.detail || '删除失败，请稍后重试')
    }
  }
}

const openModelAccess = async (user) => {
  modelAccessDialog.user = user
  modelAccessDialog.loading = true
  modelAccessDialog.visible = true
  try {
    const res = await api.users.getModelAccess(user.user_id)
    const status = normalizeModelAccess(res)
    modelAccessMap[user.user_id] = status
    modelAccessDialog.form = {
      enabled: !!status.enabled,
      used: status.used ?? 0,
      usage_limit: status.limit ?? 1000,
      reset_used: false,
      reason: '',
      disabled_reason: status.disabled_reason || ''
    }
  } catch (e) {
    modelAccessDialog.form = {
      enabled: true,
      used: 0,
      usage_limit: 1000,
      reset_used: false,
      reason: '',
      disabled_reason: ''
    }
  }
  modelAccessDialog.loading = false
}

const saveModelAccess = async () => {
  if (!modelAccessDialog.user?.user_id) return
  modelAccessDialog.loading = true
  try {
    const payload = {
      user_id: modelAccessDialog.user.user_id,
      enabled: !!modelAccessDialog.form.enabled,
      usage_limit: modelAccessDialog.form.usage_limit,
      reset_used: !!modelAccessDialog.form.reset_used,
      reason: modelAccessDialog.form.enabled ? null : (modelAccessDialog.form.reason || null)
    }
    const res = await api.users.updateModelAccess(payload)
    const status = normalizeModelAccess(res)
    modelAccessMap[modelAccessDialog.user.user_id] = status
    modelAccessDialog.form.used = status.used ?? modelAccessDialog.form.used
    modelAccessDialog.form.usage_limit = status.limit ?? modelAccessDialog.form.usage_limit
    modelAccessDialog.form.disabled_reason = status.disabled_reason || ''
    ElMessage.success('保存成功')
    modelAccessDialog.visible = false
  } catch (e) {}
  modelAccessDialog.loading = false
}

const handleUserUpdate = (data) => {
  if (!data || !data.user) return
  const updatedUser = data.user
  
  // 更新列表中的用户数据
  const index = users.value.findIndex(u => u.id === updatedUser.id)
  if (index !== -1) {
    // 保持原有对象的引用，只更新属性
    Object.assign(users.value[index], updatedUser)
    
    // 更新模型权限映射
    if (updatedUser.user_id) {
      modelAccessMap[updatedUser.user_id] = {
        enabled: updatedUser.model_enabled,
        used: updatedUser.model_used,
        used_total: updatedUser.model_used_total,
        limit: updatedUser.model_limit,
        reset_days: updatedUser.model_reset_days,
        last_reset_time: updatedUser.model_last_reset_time
      }
    }
  } else {
    // 如果是新用户，添加到列表头部
    users.value.unshift(updatedUser)
    pagination.total += 1
    
    // 更新模型权限映射
    if (updatedUser.user_id) {
      modelAccessMap[updatedUser.user_id] = {
        enabled: updatedUser.model_enabled,
        used: updatedUser.model_used,
        used_total: updatedUser.model_used_total,
        limit: updatedUser.model_limit,
        reset_days: updatedUser.model_reset_days,
        last_reset_time: updatedUser.model_last_reset_time
      }
    }
  }
}

const handleUserDelete = (data) => {
  if (!data || !data.user_id) return
  const index = users.value.findIndex(u => u.id === data.user_id)
  if (index !== -1) {
    users.value.splice(index, 1)
    pagination.total = Math.max(0, pagination.total - 1)
  }
}

const connectWebSocket = () => {
  const token = localStorage.getItem('admin_token')
  if (!token) return

  // 确定 WebSocket URL
  let wsUrl
  if (import.meta.env.DEV) {
    // 开发环境使用配置的后端地址
    const wsHost = import.meta.env.VITE_WS_HOST || '127.0.0.1:18006'
    wsUrl = `ws://${wsHost}/ws?token=${token}`
  } else {
    // 生产环境使用相对路径 (同源)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`
  }

  ws.value = new WebSocket(wsUrl)

  ws.value.onopen = () => {
    console.log('WebSocket connected')
  }

  ws.value.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'user_update') {
        handleUserUpdate(data)
      } else if (data.type === 'user_delete') {
        handleUserDelete(data)
      }
    } catch (e) {
      console.error('WebSocket message error:', e)
    }
  }

  ws.value.onclose = () => {
    console.log('WebSocket disconnected')
    // 可以添加重连逻辑，这里简单处理
    ws.value = null
  }
  
  ws.value.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
}

onMounted(() => {
  loadData()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
  }
})
</script>
