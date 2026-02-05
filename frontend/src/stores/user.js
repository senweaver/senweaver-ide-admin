import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export const useUserStore = defineStore('user', () => {
    const user = ref(null)
    const token = ref(localStorage.getItem('admin_token'))

    const login = async (credentials) => {
        const res = await api.auth.login(credentials)
        if (res.success) {
            token.value = res.token
            user.value = res.user
            localStorage.setItem('admin_token', res.token)
        }
        return res
    }

    const fetchUser = async () => {
        try {
            user.value = await api.auth.me()
        } catch (e) {
            logout()
        }
    }

    const logout = () => {
        token.value = null
        user.value = null
        localStorage.removeItem('admin_token')
    }

    return { user, token, login, fetchUser, logout }
})
