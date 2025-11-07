import os
import json
import time
import asyncio
import websockets
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import msg_pb2
from database import init_db, authenticate_user, get_auth_token, upsert_auth, find_user_by_username, get_auth_data, revoke_all_tokens, is_token_valid_for_today
from auth_utils import authenticate_broker, handle_auth_success, mask_api_credential

# Load environment variables
load_dotenv()

# Configuration
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://rtsocket-api.fyers.in/versova').strip("'")
SYMBOL = os.getenv('SYMBOL', 'NSE:NIFTY25JULFUT').strip("'")
LOT_SIZE = int(os.getenv('LOT_SIZE', '50'))

# Broker Configuration
BROKER_API_KEY = os.getenv('BROKER_API_KEY', '')
BROKER_API_SECRET = os.getenv('BROKER_API_SECRET', '')
REDIRECT_URL = os.getenv('REDIRECT_URL', 'http://localhost:5000/fyers/callback')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
init_db()

# Global WebSocket control flags (SEBI compliance)
websocket_enabled = False
websocket_task = None

# Global order book storage for maintaining full depth
order_books = {}

# Initialize scheduler for SEBI compliance (midnight token revocation)
scheduler = BackgroundScheduler(daemon=True)

def midnight_token_cleanup():
    """Revoke all tokens at 3:00 AM for SEBI compliance"""
    global websocket_enabled
    print(f"\n{'='*60}")
    print(f"[SEBI COMPLIANCE] Running midnight token cleanup at {datetime.now()}")
    print(f"{'='*60}")

    # Revoke all tokens
    count = revoke_all_tokens()

    # Stop WebSocket connections
    websocket_enabled = False

    print(f"[SEBI COMPLIANCE] Midnight cleanup complete:")
    print(f"  - Revoked {count} token(s)")
    print(f"  - WebSocket disabled")
    print(f"  - Users must re-authenticate")
    print(f"{'='*60}\n")

# Schedule midnight cleanup at 3:00 AM every day
scheduler.add_job(
    func=midnight_token_cleanup,
    trigger=CronTrigger(hour=3, minute=0),
    id='midnight_token_cleanup',
    name='SEBI Compliance - Midnight Token Cleanup',
    replace_existing=True
)

# Start the scheduler
scheduler.start()
print(f"[SCHEDULER] Started APScheduler for SEBI compliance")
print(f"[SCHEDULER] Midnight token cleanup scheduled for 3:00 AM daily")

