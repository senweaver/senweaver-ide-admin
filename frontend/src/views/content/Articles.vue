<template>
  <div>
    <div class="page-header">
      <h2>文章管理</h2>
      <p>管理系统文章</p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <h3>文章列表</h3>
        <el-button type="primary" :icon="Plus" @click="showCreate">新增文章</el-button>
      </div>
      <div class="panel-body">
        <div class="filter-bar">
          <el-input v-model="filters.keyword" placeholder="搜索标题" style="width: 200px" clearable />
          <el-select v-model="filters.category" placeholder="分类" clearable style="width: 150px">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
          <el-button type="primary" @click="loadData">搜索</el-button>
        </div>

        <el-table :data="articles" v-loading="loading" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="title" label="标题" min-width="200" />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column prop="author" label="作者" width="250" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'published' ? 'success' : 'info'">
                {{ row.status === 'published' ? '已发布' : '草稿' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="view_count" label="浏览" width="80" />
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showEdit(row)">编辑</el-button>
              <el-button v-if="row.status === 'draft'" type="success" link size="small" @click="publishArticle(row)">发布</el-button>
              <el-popconfirm title="确定删除？" @confirm="deleteArticle(row)">
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

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑文章' : '新增文章'" width="700px">
      <el-form :model="dialog.form" label-width="80px">
        <el-form-item label="标题"><el-input v-model="dialog.form.title" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="dialog.form.category" style="width: 100%">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="摘要"><el-input v-model="dialog.form.excerpt" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="dialog.form.content" type="textarea" :rows="8" /></el-form-item>
        <el-form-item label="作者"><el-input v-model="dialog.form.author" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="saveArticle">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const articles = ref([])
const categories = ref(['产品更新', '教程指南', '技术文章', '公告通知'])
const filters = reactive({ keyword: '', category: '' })
const pagination = reactive({ page: 1, size: 10, total: 0 })

const dialog = reactive({
  visible: false, isEdit: false, loading: false,
  form: { title: '', category: '', excerpt: '', content: '', author: '' }
})

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.articles.list({ ...filters, page: pagination.page, size: pagination.size })
    articles.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {}
  loading.value = false
}

const showCreate = () => {
  dialog.isEdit = false
  dialog.form = { title: '', category: '产品更新', excerpt: '', content: '', author: 'Admin' }
  dialog.visible = true
}

const showEdit = (article) => {
  dialog.isEdit = true
  dialog.form = { ...article }
  dialog.visible = true
}

const saveArticle = async () => {
  dialog.loading = true
  try {
    if (dialog.isEdit) {
      await api.articles.update(dialog.form.id, dialog.form)
    } else {
      await api.articles.create(dialog.form)
    }
    ElMessage.success('保存成功')
    dialog.visible = false
    loadData()
  } catch (e) {}
  dialog.loading = false
}

const publishArticle = async (article) => {
  try {
    await api.articles.publish(article.id)
    ElMessage.success('发布成功')
    loadData()
  } catch (e) {}
}

const deleteArticle = async (article) => {
  try {
    await api.articles.delete(article.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
