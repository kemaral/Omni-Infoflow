import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    {
        path: '/',
        redirect: '/dashboard',
    },
    {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
    },
    {
        path: '/plugins',
        name: 'Plugins',
        component: () => import('../views/Plugins.vue'),
    },
    {
        path: '/setup',
        name: 'Setup',
        component: () => import('../views/Setup.vue'),
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

export default router
