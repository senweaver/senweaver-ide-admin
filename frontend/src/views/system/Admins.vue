<template>
  <div>
    <div class="page-header">
      <h2>管理员管理</h2>
      <p>管理系统管理员账号</p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <h3>管理员列表</h3>
        <el-button type="primary" :icon="Plus" @click="showCreate">新增管理员</el-button>
      </div>
      <div class="panel-body">
        <el-table :data="admins" v-loading="loading">
          <el-table-column prop="username" label="用户名" width="250" />
          <el-table-column prop="name" label="姓名" width="200" />
          <el-table-column prop="email" label="邮箱" width="200" />
          <el-table-column prop="role" label="角色" width="120">
            <template #default="{ row }">
              <el-tag :type="row.role === 'super_admin' ? 'danger' : 'primary'">
                {{ row.role === 'super_admin' ? '超级管理员' : '管理员' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="last_login_at" label="最后登录" width="160">
            <template #default="{ row }">{{ row.last_login_at ? formatDate(row.last_login_at) : '从未' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showEdit(row)">编辑</el-button>
              <el-popconfirm v-if="row.role !== 'super_admin'" title="确定删除该管理员？" @confirm="deleteAdmin(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
              <el-tag v-else type="info" size="small">受保护</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑管理员' : '新增管理员'" width="480px">
      <el-form :model="dialog.form" :rules="dialog.isEdit ? editRules : rules" ref="formRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="dialog.form.username" :disabled="dialog.isEdit" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="dialog.form.name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="dialog.form.email" placeholder="邮箱地址（选填）" />
        </el-form-item>
        <el-form-item :label="dialog.isEdit ? '新密码' : '密码'" :prop="dialog.isEdit ? '' : 'password'">
          <el-input v-model="dialog.form.password" type="password" :placeholder="dialog.isEdit ? '留空则不修改' : '登录密码'" show-password />
        </el-form-item>
        <el-form-item v-if="dialog.isEdit" label="状态">
          <el-switch v-model="dialog.form.is_active" :disabled="dialog.form.role === 'super_admin'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="saveAdmin">保存</el-button>
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
const admins = ref([])
const formRef = ref(null)

const dialog = reactive({
  visible: false,
  isEdit: false,
  loading: false,
  form: { id: null, username: '', name: '', email: '', password: '', is_active: true, role: '' }
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }]
}

const editRules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }]
}

const formatDate = (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : ''

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.admins.list()
    admins.value = res.items || []
  } catch (e) {}
  loading.value = false
}

const showCreate = () => {
  dialog.isEdit = false
  dialog.form = { id: null, username: '', name: '', email: '', password: '', is_active: true, role: '' }
  dialog.visible = true
}

const showEdit = (row) => {
  dialog.isEdit = true
  dialog.form = { id: row.id, username: row.username, name: row.name, email: row.email || '', password: '', is_active: row.is_active, role: row.role }
  dialog.visible = true
}

const saveAdmin = async () => {
  try {
    await formRef.value?.validate()
  } catch { return }

  dialog.loading = true
  try {
    if (dialog.isEdit) {
      const data = { name: dialog.form.name, email: dialog.form.email, is_active: dialog.form.is_active }
      if (dialog.form.password) data.password = dialog.form.password
      await api.admins.update(dialog.form.id, data)
    } else {
      await api.admins.create(dialog.form)
    }
    ElMessage.success('保存成功')
    dialog.visible = false
    loadData()
  } catch (e) {}
  dialog.loading = false
}

const deleteAdmin = async (admin) => {
  try {
    await api.admins.delete(admin.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
