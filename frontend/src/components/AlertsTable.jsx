import React, { useState } from 'react';
import { 
  Table, 
  Tag, 
  Button, 
  Space, 
  Modal, 
  Select,
  message,
  Typography,
  Descriptions,
  Badge 
} from 'antd';
import { 
  EyeOutlined
} from '@ant-design/icons';
import { alertsAPI } from '../services/api';

const { Text } = Typography;
const { Option } = Select;

const AlertsTable = ({ 
  alerts = [], 
  showPagination = true, 
  size = 'default',
  onRefresh 
}) => {
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [updating, setUpdating] = useState(false);

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'HIGH': return 'error';
      case 'MEDIUM': return 'warning';
      case 'LOW': return 'success';
      default: return 'default';
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'OPEN': return 'error';
      case 'IN_REVIEW': return 'warning';
      case 'CLOSED': return 'success';
      case 'FALSE_POSITIVE': return 'default';
      default: return 'processing';
    }
  };

  const handleViewDetails = (alert) => {
    setSelectedAlert(alert);
    setDetailsVisible(true);
  };

  const handleStatusUpdate = async (alertId, newStatus) => {
    setUpdating(true);
    try {
      await alertsAPI.updateAlertStatus(alertId, newStatus);
      message.success('Alert status updated successfully');
      setDetailsVisible(false);
      if (onRefresh) onRefresh();
    } catch (error) {
      message.error('Failed to update alert status');
    } finally {
      setUpdating(false);
    }
  };

  // Helpers
  const toTitle = (val) => {
    const s = typeof val === 'string' ? val : '';
    if (!s) return '—';
    return s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (l) => l.toUpperCase());
  };

  const safeStatusText = (status) => {
    const s = typeof status === 'string' ? status : '';
    return s ? s.replace(/_/g, ' ') : 'UNKNOWN';
  };

  const safeIdShort = (val) => {
    const s = typeof val === 'string' ? val : String(val ?? '');
    return s ? `${s.substring(0, 8)}...` : '—';
  };

  const safeDate = (val) => {
    try {
      return val ? new Date(val).toLocaleDateString() : '—';
    } catch {
      return '—';
    }
  };

  const safeDateTime = (val) => {
    try {
      return val ? new Date(val).toLocaleString() : '—';
    } catch {
      return '—';
    }
  };

  const safeJsonPretty = (val) => {
    if (!val) return null;
    try {
      return JSON.stringify(JSON.parse(val), null, 2);
    } catch {
      // Not valid JSON, show as-is
      return String(val);
    }
  };

  const columns = [
    {
      title: 'Alert ID',
      dataIndex: 'alert_id',
      key: 'alert_id',
    render: (text) => (
        <Text code style={{ fontSize: '11px' }}>
      {safeIdShort(text)}
        </Text>
      ),
      width: 100,
    },
    {
      title: 'Rule',
      dataIndex: 'rule_name',
      key: 'rule_name',
    render: (text) => <Tag>{toTitle(text)}</Tag>,
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity) => (
        <Badge 
          status={getSeverityColor(severity)} 
          text={severity}
        />
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      width: 300,
    },
    {
      title: 'Client',
      dataIndex: 'client_id',
      key: 'client_id',
    },
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={getStatusColor(status)}>
          {safeStatusText(status)}
        </Tag>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date) => safeDate(date),
      width: 100,
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space size="small">
          <Button
            icon={<EyeOutlined />}
            size="small"
            onClick={() => handleViewDetails(record)}
          />
        </Space>
      ),
      width: 100,
    },
  ];

  return (
    <>
      <Table
        columns={columns}
        dataSource={alerts}
        rowKey="alert_id"
        size={size}
        pagination={showPagination ? {
          pageSize: 10,
          showSizeChanger: true,
          showQuickJumper: true,
        } : false}
        scroll={{ x: 800 }}
      />

      <Modal
        title="Alert Details"
        open={detailsVisible}
        onCancel={() => setDetailsVisible(false)}
        width={800}
        footer={[
          <Button key="close" onClick={() => setDetailsVisible(false)}>
            Close
          </Button>
        ]}
      >
        {selectedAlert && (
          <div>
            <Descriptions bordered size="small">
              <Descriptions.Item label="Alert ID" span={3}>
                <Text code>{selectedAlert.alert_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Rule">
                {toTitle(selectedAlert.rule_name)}
              </Descriptions.Item>
              <Descriptions.Item label="Severity">
                <Badge 
                  status={getSeverityColor(selectedAlert.severity)} 
                  text={selectedAlert.severity}
                />
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={getStatusColor(selectedAlert.status)}>
                  {safeStatusText(selectedAlert.status)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Client ID">
                {selectedAlert.client_id}
              </Descriptions.Item>
              <Descriptions.Item label="Symbol">
                {selectedAlert.symbol}
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {safeDateTime(selectedAlert.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="Description" span={3}>
                {selectedAlert.description}
              </Descriptions.Item>
            </Descriptions>

    {selectedAlert.data_json && (
              <div style={{ marginTop: 16 }}>
                <Text strong>Technical Details:</Text>
                <pre style={{ 
                  background: '#f5f5f5', 
                  padding: '12px', 
                  borderRadius: '4px',
                  fontSize: '12px',
                  marginTop: '8px'
                }}>
      {safeJsonPretty(selectedAlert.data_json)}
                </pre>
              </div>
            )}

            <div style={{ marginTop: 16 }}>
              <Text strong>Update Status: </Text>
              <Select
                value={selectedAlert.status}
                onChange={(value) => handleStatusUpdate(selectedAlert.alert_id, value)}
                loading={updating}
                style={{ width: 150, marginLeft: 8 }}
              >
                <Option value="OPEN">Open</Option>
                <Option value="IN_REVIEW">In Review</Option>
                <Option value="CLOSED">Closed</Option>
                <Option value="FALSE_POSITIVE">False Positive</Option>
              </Select>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};

export default AlertsTable;
