<template>
  <div>
    <div class="page-header">
      <h2>VIP管理</h2>
      <p>管理VIP用户</p>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <el-table :data="users" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="username" label="用户名" width="250" />
          <el-table-column prop="email" label="邮箱" width="200" />
          <el-table-column prop="vip_level" label="VIP等级" width="100">
            <template #default="{ row }">
              <el-tag type="warning">VIP{{ row.vip_level || 1 }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="vip_expire_at" label="到期时间" width="180">
            <template #default="{ row }">{{ formatDate(row.vip_expire_at) }}</template>
          </el-table-column>
          <el-table-column prop="balance" label="余额" width="120">
            <template #default="{ row }">¥{{ row.balance?.toFixed(2) || '0.00' }}</template>
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
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const users = ref([])
const pagination = reactive({ page: 1, size: 10, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD') : '-'

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.users.vip({ page: pagination.page, size: pagination.size })
    users.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

onMounted(loadData)
</script>