def update_order_book(ticker, bids, asks, tbq, tsq, timestamp, is_snapshot):
    """Enhanced order book update with guaranteed 50-level depth maintenance"""
    global order_books
    
    if ticker not in order_books:
        # Initialize empty order book with 50 levels
        order_books[ticker] = {
            'bids': {i: {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i} for i in range(50)},
            'asks': {i: {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i} for i in range(50)},
            'tbq': 0,
            'tsq': 0,
            'timestamp': 0,
            'initialized': False
        }
    
    # Update total quantities and timestamp
    order_books[ticker]['tbq'] = tbq
    order_books[ticker]['tsq'] = tsq
    order_books[ticker]['timestamp'] = timestamp
    
    # Check if this is truly the first update
    first_update = not order_books[ticker].get('initialized', False)
    
    if is_snapshot or first_update:
        if first_update:
            print(f"[SNAPSHOT] FIRST UPDATE: Initializing order book for {ticker}")
            # Only reset on very first update
            for i in range(50):
                order_books[ticker]['bids'][i] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i}
                order_books[ticker]['asks'][i] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': i}
        else:
            print(f"[SNAPSHOT] SNAPSHOT: Updating order book for {ticker}")
    else:
        print(f"[INCREMENTAL] INCREMENTAL: Updating {len(bids)} bid levels and {len(asks)} ask levels for {ticker}")
    
    # Process bid updates
    for bid in bids:
        level = bid['level']
        if 0 <= level < 50:
            old_data = order_books[ticker]['bids'][level]
            
            if bid['price'] == 0.0 and bid['qty'] > 0:
                if old_data['price'] > 0:
                    order_books[ticker]['bids'][level] = {
                        'price': old_data['price'], 
                        'qty': bid['qty'],
                        'orders': bid['orders'], 
                        'level': level
                    }
                    # Only log invalid data occasionally to reduce noise
                    if level % 10 == 0:  # Log every 10th level only
                        print(f"   [BID] Level {level}: Invalid data corrected (price preserved)")
                # Skip invalid updates without valid old price
            elif bid['qty'] == 0:
                if bid['price'] == 0.0 and old_data['price'] > 0:
                    order_books[ticker]['bids'][level] = {
                        'price': old_data['price'], 
                        'qty': 0, 
                        'orders': bid['orders'], 
                        'level': level
                    }
                    print(f"   [BID] BID Level {level}: {old_data['price']:.2f} qty:0 orders:{bid['orders']} (preserving level)")
                elif bid['price'] > 0:
                    order_books[ticker]['bids'][level] = bid
                    print(f"   [BID] BID Level {level}: {bid['price']:.2f} qty:0 orders:{bid['orders']} (was {old_data['price']:.2f} qty:{old_data['qty']:,})")
                else:
                    if old_data['price'] == 0.0:
                        order_books[ticker]['bids'][level] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': level}
                    else:
                        order_books[ticker]['bids'][level] = {
                            'price': old_data['price'], 
                            'qty': 0, 
                            'orders': bid['orders'], 
                            'level': level
                        }
                        print(f"   [BID] BID Level {level}: {old_data['price']:.2f} qty:0 orders:{bid['orders']} (preserving structure)")
            else:
                order_books[ticker]['bids'][level] = bid
                if old_data['price'] != bid['price'] or old_data['qty'] != bid['qty']:
                    print(f"   [BID] BID Level {level}: {bid['price']:.2f} qty:{bid['qty']:,} orders:{bid['orders']} (was {old_data['price']:.2f} qty:{old_data['qty']:,})")
    
    # Process ask updates
    for ask in asks:
        level = ask['level']
        if 0 <= level < 50:
            old_data = order_books[ticker]['asks'][level]
            
            if ask['price'] == 0.0 and ask['qty'] > 0:
                if old_data['price'] > 0:
                    order_books[ticker]['asks'][level] = {
                        'price': old_data['price'], 
                        'qty': ask['qty'],
                        'orders': ask['orders'], 
                        'level': level
                    }
                    # Only log invalid data occasionally to reduce noise
                    if level % 10 == 0:  # Log every 10th level only
                        print(f"   [ASK] Level {level}: Invalid data corrected (price preserved)")
                # Skip invalid updates without valid old price
            elif ask['qty'] == 0:
                if ask['price'] == 0.0 and old_data['price'] > 0:
                    order_books[ticker]['asks'][level] = {
                        'price': old_data['price'], 
                        'qty': 0, 
                        'orders': ask['orders'], 
                        'level': level
                    }
                    print(f"   [ASK] ASK Level {level}: {old_data['price']:.2f} qty:0 orders:{ask['orders']} (preserving level)")
                elif ask['price'] > 0:
                    order_books[ticker]['asks'][level] = ask
                    print(f"   [ASK] ASK Level {level}: {ask['price']:.2f} qty:0 orders:{ask['orders']} (was {old_data['price']:.2f} qty:{old_data['qty']:,})")
                else:
                    if old_data['price'] == 0.0:
                        order_books[ticker]['asks'][level] = {'price': 0.0, 'qty': 0, 'orders': 0, 'level': level}
                    else:
                        order_books[ticker]['asks'][level] = {
                            'price': old_data['price'], 
                            'qty': 0, 
                            'orders': ask['orders'], 
                            'level': level
                        }
                        print(f"   [ASK] ASK Level {level}: {old_data['price']:.2f} qty:0 orders:{ask['orders']} (preserving structure)")
            else:
                order_books[ticker]['asks'][level] = ask
                if old_data['price'] != ask['price'] or old_data['qty'] != ask['qty']:
                    print(f"   [ASK] ASK Level {level}: {ask['price']:.2f} qty:{ask['qty']:,} orders:{ask['orders']} (was {old_data['price']:.2f} qty:{old_data['qty']:,})")
    
    # Mark as initialized after processing updates
    order_books[ticker]['initialized'] = True
    
    # Post-update validation
    active_bids = len([b for b in order_books[ticker]['bids'].values() if b['price'] > 0])
    active_asks = len([a for a in order_books[ticker]['asks'].values() if a['price'] > 0])
    
    print(f"   [STATUS] Update complete: {active_bids} active bid levels, {active_asks} active ask levels")

