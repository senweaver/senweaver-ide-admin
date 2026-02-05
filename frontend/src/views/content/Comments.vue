<template>
  <div>
    <div class="page-header">
      <h2>评论管理</h2>
      <p>管理文章评论</p>
    </div>
    
    <div class="panel">
      <div class="panel-body">
        <el-table :data="comments" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="article_title" label="文章" width="200" />
          <el-table-column prop="author" label="作者" width="250" />
          <el-table-column prop="content" label="内容" min-width="250" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'approved' ? 'success' : 'warning'">
                {{ row.status === 'approved' ? '已审核' : '待审核' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button v-if="row.status === 'pending'" type="success" link size="small" @click="approveComment(row)">审核通过</el-button>
              <el-popconfirm title="确定删除？" @confirm="deleteComment(row)">
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
const comments = ref([])
const pagination = reactive({ page: 1, size: 20, total: 0 })

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.comments.list({ page: pagination.page, size: pagination.size })
    comments.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

const approveComment = async (comment) => {
  try {
    await api.comments.approve(comment.id)
    ElMessage.success('审核通过')
    loadData()
  } catch (e) {}
}

const deleteComment = async (comment) => {
  try {
    await api.comments.delete(comment.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
