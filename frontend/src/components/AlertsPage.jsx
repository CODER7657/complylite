import React, { useState, useEffect } from 'react';
import { Card, Button, Space, message, Spin, Empty, Input } from 'antd';
import { ReloadOutlined, PlayCircleOutlined, SearchOutlined } from '@ant-design/icons';
import AlertsTable from './AlertsTable';
import { alertsAPI, dataAPI } from '../services/api';

const AlertsPage = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningDetection, setRunningDetection] = useState(false);
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async (search = null) => {
    try {
      setLoading(true);
      const params = { limit: 100 };
      if (search) {
        params.search = search;
      }
      const response = await alertsAPI.getAlerts(params);
      setAlerts(response.data);
    } catch (error) {
      message.error('Failed to fetch alerts: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleRunDetection = async () => {
    setRunningDetection(true);
    try {
      const response = await dataAPI.runDetection();
      message.success(
        `Detection completed! Generated ${response.data.alerts_generated} new alerts`
      );
      await handleRefresh(); // Refresh alerts after detection
    } catch (error) {
      message.error('Detection failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setRunningDetection(false);
    }
  };

  const handleSearch = (value) => {
    setSearchText(value);
    fetchAlerts(value || null);
  };

  const handleRefresh = () => {
    fetchAlerts(searchText || null);
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <div style={{ marginTop: '20px' }}>Loading alerts...</div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      <Card 
        title="Compliance Alerts" 
        extra={
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleRunDetection}
              loading={runningDetection}
            >
              Run Detection
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
            >
              Refresh
            </Button>
          </Space>
        }
      >
        <div style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="Search alerts by description, client ID, symbol, or rule name..."
            allowClear
            enterButton={<SearchOutlined />}
            size="large"
            onSearch={handleSearch}
            onChange={(e) => {
              if (e.target.value === '') {
                handleSearch('');
              }
            }}
            style={{ width: '100%' }}
          />
        </div>
        {alerts.length === 0 ? (
          <Empty description="No alerts found. Try uploading data or running detection." />
        ) : (
          <div className="table-sticky table-zebra">
            <AlertsTable 
              alerts={alerts}
              onRefresh={handleRefresh}
            />
          </div>
        )}
      </Card>
    </div>
  );
};

export default AlertsPage;
