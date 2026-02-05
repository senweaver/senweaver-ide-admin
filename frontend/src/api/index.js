import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const api = axios.create({
    baseURL: '/api/admin',
    timeout: 30000
})

api.interceptors.request.use(config => {
    const token = localStorage.getItem('admin_token')
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

api.interceptors.response.use(
    response => response.data,
    error => {
        if (error.response?.status === 401) {
            localStorage.removeItem('admin_token')
            router.push('/admin/login')
            ElMessage.error('登录已过期，请重新登录')
        } else {
            ElMessage.error(error.response?.data?.detail || '请求失败')
        }
        return Promise.reject(error)
    }
)

export default {
    auth: {
        login: (data) => api.post('/login', data),
        me: () => api.get('/me'),
        changePassword: (data) => api.post('/change-password', data)
    },
    stats: {
        dashboard: () => api.get('/stats/dashboard'),
        users: () => api.get('/stats/users'),
        orders: () => api.get('/stats/orders')
    },
    users: {
        list: (params) => api.get('/users', { params }),
        get: (id) => api.get(`/users/${id}`),
        update: (id, data) => api.put(`/users/${id}`, data),
        recharge: (id, data) => api.post(`/users/${id}/recharge`, data),
        adjustBalance: (id, data) => api.post(`/users/${id}/adjust-balance`, data),
        setVip: (id, data) => api.post(`/users/${id}/vip`, data),
        toggle: (id) => api.post(`/users/${id}/toggle`),
        delete: (id) => api.delete(`/users/${id}`),
        getModelAccess: (userId) => api.get('/users/model-access', { params: { user_id: userId } }),
        updateModelAccess: (data) => api.post('/users/model-access', data),
        online: () => api.get('/users/online'),
        vip: (params) => api.get('/users/vip', { params })
    },
    orders: {
        list: (params) => api.get('/orders', { params }),
        get: (id) => api.get(`/orders/${id}`),
        create: (data) => api.post('/orders', data),
        pay: (id) => api.post(`/orders/${id}/pay`),
        cancel: (id) => api.post(`/orders/${id}/cancel`),
        refund: (id) => api.post(`/orders/${id}/refund`)
    },
    transactions: {
        list: (params) => api.get('/transactions', { params })
    },
    packages: {
        list: () => api.get('/packages'),
        create: (data) => api.post('/packages', data),
        update: (id, data) => api.put(`/packages/${id}`, data),
        delete: (id) => api.delete(`/packages/${id}`)
    },
    articles: {
        list: (params) => api.get('/articles', { params }),
        get: (id) => api.get(`/articles/${id}`),
        create: (data) => api.post('/articles', data),
        update: (id, data) => api.put(`/articles/${id}`, data),
        delete: (id) => api.delete(`/articles/${id}`),
        publish: (id) => api.post(`/articles/${id}/publish`),
        categories: () => api.get('/articles/categories')
    },
    comments: {
        list: (params) => api.get('/comments', { params }),
        approve: (id) => api.post(`/comments/${id}/approve`),
        delete: (id) => api.delete(`/comments/${id}`)
    },
    logs: {
        list: (params) => api.get('/logs', { params })
    },
    subscribers: {
        list: (params) => api.get('/subscribers', { params }),
        delete: (id) => api.delete(`/subscribers/${id}`)
    },
    admins: {
        list: () => api.get('/admins'),
        get: (id) => api.get(`/admins/${id}`),
        create: (data) => api.post('/admins', data),
        update: (id, data) => api.put(`/admins/${id}`, data),
        delete: (id) => api.delete(`/admins/${id}`)
    },
    versions: {
        list: () => api.get('/versions'),
        get: (id) => api.get(`/versions/${id}`),
        create: (data) => api.post('/versions', data),
        update: (id, data) => api.put(`/versions/${id}`, data),
        delete: (id) => api.delete(`/versions/${id}`),
        setLatest: (id) => api.post(`/versions/${id}/set-latest`)
    },
    keyPools: {
        providers: {
            list: () => api.get('/key-pools/providers'),
            create: (data) => api.post('/key-pools/providers', data),
            update: (id, data) => api.put(`/key-pools/providers/${id}`, data),
            delete: (id) => api.delete(`/key-pools/providers/${id}`)
        },
        pools: {
            list: (params) => api.get('/key-pools/pools', { params }),
            create: (data) => api.post('/key-pools/pools', data),
            batchCreate: (data) => api.post('/key-pools/pools/batch', data),
            update: (id, data) => api.put(`/key-pools/pools/${id}`, data),
            delete: (id) => api.delete(`/key-pools/pools/${id}`)
        },
        allocations: {
            list: (params) => api.get('/key-pools/allocations', { params })
        },
        stats: () => api.get('/key-pools/stats')
    }
}
