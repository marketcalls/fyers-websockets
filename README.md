<img src="static/images/TBT.png" alt="TBT Logo" width="200"/>

# Fyers Market Depth Viewer

A real-time market depth viewer application that connects to Fyers WebSocket API to stream Tick-by-Tick (TBT) market depth data for BANKNIFTY futures. Built with Flask and Socket.IO for real-time updates, and DaisyUI for a modern UI.

## Features

- Real-time market depth data streaming via WebSocket
- Advanced DOM (Depth of Market) Analysis:
  - Support and Resistance Level Detection
  - Large Order Tracking and Alerts
  - Price Cluster Analysis
  - Order Flow Metrics
  - Market Sentiment Indicators
- Interactive Depth Distribution Visualization
- VWAP (Volume Weighted Average Price) Calculation
- Price Level Activity Monitoring
- Customizable DOM Display Options
- Real-time Market Statistics:
  - Bid-Ask Spread Analysis
  - Total Volume Analysis
  - Price Change Tracking
- Modern UI Components:
  - Heat Maps for Order Book Visualization
  - Animated Price Changes
  - Custom Tooltips
  - Responsive Design
  - Dark/Light Theme Toggle
- Auto-reconnect WebSocket functionality
- Efficient Data Processing using Protocol Buffers

## Prerequisites

- Python 3.8 or higher
- Fyers API credentials (App ID and Access Token)
- Active Fyers trading account
- Protocol Buffers compiler (protoc)

##  Fyers API Credentials (How To)

- Register a new App from URL: `https://myapi.fyers.in/` and activate the app

## Installation

1. Clone the repository:
```bash
git clone https://github.com/marketcalls/fyers-websockets.git
cd fyers-websockets
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

4. Update the `.env` file with your Fyers credentials:
```
FYERS_APP_ID=your_app_id
FYERS_ACCESS_TOKEN=your_access_token
```

5. The `generate_token.py` script helps you generate an access token for the Fyers API:

```
python generate_token.py
```

This script will:
1. Prompt you for your Fyers API credentials
2. Open a browser window for authentication
3. Generate an access token
4. Optionally update the `.env` file with the new token

## Understanding WebSockets

WebSockets provide a persistent, bi-directional communication channel between the client and server. In this application, we use WebSockets at two levels:

1. **Fyers WebSocket Connection (Backend)**:
   - The backend establishes a WebSocket connection to Fyers API
   - Uses Protocol Buffers for efficient data serialization
   - Handles automatic reconnection and ping/pong messages
   - Processes market depth data in real-time

2. **Flask-SocketIO (Frontend-Backend Communication)**:
   - Provides real-time updates to the browser
   - Handles multiple client connections
   - Ensures efficient data delivery to the UI
   - Manages connection state and reconnection

## Creating msg_pb2.py from Protocol Buffers

The `msg_pb2.py` file is generated from a Protocol Buffers definition file. Follow these steps to create it:

1. First, create a file named `msg.proto` with your message definitions:
```protobuf
syntax = "proto3";

message Value {
    int64 value = 1;
}

message Depth {
    message DepthLevel {
        Value price = 1;
        Value qty = 2;
        Value nord = 3;
        Value num = 4;
    }
    repeated DepthLevel bids = 1;
    repeated DepthLevel asks = 2;
    Value tbq = 3;  // Total Bid Quantity
    Value tsq = 4;  // Total Sell Quantity
}

message Feed {
    Value feed_time = 1;
    Depth depth = 2;
}

message SocketMessage {
    bool error = 1;
    string msg = 2;
    bool snapshot = 3;
    map<string, Feed> feeds = 4;
}
```

2. Install the Protocol Buffers compiler:
   - Windows: Download from [Protocol Buffers Releases](https://github.com/protocolbuffers/protobuf/releases)
   - Add protoc to your system PATH

3. Generate the Python code:
```bash
protoc --python_out=. msg.proto
```

This will create `msg_pb2.py` which contains the Python classes for serializing/deserializing market data.

## Data Processing Flow

1. **WebSocket Data Reception**:
   ```python
   message_bytes = await ws.recv()
   socket_message = msg_pb2.SocketMessage()
   socket_message.ParseFromString(message_bytes)
   ```

2. **Data Processing**:
   - Market depth data is deserialized using Protocol Buffers
   - Processed into a structured format
   - Enhanced with additional analytics

3. **Real-time Updates**:
   - Processed data is sent to connected clients
   - UI updates dynamically with new information
   - Analytics are recalculated in real-time

## Running the Application

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:5000
```

## WebSocket Connection Details

- WebSocket URL: `wss://rtsocket-api.fyers.in/versova`
- Protocol: Protobuf for efficient message encoding/decoding
- Subscription: BANKNIFTY futures market depth data
- Auto-ping enabled to maintain connection

## Data Display

The application shows:
- Total bid and ask quantities at the top
- Two tables showing bid and ask orders with:
  - Level number (1-50)
  - Price (formatted with 2 decimal places)
  - Quantity (formatted with Indian number system)
  - Number of orders at each level

## UI Features

- Responsive design using DaisyUI and Tailwind CSS
- Dark/Light theme toggle
- Scrollable tables with pinned headers
- Color-coded bid (green) and ask (red) orders
- Monospace font for better number readability

## Error Handling

- Automatic WebSocket reconnection on disconnection
- Error logging for WebSocket and data processing issues
- User-friendly error messages in the UI

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Fyers API Documentation](https://api-docs.fyers.in/)
- [DaisyUI](https://daisyui.com/)
- [Flask-SocketIO](https://flask-socketio.readthedocs.io/)

## Author

**marketcalls**
- GitHub: [@marketcalls](https://github.com/marketcalls)

## Support

If you found this project helpful, please consider giving it a ⭐!