def get_full_order_book(ticker):
    """Get the complete 50-level order book for display with proper depth reconstruction"""
    if ticker not in order_books:
        return None
    
    book = order_books[ticker]
    
    # Get all bid levels with valid prices, sorted by price (descending for bids)
    raw_bids = []
    for i in range(50):
        bid = book['bids'][i]
        if bid['price'] > 0:
            raw_bids.append({
                'price': bid['price'],
                'qty': bid['qty'], 
                'orders': bid['orders'],
                'level': len(raw_bids)
            })
    
    # Sort bids by price (highest first) and reassign levels
    raw_bids.sort(key=lambda x: x['price'], reverse=True)
    active_bids = []
    for i, bid in enumerate(raw_bids[:50]):
        active_bids.append({
            'price': bid['price'],
            'qty': bid['qty'],
            'orders': bid['orders'],
            'level': i
        })
    
    # Get all ask levels with valid prices, sorted by price (ascending for asks)
    raw_asks = []
    for i in range(50):
        ask = book['asks'][i]
        if ask['price'] > 0:
            raw_asks.append({
                'price': ask['price'],
                'qty': ask['qty'],
                'orders': ask['orders'],
                'level': len(raw_asks)
            })
    
    # Sort asks by price (lowest first) and reassign levels
    raw_asks.sort(key=lambda x: x['price'])
    active_asks = []
    for i, ask in enumerate(raw_asks[:50]):
        active_asks.append({
            'price': ask['price'],
            'qty': ask['qty'],
            'orders': ask['orders'],
            'level': i
        })
    
    return {
        'ticker': ticker,
        'tbq': book['tbq'],
        'tsq': book['tsq'],
        'timestamp': book['timestamp'],
        'bids': active_bids,
        'asks': active_asks,
        'bidprice': [bid['price'] for bid in active_bids],
        'askprice': [ask['price'] for ask in active_asks],
        'bidqty': [bid['qty'] for bid in active_bids],
        'askqty': [ask['qty'] for ask in active_asks],
        'bidordn': [bid['orders'] for bid in active_bids],
        'askordn': [ask['orders'] for ask in active_asks]
    }

def calculate_order_book_imbalance(bids, asks, depth):
    """Calculate order book imbalance at specified depth level"""
    try:
        # Get quantities up to specified depth
        bid_qty = sum(bid['qty'] for bid in bids[:depth])
        ask_qty = sum(ask['qty'] for ask in asks[:depth])
        
        # Calculate imbalance ratio
        total_qty = bid_qty + ask_qty
        if total_qty > 0:
            imbalance = (bid_qty - ask_qty) / total_qty
            imbalance_pct = imbalance * 100
        else:
            imbalance = 0
            imbalance_pct = 0
        
        return {
            'bid_qty': bid_qty,
            'ask_qty': ask_qty,
            'imbalance': imbalance,
            'imbalance_pct': imbalance_pct,
            'interpretation': interpret_imbalance(imbalance_pct)
        }
    except Exception as e:
        print(f"Error calculating imbalance: {e}")
        return {
            'bid_qty': 0,
            'ask_qty': 0,
            'imbalance': 0,
            'imbalance_pct': 0,
            'interpretation': 'Unknown'
        }

def interpret_imbalance(imbalance_pct):
    """Interpret the imbalance percentage"""
    if imbalance_pct > 30:
        return "Strong Buying Pressure"
    elif imbalance_pct > 15:
        return "Moderate Buying Pressure"
    elif imbalance_pct > 5:
        return "Slight Buying Pressure"
    elif imbalance_pct < -30:
        return "Strong Selling Pressure"
    elif imbalance_pct < -15:
        return "Moderate Selling Pressure"
    elif imbalance_pct < -5:
        return "Slight Selling Pressure"
    else:
        return "Balanced"

