<template>
  <div>
    <div class="page-header">
      <h2>仪表盘</h2>
      <p>系统运行概览</p>
    </div>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-card-header">
          <div class="stat-card-icon blue"><el-icon><User /></el-icon></div>
        </div>
        <div class="stat-card-body">
          <div class="label">总用户数</div>
          <div class="value">{{ stats.total_users || 0 }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <div class="stat-card-icon green"><el-icon><Connection /></el-icon></div>
        </div>
        <div class="stat-card-body">
          <div class="label">在线用户</div>
          <div class="value">{{ stats.online_count || 0 }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <div class="stat-card-icon orange"><el-icon><Wallet /></el-icon></div>
        </div>
        <div class="stat-card-body">
          <div class="label">总充值金额</div>
          <div class="value">¥{{ (stats.total_recharge || 0).toLocaleString() }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <div class="stat-card-icon cyan"><el-icon><Document /></el-icon></div>
        </div>
        <div class="stat-card-body">
          <div class="label">文章数</div>
          <div class="value">{{ stats.total_articles || 0 }}</div>
        </div>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="16">
        <div class="panel">
          <div class="panel-header">
            <h3>用户趋势</h3>
          </div>
          <div class="panel-body">
            <div class="chart-container">
              <canvas ref="chartRef"></canvas>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="panel">
          <div class="panel-header">
            <h3>最近订单</h3>
          </div>
          <div class="panel-body">
            <el-table :data="recentOrders" size="small">
              <el-table-column prop="order_no" label="订单号" width="120" />
              <el-table-column prop="amount" label="金额">
                <template #default="{ row }">¥{{ row.amount }}</template>
              </el-table-column>
              <el-table-column prop="status" label="状态">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'paid' ? 'success' : 'info'" size="small">
                    {{ row.status === 'paid' ? '已支付' : '待支付' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { User, Connection, Wallet, Document } from '@element-plus/icons-vue'
import { Chart, registerables } from 'chart.js'
import api from '@/api'

Chart.register(...registerables)

const stats = ref({})
const recentOrders = ref([])
const chartRef = ref(null)
let chartInstance = null

const loadData = async () => {
  try {
    const data = await api.stats.dashboard()
    stats.value = data.stats || {}
    recentOrders.value = data.recent_orders || []
    initChart(data.user_trend || [])
  } catch (e) {
    console.error(e)
  }
}

const initChart = (trendData) => {
  if (!chartRef.value) return
  if (chartInstance) chartInstance.destroy()
  
  const labels = trendData.map(d => d.date) || ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const values = trendData.map(d => d.count) || [12, 19, 15, 25, 22, 30, 28]
  
  chartInstance = new Chart(chartRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '新增用户',
        data: values,
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56, 189, 248, 0.1)',
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#94a3b8' } }
      }
    }
  })
}

onMounted(loadData)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>
