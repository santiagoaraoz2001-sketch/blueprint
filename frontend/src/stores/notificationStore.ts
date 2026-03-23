import { create } from 'zustand'

export interface Notification {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  message: string
  timestamp: string
  read: boolean
}

interface NotificationState {
  notifications: Notification[]
  unreadCount: number

  addNotification: (type: Notification['type'], title: string, message: string) => void
  markRead: (id: string) => void
  markAllRead: () => void
  clearAll: () => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (type, title, message) => {
    const notification: Notification = {
      id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      type,
      title,
      message,
      timestamp: new Date().toISOString(),
      read: false,
    }
    set((s) => ({
      notifications: [notification, ...s.notifications].slice(0, 100), // keep last 100
      unreadCount: s.unreadCount + 1,
    }))
  },

  markRead: (id) => {
    set((s) => {
      const updated = s.notifications.map((n) =>
        n.id === id && !n.read ? { ...n, read: true } : n
      )
      const wasUnread = s.notifications.find((n) => n.id === id && !n.read)
      return {
        notifications: updated,
        unreadCount: wasUnread ? Math.max(0, s.unreadCount - 1) : s.unreadCount,
      }
    })
  },

  markAllRead: () => {
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }))
  },

  clearAll: () => {
    set({ notifications: [], unreadCount: 0 })
  },
}))
