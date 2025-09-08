import React, { useState } from 'react';
import { Card, Form, Input, Button, Typography, Alert } from 'antd';
import { authAPI } from '../services/api';

const { Title, Text } = Typography;

const Login = ({ onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const onFinish = async (values) => {
    setLoading(true);
    setError('');
    try {
      const res = await authAPI.login(values.username, values.password);
      const token = res.data?.access_token;
      if (token) {
        localStorage.setItem('auth_token', token);
        if (onSuccess) onSuccess();
      } else {
        setError('Login failed: token not received');
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f5f7fa' }}>
      <Card style={{ width: 380, boxShadow: '0 8px 24px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <Title level={3} style={{ margin: 0 }}>ComplyLite</Title>
          <Text type="secondary">Sign in to continue</Text>
        </div>
        {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
          <Form.Item label="Username" name="username" rules={[{ required: true, message: 'Please enter your username' }]}>
            <Input size="large" placeholder="admin" autoFocus />
          </Form.Item>
          <Form.Item label="Password" name="password" rules={[{ required: true, message: 'Please enter your password' }]}>
            <Input.Password size="large" placeholder="admin123" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block size="large">
            Sign In
          </Button>
        </Form>
      </Card>
    </div>
  );
};

export default Login;


