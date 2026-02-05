<template>
  <div>
    <div class="page-header">
      <h2>订单管理</h2>
      <p>管理系统订单</p>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <div class="filter-bar">
          <el-input v-model="filters.keyword" placeholder="订单号/用户" style="width: 200px" clearable />
          <el-select v-model="filters.order_type" placeholder="类型" clearable style="width: 120px; margin-right: 10px">
            <el-option label="充值" value="recharge" />
            <el-option label="订阅" value="subscribe" />
            <el-option label="服务" value="service" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px">
            <el-option label="待支付" value="pending" />
            <el-option label="已支付" value="paid" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
          <el-button type="primary" :icon="Search" @click="loadData">搜索</el-button>
        </div>

        <el-table :data="orders" v-loading="loading" stripe>
          <el-table-column prop="order_no" label="订单号" width="180" />
          <el-table-column prop="user_name" label="用户" width="250" />
          <el-table-column prop="order_type" label="类型" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.order_type === 'recharge'" type="success">充值</el-tag>
              <el-tag v-else-if="row.order_type === 'subscribe'" type="warning">订阅</el-tag>
              <el-tag v-else type="info">{{ row.order_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="120">
            <template #default="{ row }">
              <span style="color: var(--warning-color); font-weight: 600;">¥{{ row.amount }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button v-if="row.status === 'pending'" type="success" link size="small" @click="payOrder(row)">确认支付</el-button>
              <el-button v-if="row.status === 'pending'" type="warning" link size="small" @click="cancelOrder(row)">取消</el-button>
              <el-button v-if="row.status === 'paid'" type="danger" link size="small" @click="refundOrder(row)">退款</el-button>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const orders = ref([])
const filters = reactive({ keyword: '', status: '', order_type: '' })
const pagination = reactive({ page: 1, size: 10, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
const statusType = (s) => ({ pending: 'warning', paid: 'success', cancelled: 'info', refunded: 'danger' }[s] || 'info')
const statusText = (s) => ({ pending: '待支付', paid: '已支付', cancelled: '已取消', refunded: '已退款' }[s] || s)

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.orders.list({ ...filters, page: pagination.page, size: pagination.size })
    orders.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

const payOrder = async (order) => {
  await ElMessageBox.confirm('确认该订单已支付？', '提示')
  try {
    await api.orders.pay(order.id)
    ElMessage.success('操作成功')
    loadData()
  } catch (e) {}
}

const cancelOrder = async (order) => {
  await ElMessageBox.confirm('确定取消该订单？', '提示', { type: 'warning' })
  try {
    await api.orders.cancel(order.id)
    ElMessage.success('订单已取消')
    loadData()
  } catch (e) {}
}

const refundOrder = async (order) => {
  await ElMessageBox.confirm('确定退款？', '提示', { type: 'warning' })
  try {
    await api.orders.refund(order.id)
    ElMessage.success('退款成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