def process_market_depth(message_bytes):
    """Process market depth protobuf message with proper order book management"""
    try:
        socket_message = msg_pb2.SocketMessage()
        socket_message.ParseFromString(message_bytes)
        
        if socket_message.error:
            print(f"Error in socket message: {socket_message.msg}")
            return None
            
        market_data = {}
        for ticker, feed in socket_message.feeds.items():
            # Extract raw update data
            timestamp = feed.feed_time.value if feed.feed_time else None
            tbq = feed.depth.tbq.value if feed.depth.tbq else 0
            tsq = feed.depth.tsq.value if feed.depth.tsq else 0
            is_snapshot = socket_message.snapshot
            
            # Process bids from update
            update_bids = []
            for bid in feed.depth.bids:
                bid_data = {
                    'price': bid.price.value / 100.0,
                    'qty': bid.qty.value,
                    'orders': bid.nord.value,
                    'level': bid.num.value
                }
                update_bids.append(bid_data)
            
            # Process asks from update
            update_asks = []
            for ask in feed.depth.asks:
                ask_data = {
                    'price': ask.price.value / 100.0,
                    'qty': ask.qty.value,
                    'orders': ask.nord.value,
                    'level': ask.num.value
                }
                update_asks.append(ask_data)
            
            # Update the order book
            update_order_book(ticker, update_bids, update_asks, tbq, tsq, timestamp, is_snapshot)
            
            # Get the complete order book for display
            full_book = get_full_order_book(ticker)
            if full_book:
                # Transform data structure to match frontend expectations
                frontend_data = {
                    'ticker': full_book['ticker'],
                    'timestamp': full_book['timestamp'] * 1000,
                    'total_bid_qty': full_book['tbq'],
                    'total_sell_qty': full_book['tsq'],
                    'bids': [
                        {
                            'level': bid['level'],
                            'price': bid['price'],
                            'quantity': bid['qty'],
                            'orders': bid['orders']
                        }
                        for bid in full_book['bids']
                    ],
                    'asks': [
                        {
                            'level': ask['level'],
                            'price': ask['price'],
                            'quantity': ask['qty'],
                            'orders': ask['orders']
                        }
                        for ask in full_book['asks']
                    ],
                    'bidprice': full_book['bidprice'],
                    'askprice': full_book['askprice'],
                    'bidqty': full_book['bidqty'],
                    'askqty': full_book['askqty'],
                    'bidordn': full_book['bidordn'],
                    'askordn': full_book['askordn'],
                    # Calculate imbalances at different depths
                    'imbalance_10': calculate_order_book_imbalance(full_book['bids'], full_book['asks'], 10),
                    'imbalance_20': calculate_order_book_imbalance(full_book['bids'], full_book['asks'], 20),
                    'imbalance_50': calculate_order_book_imbalance(full_book['bids'], full_book['asks'], 50)
                }
                
                market_data[ticker] = frontend_data
        
        return market_data if len(market_data) > 0 else None
    except Exception as e:
        print(f"Error processing market depth: {e}")
        return None

async def subscribe_symbols():
    """Subscribe to market depth data for symbols"""
    try:
        subscribe_msg = {
            "type": 1,
            "data": {
                "subs": 1,
                "symbols": [SYMBOL],
                "mode": "depth",
                "channel": "1"
            }
        }
        
        print(f"\n=== Sending Subscribe Message ===")
        print(f"Message: {json.dumps(subscribe_msg, indent=2)}")
        
        if websocket:
            await websocket.send(json.dumps(subscribe_msg))
            print("Subscribe message sent successfully")
            
            resume_msg = {
                "type": 2,
                "data": {
                    "resumeChannels": ["1"],
                    "pauseChannels": []
                }
            }
            
            await websocket.send(json.dumps(resume_msg))
            print("Channel resume message sent successfully")
            
    except Exception as e:
        print(f"Error in subscribe_symbols: {e}")

websocket = None
last_ping_time = 0

