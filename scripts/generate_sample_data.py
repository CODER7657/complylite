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
    
    for i in range(2000):
        client_id = random.choice(client_ids)
        symbol = random.choice(symbols)
        side = random.choice(['BUY', 'SELL'])
        quantity = random.randint(100, 5000)
        base_price = random.uniform(50, 500)
        price = round(base_price + random.uniform(-5, 5), 2)
        timestamp = base_time + timedelta(
            days=random.randint(0, 6),
            hours=random.randint(9, 16),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )
        
        order_id = f'ORD_{i:06d}'
        trade_id = f'TRD_{i:06d}'
        
        # Add normal order/trade
        orders.append({
            'order_id': order_id,
            'client_id': client_id,
            'trader_id': f'TRADER_{random.randint(1,10):02d}',
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp,
            'order_type': random.choice(['MARKET', 'LIMIT', 'STOP'])
        })
        
        trades.append({
            'trade_id': trade_id,
            'order_id': order_id,
            'client_id': client_id,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price + random.uniform(-0.5, 0.5),
            'timestamp': timestamp + timedelta(seconds=random.randint(1, 300))
        })
        
        # Add suspicious patterns every 50th record
        if i % 50 == 0:
            # Self-trade pattern
            opposite_side = 'SELL' if side == 'BUY' else 'BUY'
            suspicious_time = timestamp + timedelta(minutes=random.randint(1, 30))
            
            suspicious_order_id = f'ORD_{i:06d}_SUS'
            suspicious_trade_id = f'TRD_{i:06d}_SUS'
            
            orders.append({
                'order_id': suspicious_order_id,
                'client_id': client_id,  # Same client
                'trader_id': f'TRADER_{random.randint(1,10):02d}',
                'symbol': symbol,  # Same symbol
                'side': opposite_side,  # Opposite side
                'quantity': quantity + random.randint(-50, 50),  # Similar quantity
                'price': price + random.uniform(-1, 1),  # Similar price
                'timestamp': suspicious_time,
                'order_type': 'LIMIT'
            })
            
            trades.append({
                'trade_id': suspicious_trade_id,
                'order_id': suspicious_order_id,
                'client_id': client_id,
                'symbol': symbol,
                'side': opposite_side,
                'quantity': quantity + random.randint(-50, 50),
                'price': price + random.uniform(-1, 1),
                'timestamp': suspicious_time + timedelta(seconds=random.randint(1, 100))
            })
        
        # Add high-frequency pattern every 100th record
        if i % 100 == 0:
            # Generate burst of trades
            burst_time = timestamp
            for burst in range(15):  # 15 trades in quick succession
                burst_order_id = f'ORD_{i:06d}_BURST_{burst}'
                burst_trade_id = f'TRD_{i:06d}_BURST_{burst}'
                burst_time += timedelta(seconds=random.randint(1, 10))
                
                orders.append({
                    'order_id': burst_order_id,
                    'client_id': client_id,
                    'trader_id': f'TRADER_{random.randint(1,10):02d}',
                    'symbol': symbol,
                    'side': random.choice(['BUY', 'SELL']),
                    'quantity': random.randint(100, 500),
                    'price': price + random.uniform(-2, 2),
                    'timestamp': burst_time,
                    'order_type': 'MARKET'
                })
                
                trades.append({
                    'trade_id': burst_trade_id,
                    'order_id': burst_order_id,
                    'client_id': client_id,
                    'symbol': symbol,
                    'side': random.choice(['BUY', 'SELL']),
                    'quantity': random.randint(100, 500),
                    'price': price + random.uniform(-2, 2),
                    'timestamp': burst_time + timedelta(seconds=1)
                })
    
    # Save data
    orders_df = pd.DataFrame(orders)
    trades_df = pd.DataFrame(trades)
    
    orders_df.to_csv('data/sample_orders.csv', index=False)
    trades_df.to_csv('data/sample_trades.csv', index=False)
    
    print(f"Generated sample data:")
    print(f"- {len(clients_df)} clients saved to data/sample_clients.csv")
    print(f"- {len(orders_df)} orders saved to data/sample_orders.csv")
    print(f"- {len(trades_df)} trades saved to data/sample_trades.csv")
    print(f"\nSuspicious patterns included:")
    print(f"- Self-trade patterns: ~{len(orders_df)//50} instances")
    print(f"- High-frequency bursts: ~{len(orders_df)//100} instances")

if __name__ == "__main__":
    generate_sample_data()
