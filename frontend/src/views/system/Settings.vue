<template>
  <div>
    <div class="page-header">
      <h2>系统设置</h2>
      <p>管理系统配置</p>
    </div>
    
    <el-row :gutter="20">
      <el-col :span="12">
        <div class="panel">
          <div class="panel-header">
            <h3>修改密码</h3>
          </div>
          <div class="panel-body">
            <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="100px">
              <el-form-item label="当前密码" prop="oldPassword">
                <el-input v-model="passwordForm.oldPassword" type="password" show-password />
              </el-form-item>
              <el-form-item label="新密码" prop="newPassword">
                <el-input v-model="passwordForm.newPassword" type="password" show-password />
              </el-form-item>
              <el-form-item label="确认密码" prop="confirmPassword">
                <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="passwordLoading" @click="changePassword">修改密码</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="panel">
          <div class="panel-header">
            <h3>系统信息</h3>
          </div>
          <div class="panel-body">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="系统版本">2.8.3</el-descriptions-item>
              <el-descriptions-item label="后端框架">FastAPI</el-descriptions-item>
              <el-descriptions-item label="前端框架">Vue 3 + Vite</el-descriptions-item>
              <el-descriptions-item label="UI组件">Element Plus</el-descriptions-item>
              <el-descriptions-item label="数据库">PostgreSQL</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const passwordFormRef = ref(null)
const passwordLoading = ref(false)

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const validateConfirm = (rule, value, callback) => {
  if (value !== passwordForm.newPassword) {
    callback(new Error('两次输入密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' }
  ]
}

const changePassword = async () => {
  try {
    await passwordFormRef.value?.validate()
  } catch { return }

  passwordLoading.value = true
  try {
    await api.auth.changePassword({
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword
    })
    ElMessage.success('密码修改成功')
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch (e) {}
  passwordLoading.value = false
}
</script>