async def websocket_client():
    """
    WebSocket client with SEBI compliance:
    - Only connects when user is logged in (session active)
    - Only connects when token is valid for today
    - Stops when websocket_enabled is False
    """
    global websocket, last_ping_time, websocket_enabled

    print("[WEBSOCKET] WebSocket client task started (waiting for login)")

    while True:
        try:
            # CRITICAL: Check if WebSocket is enabled (SEBI compliance)
            if not websocket_enabled:
                # Wait for user to login
                await asyncio.sleep(5)
                continue

            # Get auth data from database
            from database import db_session, Auth
            active_auth = db_session.query(Auth).filter_by(is_revoked=False, broker='fyers').first()

            if not active_auth:
                print("[WEBSOCKET] No active authentication found, waiting...")
                websocket_enabled = False
                await asyncio.sleep(10)
                continue

            # SEBI COMPLIANCE: Check if token is valid for today
            if not is_token_valid_for_today(active_auth.name):
                print(f"[WEBSOCKET] Token for {active_auth.name} is not valid for today")
                websocket_enabled = False
                await asyncio.sleep(10)
                continue

            # Get all auth data including API key and auth token
            auth_data = get_auth_data(active_auth.name)

            if not auth_data or not auth_data['auth_token'] or not auth_data['api_key']:
                print("[WEBSOCKET] No valid auth data available, waiting...")
                websocket_enabled = False
                await asyncio.sleep(10)
                continue

            print("\n=== Attempting WebSocket Connection ===")
            auth_header = f"{auth_data['api_key']}:{auth_data['auth_token']}"

            print(f"WebSocket URL: {WEBSOCKET_URL}")
            print(f"App ID: {auth_data['api_key']}")
            print(f"User: {active_auth.name}")
            print(f"Broker: {auth_data['broker']}")
            print(f"Login Date: {active_auth.login_date}")

            async with websockets.connect(
                WEBSOCKET_URL,
                extra_headers={
                    "Authorization": auth_header
                }
            ) as ws:
                websocket = ws
                print("[WEBSOCKET] Connection established!")

                # Subscribe to symbols
                await subscribe_symbols()
                last_ping_time = time.time()

                while True:
                    # Check if WebSocket should be disabled (logout or midnight cleanup)
                    if not websocket_enabled:
                        print("[WEBSOCKET] WebSocket disabled, closing connection...")
                        break

                    try:
                        # Send ping every 30 seconds
                        current_time = time.time()
                        if current_time - last_ping_time >= 30:
                            await ws.send("ping")
                            last_ping_time = current_time
                            print("[WEBSOCKET] Ping sent")

                        # Receive message with timeout
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)

                        if isinstance(message, bytes):
                            market_data = process_market_depth(message)
                            if market_data:
                                print(f"[EMIT] Emitting market_depth data to frontend with {len(market_data)} symbols")
                                socketio.emit('market_depth', market_data)
                        else:
                            print(f"[WEBSOCKET] Received text message: {message}")

                    except asyncio.TimeoutError:
                        # Normal timeout, continue loop
                        continue
                    except websockets.ConnectionClosed:
                        print("[WEBSOCKET] Connection closed")
                        break
                    except Exception as e:
                        print(f"[WEBSOCKET] Error processing message: {e}")

        except Exception as e:
            print(f"\n[WEBSOCKET] Connection Error: {str(e)}")

        # Only retry if WebSocket is still enabled
        if websocket_enabled:
            print("[WEBSOCKET] Retrying connection in 5 seconds...")
            await asyncio.sleep(5)
        else:
            print("[WEBSOCKET] WebSocket disabled, waiting for login...")
            await asyncio.sleep(5)

# Authentication Routes
@app.route('/')
def index():
    """Main route - redirect directly to Fyers login if not authenticated, otherwise to dashboard"""
    if not session.get('logged_in'):
        return redirect(url_for('broker_login'))
    
    return redirect(url_for('dashboard'))

# Admin login route removed - using direct Fyers OAuth login

@app.route('/auth/broker', methods=['GET'])
def broker_login():
    """Broker authentication page - direct Fyers login"""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    # Set a default user session for the authentication flow
    if 'user' not in session:
        session['user'] = 'fyers_user'
    
    broker_name = 'fyers'
    if REDIRECT_URL:
        match = re.search(r'/([^/]+)/callback', REDIRECT_URL)
        if match:
            broker_name = match.group(1)
    
    return render_template('broker.html',
                         broker_api_key=BROKER_API_KEY,
                         broker_api_key_masked=mask_api_credential(BROKER_API_KEY),
                         broker_api_secret=BROKER_API_SECRET,
                         broker_api_secret_masked=mask_api_credential(BROKER_API_SECRET),
                         redirect_url=REDIRECT_URL,
                         broker_name=broker_name)

