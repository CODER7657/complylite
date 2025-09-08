import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography, Space, Button } from 'antd';
import { 
  DashboardOutlined, 
  AlertOutlined, 
  UploadOutlined,
  SettingOutlined
} from '@ant-design/icons';
import Dashboard from './components/Dashboard';
import AlertsPage from './components/AlertsPage';
import DataUploadPage from './components/DataUploadPage';
import RuleSettingsPage from './components/RuleSettingsPage';
import Login from './components/Login';
import './App.css';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

// Navigation component that uses React Router hooks
const AppContent = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const getCurrentPageTitle = () => {
    switch(location.pathname) {
      case '/': case '/dashboard': return 'Compliance Surveillance Dashboard';
      case '/alerts': return 'Alert Management';
      case '/upload': return 'Data Upload & Management';
      case '/settings': return 'Rule Configuration';
      default: return 'ComplyLite';
    }
  };

  const handleMenuClick = ({ key }) => {
    switch(key) {
      case 'dashboard':
        navigate('/dashboard');
        break;
      case 'alerts':
        navigate('/alerts');
        break;
      case 'upload':
        navigate('/upload');
        break;
      case 'settings':
        navigate('/settings');
        break;
      default:
        navigate('/dashboard');
    }
  };

  const getSelectedKey = () => {
    switch(location.pathname) {
      case '/': case '/dashboard': return ['dashboard'];
      case '/alerts': return ['alerts'];
      case '/upload': return ['upload'];
      case '/settings': return ['settings'];
      default: return ['dashboard'];
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={250}>
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <Title level={3} style={{ color: 'white', margin: 0 }}>
            ComplyLite
          </Title>
        </div>
        <Menu
          theme="dark"
          selectedKeys={getSelectedKey()}
          mode="inline"
          onClick={handleMenuClick}
          items={[
            {
              key: 'dashboard',
              icon: <DashboardOutlined />,
              label: 'Dashboard',
            },
            {
              key: 'alerts',
              icon: <AlertOutlined />,
              label: 'Alerts',
            },
            {
              key: 'upload',
              icon: <UploadOutlined />,
              label: 'Data Upload',
            },
            {
              key: 'settings',
              icon: <SettingOutlined />,
              label: 'Rule Settings',
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>
            {getCurrentPageTitle()}
          </Title>
          <Button onClick={() => { localStorage.removeItem('auth_token'); window.location.replace('/login'); }}>Logout</Button>
        </Header>
  <Content style={{ margin: 0, background: '#f5f7fa' }}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/upload" element={<DataUploadPage />} />
            <Route path="/settings" element={<RuleSettingsPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

function App() {
  return (
    <Router>
      {localStorage.getItem('auth_token') ? (
        <AppContent />
      ) : (
        <Routes>
          <Route path="/login" element={<Login onSuccess={() => window.location.replace('/dashboard')} />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      )}
    </Router>
  );
}

export default App;
