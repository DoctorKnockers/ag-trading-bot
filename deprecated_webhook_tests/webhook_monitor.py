"""
Discord Webhook Monitor
Receives and displays webhook calls from Discord
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json
import logging
import colorama
from colorama import Fore, Style, Back
import threading
import time

# Initialize colorama for colored output
colorama.init()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store recent webhook calls
webhook_calls = []
MAX_CALLS = 50  # Keep last 50 calls in memory

def format_webhook_data(data):
    """Format webhook data for display."""
    output = []
    
    # Header
    output.append(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    output.append(f"{Fore.GREEN}📨 NEW WEBHOOK RECEIVED{Style.RESET_ALL}")
    output.append(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    # Timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    output.append(f"{Fore.YELLOW}⏰ Time:{Style.RESET_ALL} {timestamp}")
    
    # Check if it's a Discord message
    if 'content' in data:
        output.append(f"\n{Fore.MAGENTA}📝 Message Content:{Style.RESET_ALL}")
        output.append(f"  {data.get('content', 'No content')}")
    
    # Author info
    if 'author' in data:
        author = data['author']
        output.append(f"\n{Fore.BLUE}👤 Author:{Style.RESET_ALL}")
        output.append(f"  Username: {author.get('username', 'Unknown')}")
        output.append(f"  ID: {author.get('id', 'Unknown')}")
    
    # Channel info
    if 'channel_id' in data:
        output.append(f"\n{Fore.GREEN}📍 Channel:{Style.RESET_ALL}")
        output.append(f"  Channel ID: {data['channel_id']}")
        if 'guild_id' in data:
            output.append(f"  Guild ID: {data['guild_id']}")
    
    # Embeds
    if 'embeds' in data and data['embeds']:
        output.append(f"\n{Fore.CYAN}📋 Embeds:{Style.RESET_ALL} {len(data['embeds'])} embed(s)")
        for i, embed in enumerate(data['embeds'], 1):
            output.append(f"  Embed {i}:")
            if 'title' in embed:
                output.append(f"    Title: {embed['title']}")
            if 'url' in embed:
                output.append(f"    URL: {embed['url']}")
            if 'description' in embed:
                desc = embed['description'][:100] + '...' if len(embed['description']) > 100 else embed['description']
                output.append(f"    Description: {desc}")
    
    # Components (buttons)
    if 'components' in data and data['components']:
        output.append(f"\n{Fore.YELLOW}🔘 Components:{Style.RESET_ALL}")
        for row in data['components']:
            if 'components' in row:
                for comp in row['components']:
                    if comp.get('type') == 2:  # Button
                        output.append(f"  Button: {comp.get('label', 'No label')}")
                        if 'url' in comp:
                            output.append(f"    URL: {comp['url']}")
    
    # Attachments
    if 'attachments' in data and data['attachments']:
        output.append(f"\n{Fore.RED}📎 Attachments:{Style.RESET_ALL} {len(data['attachments'])} file(s)")
        for att in data['attachments']:
            output.append(f"  - {att.get('filename', 'Unknown')} ({att.get('size', 0)} bytes)")
    
    # Message type
    if 'type' in data:
        msg_types = {
            0: "DEFAULT",
            1: "RECIPIENT_ADD",
            2: "RECIPIENT_REMOVE",
            3: "CALL",
            4: "CHANNEL_NAME_CHANGE",
            5: "CHANNEL_ICON_CHANGE",
            6: "CHANNEL_PINNED_MESSAGE",
            7: "GUILD_MEMBER_JOIN",
            19: "REPLY",
            20: "APPLICATION_COMMAND",
            21: "THREAD_STARTER_MESSAGE",
            23: "GUILD_INVITE_REMINDER"
        }
        msg_type = msg_types.get(data['type'], f"UNKNOWN ({data['type']})")
        output.append(f"\n{Fore.WHITE}📌 Message Type:{Style.RESET_ALL} {msg_type}")
    
    output.append(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    return '\n'.join(output)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Receive webhook from Discord."""
    try:
        # Get the JSON data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Store the call
        webhook_calls.append({
            'timestamp': datetime.now().isoformat(),
            'data': data
        })
        
        # Keep only last MAX_CALLS
        if len(webhook_calls) > MAX_CALLS:
            webhook_calls.pop(0)
        
        # Display formatted data
        print(format_webhook_data(data))
        
        # Log raw data to file for debugging
        with open('webhook_log.json', 'a') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f)
            f.write('\n')
        
        return jsonify({'status': 'received'}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'calls_received': len(webhook_calls),
        'uptime': time.time()
    }), 200

@app.route('/stats', methods=['GET'])
def stats():
    """Get statistics about received webhooks."""
    return jsonify({
        'total_calls': len(webhook_calls),
        'recent_calls': webhook_calls[-10:] if webhook_calls else []
    }), 200

def print_startup_message():
    """Print startup instructions."""
    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}🚀 Discord Webhook Monitor Started!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}📋 Setup Instructions:{Style.RESET_ALL}")
    print(f"1. The server is running on: {Fore.GREEN}http://localhost:8888{Style.RESET_ALL}")
    print(f"2. Open a new terminal and run: {Fore.YELLOW}ngrok http 8888{Style.RESET_ALL}")
    print(f"3. Copy the HTTPS URL from ngrok (e.g., https://abc123.ngrok.io)")
    print(f"4. Go to Discord → Alpha Gardeners → #launchpads channel")
    print(f"5. Right-click channel → Edit Channel → Integrations → Webhooks")
    print(f"6. Create webhook with URL: {Fore.GREEN}https://your-ngrok-url.ngrok.io/webhook{Style.RESET_ALL}")
    print(f"\n{Fore.MAGENTA}✨ Monitoring for incoming webhooks...{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")

if __name__ == '__main__':
    print_startup_message()
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=8888, debug=False)
