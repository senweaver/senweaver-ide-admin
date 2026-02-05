<template>
  <div>
    <div class="page-header">
      <h2>连接日志</h2>
      <p>WebSocket连接记录</p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <h3>日志列表</h3>
        <el-button type="primary" :icon="Refresh" @click="loadData">刷新</el-button>
      </div>
      <div class="panel-body">
        <el-table :data="logs" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="user_id" label="用户ID" width="250" />
          <el-table-column prop="action" label="动作" width="100">
            <template #default="{ row }">
              <el-tag :type="row.action === 'connect' ? 'success' : 'info'">
                {{ row.action === 'connect' ? '连接' : '断开' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip" label="IP地址" width="150" />
          <el-table-column prop="user_agent" label="设备信息" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        
        <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
          <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size" :total="pagination.total"
            layout="total, prev, pager, next" @change="loadData" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const logs = ref([])
const pagination = reactive({ page: 1, size: 20, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm:ss') : '-'

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.logs.list({ page: pagination.page, size: pagination.size })
    logs.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

onMounted(loadData)
</script>
