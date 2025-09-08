import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_sample_data():
    """Generate realistic sample data with suspicious patterns for demo"""
    
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Generate clients
    clients = []
    for i in range(50):
        clients.append({
            'client_id': f'CLIENT_{i:03d}',
            'client_name': f'Client Company {i+1}',
            'client_type': random.choice(['INDIVIDUAL', 'CORPORATE', 'INSTITUTIONAL']),
            'risk_rating': random.choice(['LOW', 'MEDIUM', 'HIGH']),
            'account_status': 'ACTIVE',
            'created_date': datetime.now() - timedelta(days=random.randint(30, 365))
        })
    
    clients_df = pd.DataFrame(clients)
    clients_df.to_csv('data/sample_clients.csv', index=False)
    
    # Generate orders and trades with suspicious patterns
    symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX']
    client_ids = [f'CLIENT_{i:03d}' for i in range(50)]
    
    orders = []
    trades = []
    
    base_time = datetime.now() - timedelta(days=7)
