<template>
  <div class="admin-layout">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-logo">
        <img class="logo-icon" src="@/assets/logo.svg" alt="Logo" />
        <span v-if="!sidebarCollapsed" class="logo-text">Senweaver</span>
      </div>
      <div class="sidebar-menu">
        <el-menu :default-active="route.path" :collapse="sidebarCollapsed" router>
          <el-menu-item index="/admin/dashboard">
            <el-icon><Odometer /></el-icon>
            <span>仪表盘</span>
          </el-menu-item>
          <el-sub-menu index="users">
            <template #title>
              <el-icon><User /></el-icon>
              <span>用户中心</span>
            </template>
            <el-menu-item index="/admin/users">用户列表</el-menu-item>
            <el-menu-item index="/admin/users/vip">VIP管理</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="finance">
            <template #title>
              <el-icon><Wallet /></el-icon>
              <span>财务管理</span>
            </template>
            <el-menu-item index="/admin/orders">订单管理</el-menu-item>
            <el-menu-item index="/admin/transactions">交易流水</el-menu-item>
            <el-menu-item index="/admin/packages">充值套餐</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="content">
            <template #title>
              <el-icon><Document /></el-icon>
              <span>内容管理</span>
            </template>
            <el-menu-item index="/admin/articles">文章管理</el-menu-item>
            <el-menu-item index="/admin/comments">评论管理</el-menu-item>
          </el-sub-menu>
          <el-sub-menu index="system">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/admin/logs">连接日志</el-menu-item>
            <el-menu-item index="/admin/subscribers">订阅者</el-menu-item>
            <el-menu-item index="/admin/admins">管理员</el-menu-item>
            <el-menu-item index="/admin/versions">版本管理</el-menu-item>
            <el-menu-item index="/admin/key-pools">密钥池管理</el-menu-item>
            <el-menu-item index="/admin/settings">系统设置</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </div>
    </aside>
    <div class="main-container">
      <header class="main-header">
        <div style="display: flex; align-items: center; gap: 16px;">
          <el-button :icon="sidebarCollapsed ? Expand : Fold" text @click="sidebarCollapsed = !sidebarCollapsed" />
          <el-breadcrumb>
            <el-breadcrumb-item>首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div style="display: flex; align-items: center; gap: 16px;">
          <span class="online-dot" title="在线"></span>
          <el-dropdown @command="handleCommand">
            <div style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
              <el-avatar :size="36" style="background: linear-gradient(135deg, var(--primary-color), var(--primary-hover)); color: #000;">
                {{ userStore.user?.name?.[0] || 'A' }}
              </el-avatar>
              <span style="color: var(--text-primary);">{{ userStore.user?.name || '管理员' }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="settings">系统设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Odometer, User, Wallet, Document, Setting, Expand, Fold } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const sidebarCollapsed = ref(false)

const titles = {
  '/admin/dashboard': '仪表盘',
  '/admin/users': '用户列表',
  '/admin/users/vip': 'VIP管理',
  '/admin/orders': '订单管理',
  '/admin/transactions': '交易流水',
  '/admin/packages': '充值套餐',
  '/admin/articles': '文章管理',
  '/admin/comments': '评论管理',
  '/admin/logs': '连接日志',
  '/admin/subscribers': '订阅者',
  '/admin/admins': '管理员管理',
  '/admin/versions': '版本管理',
  '/admin/key-pools': '密钥池管理',
  '/admin/settings': '系统设置'
}

const currentTitle = computed(() => titles[route.path] || '仪表盘')

const handleCommand = (cmd) => {
  if (cmd === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
      .then(() => {
        userStore.logout()
        router.push('/admin/login')
        ElMessage.success('已退出登录')
      }).catch(() => {})
  } else if (cmd === 'settings') {
    router.push('/admin/settings')
  }
}

onMounted(() => {
  userStore.fetchUser()
})
</script>

<style scoped>
.logo-icon {
  width: 28px;
  height: 28px;
  display: inline-block;
}

.online-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--success-color);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15);
}
</style>
