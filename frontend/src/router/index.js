import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    {
        path: '/admin/login',
        name: 'Login',
        component: () => import('@/views/Login.vue')
    },
    {
        path: '/admin',
        component: () => import('@/layouts/AdminLayout.vue'),
        redirect: '/admin/dashboard',
        children: [
            { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
            { path: 'users', name: 'Users', component: () => import('@/views/users/UserList.vue') },
            { path: 'users/vip', name: 'VipUsers', component: () => import('@/views/users/VipUsers.vue') },
            { path: 'orders', name: 'Orders', component: () => import('@/views/finance/Orders.vue') },
            { path: 'transactions', name: 'Transactions', component: () => import('@/views/finance/Transactions.vue') },
            { path: 'packages', name: 'Packages', component: () => import('@/views/finance/Packages.vue') },
            { path: 'articles', name: 'Articles', component: () => import('@/views/content/Articles.vue') },
            { path: 'comments', name: 'Comments', component: () => import('@/views/content/Comments.vue') },
            { path: 'logs', name: 'Logs', component: () => import('@/views/system/Logs.vue') },
            { path: 'subscribers', name: 'Subscribers', component: () => import('@/views/system/Subscribers.vue') },
            { path: 'admins', name: 'Admins', component: () => import('@/views/system/Admins.vue') },
            { path: 'versions', name: 'Versions', component: () => import('@/views/system/Versions.vue') },
            { path: 'key-pools', name: 'KeyPools', component: () => import('@/views/system/KeyPools.vue') },
            { path: 'settings', name: 'Settings', component: () => import('@/views/system/Settings.vue') },
        ]
    },
    {
        path: '/:pathMatch(.*)*',
        redirect: '/admin'
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

router.beforeEach((to, from, next) => {
    const token = localStorage.getItem('admin_token')
    if (to.path !== '/admin/login' && !token) {
        next('/admin/login')
    } else if (to.path === '/admin/login' && token) {
        next('/admin/dashboard')
    } else {
        next()
    }
})

export default router
