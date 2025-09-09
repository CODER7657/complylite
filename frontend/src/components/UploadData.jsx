import React, { useState } from 'react';
import { 
  Upload, 
  Button, 
  Select, 
  message, 
  Card, 
  Row, 
  Col, 
  Statistic,
  Space,
  Progress,
  Alert
} from 'antd';
import { 
  UploadOutlined, 
  PlayCircleOutlined, 
  InfoCircleOutlined,
  DeleteOutlined 
} from '@ant-design/icons';
import { dataAPI } from '../services/api';

const { Option } = Select;
const { Dragger } = Upload;

const UploadData = ({ onUploadSuccess }) => {
  const [uploading, setUploading] = useState(false);
  const [tableType, setTableType] = useState('trades');
  const [runningDetection, setRunningDetection] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const handleUpload = async (file) => {
    if (!file.name.endsWith('.csv')) {
      message.error('Please upload a CSV file');
      return false;
    }

    setUploading(true);
    setUploadProgress(0);

    // Simulate upload progress
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => prev < 90 ? prev + 10 : prev);
    }, 200);

    try {
      const response = await dataAPI.uploadCSV(file, tableType);
      
      clearInterval(progressInterval);
      setUploadProgress(100);

      message.success(
        `Successfully uploaded ${response.data.records_uploaded} records!`
      );
      
      if (response.data.new_alerts_generated > 0) {
        message.info(
          `Generated ${response.data.new_alerts_generated} new alerts`
        );
      }

      if (onUploadSuccess) {
        onUploadSuccess();
      }
    } catch (error) {
      clearInterval(progressInterval);
      message.error('Upload failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
      setTimeout(() => setUploadProgress(0), 1000);
    }

    return false; // Prevent default upload behavior
  };

  const handleRunDetection = async () => {
    setRunningDetection(true);
    try {
      const response = await dataAPI.runDetection();
      message.success(
        `Detection completed! Generated ${response.data.alerts_generated} alerts`
      );
      if (onUploadSuccess) {
        onUploadSuccess();
      }
    } catch (error) {
      message.error('Detection failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setRunningDetection(false);
    }
  };

  const handleClearTable = async () => {
    try {
      await dataAPI.clearTable(tableType);
      message.success(`${tableType} table cleared successfully`);
      if (onUploadSuccess) {
        onUploadSuccess();
      }
    } catch (error) {
      message.error('Clear failed: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleClearAll = async () => {
    try {
      await dataAPI.clearAll();
      message.success('All data cleared successfully');
      if (onUploadSuccess) {
        onUploadSuccess();
      }
    } catch (error) {
      message.error('Clear all failed: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getTableTypeDescription = (type) => {
    switch(type) {
      case 'orders':
        return 'Order data with order_id, client_id, symbol, side, quantity, price, timestamp';
      case 'trades':
        return 'Trade execution data with trade_id, client_id, symbol, side, quantity, price, timestamp';
      case 'clients':
        return 'Client information with client_id, client_name, and optional risk details';
      default:
        return '';
    }
  };

  return (
    <div>
      <Row gutter={16}>
        <Col span={16}>
          <Card title="CSV Data Upload" className="card-section" extra={
            <Space>
              <Select 
                value={tableType} 
                onChange={setTableType}
                style={{ width: 120 }}
              >
                <Option value="orders">Orders</Option>
                <Option value="trades">Trades</Option>
                <Option value="clients">Clients</Option>
              </Select>
            </Space>
          }>
            <Alert
              message="Data Format"
              description={getTableTypeDescription(tableType)}
              type="info"
              icon={<InfoCircleOutlined />}
              style={{ marginBottom: 16 }}
            />

            <Dragger
              name="file"
              accept=".csv"
              beforeUpload={handleUpload}
              showUploadList={false}
              className="dropzone"
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined style={{ fontSize: '48px', color: '#1890ff' }} />
              </p>
              <p className="ant-upload-text">
                Click or drag CSV file to this area to upload
              </p>
              <p className="ant-upload-hint">
                Upload {tableType} data in CSV format. The system will automatically 
                validate the data and trigger compliance detection if applicable.
              </p>
            </Dragger>

            {uploading && uploadProgress > 0 && (
              <div style={{ marginTop: 16 }}>
                <Progress 
                  percent={uploadProgress} 
                  status={uploadProgress === 100 ? 'success' : 'active'}
                />
              </div>
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="Detection Controls" className="card-section">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleRunDetection}
                loading={runningDetection}
                block
              >
                Run Compliance Detection
              </Button>

              <Alert
                message="Manual Detection"
                description="Click to manually run all compliance detection algorithms on current data"
                type="warning"
                showIcon
              />

              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleClearTable}
                block
                style={{ marginTop: '16px' }}
              >
                Clear {tableType} Table
              </Button>

              <Button
                danger
                type="primary"
                icon={<DeleteOutlined />}
                onClick={handleClearAll}
                block
              >
                Clear All Data
              </Button>

              <div>
                <Statistic
                  title="Detection Rules Active"
                  value={3}
                  suffix="/ 3"
                />
                <ul style={{ fontSize: '12px', marginTop: '8px' }}>
                  <li>Self-Trade Detection</li>
                  <li>Wash Trade Analysis</li>
                  <li>High Frequency Patterns</li>
                </ul>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default UploadData;
