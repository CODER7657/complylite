import React, { useState, useEffect } from 'react';
import { Card, Button, Space, message, Spin, Empty } from 'antd';
import { ReloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import AlertsTable from './AlertsTable';
import { alertsAPI, dataAPI } from '../services/api';

const AlertsPage = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningDetection, setRunningDetection] = useState(false);

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    try {
      setLoading(true);
      const response = await alertsAPI.getAlerts({ limit: 100 });
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
      await fetchAlerts(); // Refresh alerts after detection
    } catch (error) {
      message.error('Detection failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setRunningDetection(false);
    }
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
              onClick={fetchAlerts}
            >
              Refresh
            </Button>
          </Space>
        }
      >
        {alerts.length === 0 ? (
          <Empty description="No alerts found. Try uploading data or running detection." />
        ) : (
          <div className="table-sticky table-zebra">
            <AlertsTable 
              alerts={alerts}
              onRefresh={fetchAlerts}
            />
          </div>
        )}
      </Card>
    </div>
  );
};

export default AlertsPage;