@app.route('/fyers/callback', methods=['GET'])
def fyers_callback():
    """Handle Fyers OAuth callback and enable WebSocket"""
    global websocket_enabled

    # Set default user if not in session
    if 'user' not in session:
        session['user'] = 'fyers_user'

    auth_code = request.args.get('auth_code') or request.args.get('code')
    error = request.args.get('error')

    if error:
        error_msg = f"OAuth error: {error}"
        print(error_msg)
        return redirect(url_for('broker_login') + f'?error={error_msg}')

    if not auth_code:
        error_msg = "No authorization code received"
        print(error_msg)
        return redirect(url_for('broker_login') + f'?error={error_msg}')

    print(f'Fyers broker callback - auth code: {auth_code}')

    auth_token, error_message = authenticate_broker(auth_code)

    if auth_token:
        username = session['user']
        success = handle_auth_success(auth_token, username, 'fyers')

        if success:
            session['logged_in'] = True
            session['broker'] = 'fyers'
            session['login_date'] = datetime.now().strftime('%Y-%m-%d')

            # CRITICAL: Enable WebSocket ONLY after successful login
            websocket_enabled = True

            print(f'[AUTH] Successfully authenticated user {username} with Fyers')
            print(f'[AUTH] WebSocket enabled for session')
            return redirect(url_for('dashboard'))
        else:
            error_msg = "Failed to store authentication token"
            print(error_msg)
            return redirect(url_for('broker_login') + f'?error={error_msg}')
    else:
        print(f"Fyers authentication failed: {error_message}")
        return redirect(url_for('broker_login') + f'?error={error_message}')

@app.route('/dashboard')
def dashboard():
    """Main dashboard with DOM display - with SEBI compliance check"""
    global websocket_enabled

    if not session.get('logged_in'):
        return redirect(url_for('broker_login'))

    # Set default user if not in session
    if 'user' not in session:
        session['user'] = 'fyers_user'

    username = session['user']

    # SEBI COMPLIANCE: Check if token is valid for today
    if not is_token_valid_for_today(username):
        print(f"[SEBI COMPLIANCE] Token for {username} is expired or invalid for today")
        session.clear()
        websocket_enabled = False
        return redirect(url_for('broker_login') + '?error=Session expired. Please login again (SEBI compliance)')

    # Check if login_date in session matches today
    today = datetime.now().strftime('%Y-%m-%d')
    session_login_date = session.get('login_date')

    if session_login_date != today:
        print(f"[SEBI COMPLIANCE] Session login date {session_login_date} does not match today {today}")
        session.clear()
        websocket_enabled = False
        return redirect(url_for('broker_login') + '?error=Session expired. Please login again (SEBI compliance)')

    auth_token = get_auth_token(username)

    if not auth_token:
        print(f"[AUTH] No auth token found for {username}")
        session.clear()
        websocket_enabled = False
        return redirect(url_for('broker_login'))

    return render_template('dashboard.html', symbol=SYMBOL, lot_size=LOT_SIZE)

@app.route('/auth/logout')
def logout():
    """Logout route - revoke token and disable WebSocket"""
    global websocket_enabled

    if session.get('logged_in'):
        username = session.get('user')
        if username:
            upsert_auth(username, "", "fyers", revoke=True)
            print(f'[AUTH] Auth token revoked for user: {username}')

    # CRITICAL: Disable WebSocket on logout
    websocket_enabled = False
    print(f'[AUTH] WebSocket disabled on logout')

    session.clear()
    return redirect(url_for('broker_login'))

@app.route('/api/config')
def get_config():
    """Get application configuration including symbol"""
    return {
        'symbol': SYMBOL,
        'app_name': 'Fyers Dom Analyzer'
    }

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    socketio.emit('test_message', {'message': 'Hello from backend!'})

def run_websocket():
    asyncio.run(websocket_client())

if __name__ == '__main__':
    import threading
    ws_thread = threading.Thread(target=run_websocket)
    ws_thread.daemon = True
    ws_thread.start()
    
    socketio.run(app, debug=True, port=5000)