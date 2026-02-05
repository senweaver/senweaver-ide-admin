<template>
  <div>
    <div class="page-header">
      <h2>充值套餐</h2>
      <p>管理充值套餐</p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <h3>套餐列表</h3>
        <el-button type="primary" :icon="Plus" @click="showCreate">新增套餐</el-button>
      </div>
      <div class="panel-body">
        <el-table :data="packages" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="名称" width="150" />
          <el-table-column prop="price" label="价格" width="120">
            <template #default="{ row }">¥{{ row.price }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="充值金额" width="120">
            <template #default="{ row }">¥{{ row.amount }}</template>
          </el-table-column>
          <el-table-column prop="bonus" label="赠送" width="100">
            <template #default="{ row }">¥{{ row.bonus || 0 }}</template>
          </el-table-column>
          <el-table-column prop="is_hot" label="热门" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_hot" type="danger">热门</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="showEdit(row)">编辑</el-button>
              <el-popconfirm title="确定删除？" @confirm="deletePackage(row)">
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑套餐' : '新增套餐'" width="450px">
      <el-form :model="dialog.form" label-width="80px">
        <el-form-item label="名称"><el-input v-model="dialog.form.name" /></el-form-item>
        <el-form-item label="价格"><el-input-number v-model="dialog.form.price" :min="1" /></el-form-item>
        <el-form-item label="充值金额"><el-input-number v-model="dialog.form.amount" :min="1" /></el-form-item>
        <el-form-item label="赠送"><el-input-number v-model="dialog.form.bonus" :min="0" /></el-form-item>
        <el-form-item label="热门"><el-switch v-model="dialog.form.is_hot" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="savePackage">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/api'

const loading = ref(false)
const packages = ref([])
const dialog = reactive({
  visible: false, isEdit: false, loading: false,
  form: { name: '', price: 100, amount: 100, bonus: 0, is_hot: false }
})

const loadData = async () => {
  loading.value = true
  try {
    packages.value = await api.packages.list() || []
  } catch (e) {}
  loading.value = false
}

const showCreate = () => {
  dialog.isEdit = false
  dialog.form = { name: '', price: 100, amount: 100, bonus: 0, is_hot: false }
  dialog.visible = true
}

const showEdit = (pkg) => {
  dialog.isEdit = true
  dialog.form = { ...pkg }
  dialog.visible = true
}

const savePackage = async () => {
  dialog.loading = true
  try {
    if (dialog.isEdit) {
      await api.packages.update(dialog.form.id, dialog.form)
    } else {
      await api.packages.create(dialog.form)
    }
    ElMessage.success('保存成功')
    dialog.visible = false
    loadData()
  } catch (e) {}
  dialog.loading = false
}

const deletePackage = async (pkg) => {
  try {
    await api.packages.delete(pkg.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {}
}

onMounted(loadData)
</script>
