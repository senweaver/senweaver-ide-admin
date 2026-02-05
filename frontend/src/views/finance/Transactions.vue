<template>
  <div>
    <div class="page-header">
      <h2>交易流水</h2>
      <p>查看所有交易记录</p>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <el-table :data="transactions" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="user_name" label="用户" width="250" />
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.type)">
                {{ statusText(row.type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="120">
            <template #default="{ row }">
              <span :style="{ color: row.amount > 0 ? 'var(--success-color)' : 'var(--danger-color)' }">
                {{ row.amount > 0 ? '+' : '' }}¥{{ row.amount }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="balance_after" label="交易后余额" width="120">
            <template #default="{ row }">¥{{ row.balance_after }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" />
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
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const transactions = ref([])
const pagination = reactive({ page: 1, size: 20, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'

const statusType = (type) => {
    const map = {
        recharge: 'success',
        consume: 'warning',
        refund: 'danger',
        gift: 'primary',
        adjustment: 'info'
    }
    return map[type] || 'info'
}

const statusText = (type) => {
    const map = {
        recharge: '充值',
        consume: '消费',
        refund: '退款',
        gift: '赠送',
        adjustment: '调整'
    }
    return map[type] || type
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.transactions.list({ page: pagination.page, size: pagination.size })
    transactions.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

onMounted(loadData)
</script>
