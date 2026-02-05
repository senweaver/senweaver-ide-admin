<template>
  <div>
    <div class="page-header">
      <h2>订阅者管理</h2>
      <p>邮件订阅用户</p>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <el-table :data="subscribers" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="email" label="邮箱" width="250" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                {{ row.status === 'active' ? '已订阅' : '已退订' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="订阅时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-popconfirm title="确定删除？" @confirm="deleteSubscriber(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
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
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const subscribers = ref([])
const pagination = reactive({ page: 1, size: 20, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.subscribers.list({ page: pagination.page, size: pagination.size })
    subscribers.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

const deleteSubscriber = async (sub) => {
  try {
    await api.subscribers.delete(sub.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
