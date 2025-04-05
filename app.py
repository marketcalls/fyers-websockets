import os
import json
import time
import asyncio
import websockets
from flask import Flask, render_template
from flask_socketio import SocketIO
from dotenv import load_dotenv
import msg_pb2

# Load environment variables
load_dotenv()

# Configuration
FYERS_APP_ID = os.getenv('FYERS_APP_ID').strip("'")
FYERS_ACCESS_TOKEN = os.getenv('FYERS_ACCESS_TOKEN').strip("'")
WEBSOCKET_URL = "wss://rtsocket-api.fyers.in/versova"

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

def process_market_depth(message_bytes):
    """Process market depth protobuf message"""
    try:
        socket_message = msg_pb2.SocketMessage()
        socket_message.ParseFromString(message_bytes)
        
        if socket_message.error:
            print(f"Error in socket message: {socket_message.msg}")
            return None
            
        market_data = {}
        for symbol, feed in socket_message.feeds.items():
            depth_data = {
                'symbol': symbol,
                'timestamp': feed.feed_time.value,
                'total_bid_qty': feed.depth.tbq.value,
                'total_sell_qty': feed.depth.tsq.value,
                'bids': [],
                'asks': []
            }
            
            # Process bids with price divided by 100
            for bid in feed.depth.bids:
                depth_data['bids'].append({
                    'price': bid.price.value / 100.0,
                    'quantity': bid.qty.value,
                    'orders': bid.nord.value,
                    'level': bid.num.value
                })
            
            # Process asks with price divided by 100
            for ask in feed.depth.asks:
                depth_data['asks'].append({
                    'price': ask.price.value / 100.0,
                    'quantity': ask.qty.value,
                    'orders': ask.nord.value,
                    'level': ask.num.value
                })
            
            # Sort bids and asks by level
            depth_data['bids'].sort(key=lambda x: x['level'])
            depth_data['asks'].sort(key=lambda x: x['level'])
            
            # Debug print depth levels
            print(f"\n=== Depth Levels for {symbol} ===")
            print(f"Number of bid levels: {len(depth_data['bids'])}")
            print(f"Number of ask levels: {len(depth_data['asks'])}")
            print(f"Bid levels: {[b['level'] for b in depth_data['bids']]}")
            print(f"Ask levels: {[a['level'] for a in depth_data['asks']]}")
            
            market_data[symbol] = depth_data
            print(f"Processed {symbol} data: Snapshot={socket_message.snapshot}")
        
        return market_data
    except Exception as e:
        print(f"Error processing market depth: {e}")
        return None

async def subscribe_symbols():
    """Subscribe to market depth data for symbols"""
    try:
        # Initial subscription message - only BANKNIFTY
        subscribe_msg = {
            "type": 1,
            "data": {
                "subs": 1,
                "symbols": [os.getenv('SYMBOL')],
                "mode": "depth",
                "channel": "1"
            }
        }
        
        print(f"\n=== Sending Subscribe Message ===")
        print(f"Message: {json.dumps(subscribe_msg, indent=2)}")
        
        if websocket:
            await websocket.send(json.dumps(subscribe_msg))
            print("Subscribe message sent successfully")
            
            # Resume channel message
            resume_msg = {
                "type": 2,
                "data": {
                    "resumeChannels": ["1"],
                    "pauseChannels": []
                }
            }
            
            print(f"\n=== Sending Channel Resume Message ===")
            print(f"Message: {json.dumps(resume_msg, indent=2)}")
            
            await websocket.send(json.dumps(resume_msg))
            print("Channel resume message sent successfully")
            
    except Exception as e:
        print(f"Error in subscribe_symbols: {e}")

websocket = None
last_ping_time = 0

async def websocket_client():
    global websocket, last_ping_time
    
    while True:
        try:
            print("\n=== Attempting WebSocket Connection ===")
            auth_header = f"{FYERS_APP_ID}:{FYERS_ACCESS_TOKEN}"
            
            print(f"WebSocket URL: {WEBSOCKET_URL}")
            print(f"App ID: {FYERS_APP_ID}")
            print(f"Auth Header Format: {FYERS_APP_ID}:<access_token>")
            print(f"Full Auth Header Length: {len(auth_header)}")
            
            async with websockets.connect(
                WEBSOCKET_URL,
                extra_headers={
                    "Authorization": auth_header
                }
            ) as ws:
                websocket = ws
                print("WebSocket connection established!")
                
                # Subscribe to symbols
                await subscribe_symbols()
                last_ping_time = time.time()
                
                while True:
                    try:
                        # Send ping every 30 seconds
                        current_time = time.time()
                        if current_time - last_ping_time >= 30:
                            await ws.send("ping")
                            last_ping_time = current_time
                            print("Ping sent")
                        
                        message = await ws.recv()
                        if isinstance(message, bytes):
                            market_data = process_market_depth(message)
                            if market_data:
                                socketio.emit('market_depth', market_data)
                        else:
                            print(f"Received text message: {message}")
                            
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed")
                        break
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        
        except websockets.exceptions.WebSocketException as e:
            print("\n=== Connection Failed ===")
            print(f"WebSocket Error: {str(e)}")
            print(f"Please check your Fyers API credentials")
            
        except Exception as e:
            print(f"\n=== Unexpected Error ===")
            print(f"Error: {str(e)}")
            
        print("\nRetrying connection in 5 seconds...")
        await asyncio.sleep(5)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print('Client connected')

def run_websocket():
    asyncio.run(websocket_client())

if __name__ == '__main__':
    # Start WebSocket client in a separate thread
    import threading
    ws_thread = threading.Thread(target=run_websocket)
    ws_thread.daemon = True
    ws_thread.start()
    
    # Run Flask application
    socketio.run(app, debug=True, port=5001, allow_unsafe_werkzeug=True)
