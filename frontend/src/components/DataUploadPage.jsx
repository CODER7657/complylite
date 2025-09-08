import React from 'react';
import { Card } from 'antd';
import UploadData from './UploadData';

const DataUploadPage = () => {
  return (
    <div className="page-wrap">
      <Card title="Data Management" className="card-section">
        <UploadData />
      </Card>
    </div>
  );
};

export default DataUploadPage;
