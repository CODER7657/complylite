import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
