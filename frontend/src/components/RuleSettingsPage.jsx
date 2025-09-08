import React, { useState } from 'react';
import { 
  Card, 
  List, 
  Switch, 
  Slider, 
  InputNumber, 
  Row, 
  Col, 
  Typography, 
  Divider,
  Alert,
  Space,
  Tag,
  Button,
  message
} from 'antd';
import { 
  SettingOutlined, 
  SaveOutlined,
  ReloadOutlined 
} from '@ant-design/icons';

const { Title, Text } = Typography;

const RuleSettingsPage = () => {
  const [settings, setSettings] = useState({
    selfTradeDetection: {
      enabled: true,
      timeWindow: 24, // hours
      minTradePairs: 4,
      offsettingThreshold: 0.7
    },
    washTradeDetection: {
      enabled: true,
      timeWindow: 7, // days
      minTradeCount: 6,
      positionThreshold: 0.1
    },
    highFrequencyDetection: {
      enabled: true,
      tradesPerHour: 50,
      alertThreshold: 100
    }
  });

  const [saving, setSaving] = useState(false);

  const handleSettingChange = (rule, field, value) => {
    setSettings(prev => ({
      ...prev,
      [rule]: {
        ...prev[rule],
        [field]: value
      }
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Simulate API call to save settings
      await new Promise(resolve => setTimeout(resolve, 1000));
      message.success('Rule settings saved successfully');
    } catch (error) {
      message.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSettings({
      selfTradeDetection: {
        enabled: true,
        timeWindow: 24,
        minTradePairs: 4,
        offsettingThreshold: 0.7
      },
      washTradeDetection: {
        enabled: true,
        timeWindow: 7,
        minTradeCount: 6,
        positionThreshold: 0.1
      },
      highFrequencyDetection: {
        enabled: true,
        tradesPerHour: 50,
        alertThreshold: 100
      }
    });
    message.info('Settings reset to defaults');
  };

  const ruleConfigs = [
    {
      key: 'selfTradeDetection',
      title: 'Self-Trade Detection',
      description: 'Detects when a client trades against themselves within a time window',
      severity: 'HIGH',
      fields: [
        {
          label: 'Time Window (hours)',
          key: 'timeWindow',
          type: 'number',
          min: 1,
          max: 168,
          tooltip: 'Time window to look for self-trades'
        },
        {
          label: 'Minimum Trade Pairs',
          key: 'minTradePairs',
          type: 'number',
          min: 2,
          max: 20,
          tooltip: 'Minimum number of trade pairs to trigger alert'
        },
        {
          label: 'Offsetting Threshold',
          key: 'offsettingThreshold',
          type: 'slider',
          min: 0.1,
          max: 1,
          step: 0.1,
          tooltip: 'Percentage of trades that must be offsetting'
        }
      ]
    },
    {
      key: 'washTradeDetection',
      title: 'Wash Trade Detection',
      description: 'Identifies wash trading patterns with near-zero net positions',
      severity: 'HIGH',
      fields: [
        {
          label: 'Time Window (days)',
          key: 'timeWindow',
          type: 'number',
          min: 1,
          max: 30,
          tooltip: 'Time window for wash trade analysis'
        },
        {
          label: 'Minimum Trade Count',
          key: 'minTradeCount',
          type: 'number',
          min: 4,
          max: 50,
          tooltip: 'Minimum trades required to trigger alert'
        },
        {
          label: 'Position Threshold',
          key: 'positionThreshold',
          type: 'slider',
          min: 0.01,
          max: 0.5,
          step: 0.01,
          tooltip: 'Maximum net position as percentage of average quantity'
        }
      ]
    },
    {
      key: 'highFrequencyDetection',
      title: 'High Frequency Pattern Detection',
      description: 'Flags suspicious high-frequency trading patterns',
      severity: 'MEDIUM',
      fields: [
        {
          label: 'Trades per Hour Threshold',
          key: 'tradesPerHour',
          type: 'number',
          min: 10,
          max: 500,
          tooltip: 'Trades per hour to trigger monitoring'
        },
        {
          label: 'Alert Threshold',
          key: 'alertThreshold',
          type: 'number',
          min: 50,
          max: 1000,
          tooltip: 'Trades per hour to trigger high severity alert'
        }
      ]
    }
  ];

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'HIGH': return 'error';
      case 'MEDIUM': return 'warning';
      case 'LOW': return 'success';
      default: return 'default';
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <Card 
        title={
          <Space>
            <SettingOutlined />
            <span>Compliance Rule Settings</span>
          </Space>
        }
        extra={
          <Space>
            <Button onClick={handleReset}>
              <ReloadOutlined /> Reset to Defaults
            </Button>
            <Button 
              type="primary" 
              onClick={handleSave}
              loading={saving}
            >
              <SaveOutlined /> Save Settings
            </Button>
          </Space>
        }
      >
        <Alert
          message="Rule Configuration"
          description="Configure detection algorithms and thresholds for compliance surveillance. Changes take effect immediately for new trades."
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />

        <List
          itemLayout="vertical"
          dataSource={ruleConfigs}
          renderItem={(rule) => (
            <List.Item key={rule.key}>
              <Card size="small">
                <Row gutter={16}>
                  <Col span={18}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <Title level={5} style={{ margin: 0 }}>
                          {rule.title}
                          <Tag 
                            color={getSeverityColor(rule.severity)} 
                            style={{ marginLeft: 8 }}
                          >
                            {rule.severity}
                          </Tag>
                        </Title>
                        <Text type="secondary">{rule.description}</Text>
                      </div>
                      
                      <Row gutter={16}>
                        {rule.fields.map((field) => (
                          <Col span={8} key={field.key}>
                            <div style={{ marginBottom: 16 }}>
                              <Text strong>{field.label}:</Text>
                              {field.type === 'slider' ? (
                                <Slider
                                  min={field.min}
                                  max={field.max}
                                  step={field.step}
                                  value={settings[rule.key][field.key]}
                                  onChange={(value) => 
                                    handleSettingChange(rule.key, field.key, value)
                                  }
                                  tooltip={{ formatter: (value) => `${value}` }}
                                />
                              ) : (
                                <InputNumber
                                  min={field.min}
                                  max={field.max}
                                  value={settings[rule.key][field.key]}
                                  onChange={(value) => 
                                    handleSettingChange(rule.key, field.key, value)
                                  }
                                  style={{ width: '100%' }}
                                />
                              )}
                            </div>
                          </Col>
                        ))}
                      </Row>
                    </Space>
                  </Col>
                  <Col span={6} style={{ textAlign: 'right' }}>
                    <Space direction="vertical">
                      <Text strong>Rule Status</Text>
                      <Switch
                        checked={settings[rule.key].enabled}
                        onChange={(checked) => 
                          handleSettingChange(rule.key, 'enabled', checked)
                        }
                        checkedChildren="ON"
                        unCheckedChildren="OFF"
                      />
                    </Space>
                  </Col>
                </Row>
              </Card>
            </List.Item>
          )}
        />

        <Divider />
        
        <Alert
          message="Current Configuration Summary"
          description={
            <div>
              <p><strong>Active Rules:</strong> {Object.values(settings).filter(rule => rule.enabled).length} / {Object.keys(settings).length}</p>
              <p><strong>Detection Modes:</strong> Real-time monitoring enabled</p>
              <p><strong>Alert Delivery:</strong> Database storage with dashboard notifications</p>
            </div>
          }
          type="success"
          showIcon
        />
      </Card>
    </div>
  );
};

export default RuleSettingsPage;
