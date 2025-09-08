import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem('auth_token');
      if (window.location.pathname !== '/login') {
        window.location.replace('/login');
      }
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (username, password) => api.post('/api/v1/auth/login', { username, password }),
};

export const dataAPI = {
  uploadCSV: (file, tableType) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('table_type', tableType);
    return api.post('/api/v1/data/upload/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  
  getTableInfo: () => api.get('/api/v1/data/tables/info'),
  
  runDetection: () => api.post('/api/v1/data/run-detection'),

  clearTable: (tableType) => api.delete('/api/v1/data/clear', { params: { table_type: tableType } }),

  clearAll: () => api.delete('/api/v1/data/clear-all'),
};

export const alertsAPI = {
  getAlerts: (params = {}) => api.get('/api/v1/alerts', { params }),
  
  getAlertStats: () => api.get('/api/v1/alerts/stats'),
  
  updateAlertStatus: (alertId, status) => 
    api.put(`/api/v1/alerts/${alertId}/status`, null, { params: { status } }),
};

export const dashboardAPI = {
  getStats: () => api.get('/api/v1/dashboard/stats'),
  
  getRecentActivity: () => api.get('/api/v1/dashboard/recent-activity'),
  
  getComplianceScore: () => api.get('/api/v1/dashboard/compliance-score'),
};

export default api;
