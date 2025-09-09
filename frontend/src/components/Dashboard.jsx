import React, { useState, useEffect } from 'react';
import { 
  Row, 
  Col, 
  Card, 
  Statistic, 
  Alert, 
  Spin, 
  Progress,
  Typography,
  Divider 
} from 'antd';
import { 
  AlertOutlined, 
  CheckCircleOutlined, 
  WarningOutlined,
  TrophyOutlined 
} from '@ant-design/icons';
import AlertsTable from './AlertsTable';
import { dashboardAPI } from '../services/api';

const { Title, Text } = Typography;

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [complianceScore, setComplianceScore] = useState({});
  const [recentActivity, setRecentActivity] = useState({});

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      const [statsRes, scoreRes, activityRes] = await Promise.all([
        dashboardAPI.getStats(),
        dashboardAPI.getComplianceScore(),
        dashboardAPI.getRecentActivity()
      ]);
      
      setStats(statsRes.data);
      setComplianceScore(scoreRes.data);
      setRecentActivity(activityRes.data);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 85) return '#52c41a';
    if (score >= 70) return '#1890ff';
    if (score >= 50) return '#faad14';
    return '#ff4d4f';
  };

  const getRiskLevelColor = (level) => {
    switch(level) {
      case 'LOW': return 'success';
      case 'MEDIUM': return 'warning';
      case 'HIGH': return 'error';
      default: return 'default';
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
        <div style={{ marginTop: '20px' }}>Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      {/* Compliance Score Section */}
      <Row gutter={[16,16]} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card className="card-section">
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="circle"
                percent={Math.round(complianceScore.compliance_score || 0)}
                strokeColor={getScoreColor(complianceScore.compliance_score)}
                size={120}
              />
              <div style={{ marginTop: 16 }}>
                <Title level={4} className="section-title">Compliance Score</Title>
                <Alert
                  message={`Risk Level: ${complianceScore.risk_level || 'UNKNOWN'}`}
                  type={getRiskLevelColor(complianceScore.risk_level)}
                  showIcon
                />
              </div>
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="System Overview" className="card-section">
            <Row gutter={16}>
              <Col span={12}>
                <Statistic
                  title="Total Trades"
                  value={stats.total_trades || 0}
                  prefix={<TrophyOutlined />}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Active Clients"
                  value={stats.total_clients || 0}
                  prefix={<CheckCircleOutlined />}
                />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      {/* Alert Statistics */}
    <Row gutter={[16,16]} style={{ marginBottom: 24 }}>
        <Col span={6}>
      <Card className="card-section">
            <Statistic
              title="Total Alerts"
              value={stats.total_alerts || 0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
      <Card className="card-section">
            <Statistic
              title="High Risk"
              value={stats.high_risk_alerts || 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col span={6}>
      <Card className="card-section">
            <Statistic
              title="Medium Risk"
              value={stats.medium_risk_alerts || 0}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
      <Card className="card-section">
            <Statistic
              title="Alerts Today"
              value={stats.alerts_today || 0}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Recent Activity */}
      <Row gutter={[16,16]} style={{ marginBottom: 24 }}>
        <Col span={16}>
          <Card title="Recent Alerts" className="card-section">
            {(recentActivity.recent_alerts || []).length === 0 ? (
              <Alert type="info" message="No recent alerts" showIcon />
            ) : (
              <div className="table-sticky table-zebra">
                <AlertsTable 
                  alerts={recentActivity.recent_alerts || []} 
                  showPagination={false}
                  size="small"
                />
              </div>
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card title="Active Trading Symbols" className="card-section">
            {(recentActivity.active_symbols || []).map((symbol, index) => (
              <div key={index} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Text strong>{symbol.symbol}</Text>
                  <Text>{symbol.trade_count} trades</Text>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Last: {new Date(symbol.last_trade).toLocaleTimeString()}
                </Text>
              </div>
            ))}
          </Card>
        </Col>
      </Row>

    </div>
  );
};

export default Dashboard;
