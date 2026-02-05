<template>
  <div>
    <div class="page-header">
      <h2>IDE版本管理</h2>
      <p>管理SenWeaver IDE安装包和更新日志</p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <h3>版本列表</h3>
        <el-button type="primary" :icon="Plus" @click="showCreate">新增版本</el-button>
      </div>
      <div class="panel-body">
        <el-table :data="versions" v-loading="loading">
          <el-table-column prop="version" label="版本号" width="200">
            <template #default="{ row }">
              <div style="display: flex; align-items: center">
                <span>{{ row.version }}</span>
                <el-tag v-if="row.is_latest" type="danger" size="small" effect="dark" style="margin-left: 8px">客户端最新</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="filename" label="安装包" width="280">
            <template #default="{ row }">
              <span v-if="row.filename">{{ row.filename }}</span>
              <el-tag v-else type="warning" size="small">未上传</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_size" label="大小" width="100">
            <template #default="{ row }">
              {{ row.file_size ? formatSize(row.file_size) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="external_url" label="第三方下载URL" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <el-link v-if="row.external_url" :href="row.external_url" target="_blank" type="primary">
                {{ row.external_url }}
              </el-link>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="download_count" label="下载次数" width="100" />
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
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showUpload(row)">上传安装包</el-button>
              <el-button type="primary" link size="small" @click="showEdit(row)">编辑</el-button>
              <el-button v-if="!row.is_latest" type="success" link size="small" @click="setLatest(row)">设为最新</el-button>
              <el-popconfirm title="确定删除该版本？" @confirm="deleteVersion(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 新增/编辑版本对话框 -->
    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑版本' : '新增版本'" width="700px">
      <el-form :model="dialog.form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="版本号" prop="version">
          <el-input v-model="dialog.form.version" :disabled="dialog.isEdit" placeholder="如: 2.8.3" />
        </el-form-item>
        <el-form-item label="版本描述">
          <el-input v-model="dialog.form.description" placeholder="简要描述此版本" />
        </el-form-item>
        <el-form-item label="第三方下载URL" prop="external_url">
          <el-input v-model="dialog.form.external_url" placeholder="https://..." clearable />
        </el-form-item>
        <el-form-item label="更新日志">
          <el-input v-model="dialog.form.changelog" type="textarea" :rows="12" placeholder="支持Markdown格式" />
        </el-form-item>
        <el-form-item label="设为最新">
          <el-switch v-model="dialog.form.is_latest" />
        </el-form-item>
        <el-form-item v-if="dialog.isEdit" label="启用状态">
          <el-switch v-model="dialog.form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="saveVersion">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上传安装包对话框 -->
    <el-dialog v-model="uploadDialog.visible" title="上传安装包" width="500px">
      <el-upload
        ref="uploadRef"
        drag
        :action="uploadDialog.action"
        :headers="uploadDialog.headers"
        :on-success="onUploadSuccess"
        :on-error="onUploadError"
        :before-upload="beforeUpload"
        accept=".exe,.zip,.dmg"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 .exe / .zip / .dmg 格式，文件大小不超过500MB</div>
        </template>
      </el-upload>
      <div v-if="uploadDialog.version" style="margin-top: 16px; color: var(--text-secondary);">
        当前版本: {{ uploadDialog.version.version }}
        <span v-if="uploadDialog.version.filename">（已上传: {{ uploadDialog.version.filename }}）</span>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import api from '@/api'

const loading = ref(false)
const versions = ref([])
const formRef = ref(null)
const uploadRef = ref(null)

const dialog = reactive({
  visible: false,
  isEdit: false,
  loading: false,
  form: { version: '', description: '', external_url: '', changelog: '', is_latest: false, is_active: true }
})

const uploadDialog = reactive({
  visible: false,
  version: null,
  action: '',
  headers: {}
})

const rules = {
  version: [
    { required: true, message: '请输入版本号', trigger: 'blur' },
    { pattern: /^\d+\.\d+\.\d+$/, message: '版本号格式应为 x.y.z', trigger: 'blur' }
  ]
}

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
const formatSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.versions.list()
    versions.value = res.items || []
  } catch (e) {}
  loading.value = false
}

const showCreate = () => {
  dialog.isEdit = false
  dialog.form = { version: '', description: '', external_url: '', changelog: '', is_latest: false, is_active: true }
  dialog.visible = true
}

const showEdit = async (row) => {
  dialog.isEdit = true
  try {
    const detail = await api.versions.get(row.id)
    dialog.form = { ...detail }
  } catch (e) {
    dialog.form = { ...row }
  }
  dialog.visible = true
}

const saveVersion = async () => {
  try {
    await formRef.value?.validate()
  } catch { return }

  dialog.loading = true
  try {
    if (dialog.isEdit) {
      await api.versions.update(dialog.form.id, dialog.form)
    } else {
      await api.versions.create(dialog.form)
    }
    ElMessage.success('保存成功')
    dialog.visible = false
    loadData()
  } catch (e) {}
  dialog.loading = false
}

const deleteVersion = async (row) => {
  try {
    await api.versions.delete(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

const setLatest = async (row) => {
  try {
    await api.versions.setLatest(row.id)
    ElMessage.success('已设为最新版本')
    loadData()
  } catch (e) {}
}

const showUpload = (row) => {
  uploadDialog.version = row
  uploadDialog.action = `/api/admin/versions/${row.id}/upload`
  uploadDialog.headers = { Authorization: `Bearer ${localStorage.getItem('admin_token')}` }
  uploadDialog.visible = true
}

const beforeUpload = (file) => {
  const maxSize = 500 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过500MB')
    return false
  }
  return true
}

const onUploadSuccess = (res) => {
  ElMessage.success('上传成功')
  uploadDialog.visible = false
  loadData()
}

const onUploadError = () => {
  ElMessage.error('上传失败')
}

onMounted(loadData)
</script>

<style scoped>
.el-upload-dragger {
  background: rgba(15, 23, 42, 0.5) !important;
  border-color: var(--border-color) !important;
}
.el-upload-dragger:hover {
  border-color: var(--primary-color) !important;
}
</style>
