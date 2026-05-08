from flask import Flask, render_template, request, jsonify, send_file
import threading
import requests
import random
import string
import time
import os
import json
from datetime import datetime

app = Flask(__name__)

# গ্লোবাল ভেরিয়েবল
scraping_active = False
found_ips = set()
lock = threading.Lock()
current_progress = 0
target_unique_ips = 20
target_isps = ["T-Mobile USA", "Verizon Business", "AT&T"]
max_threads = 20
session_lifetime = 60
current_filename = "generated_proxies.txt"

def generate_lsid(length=9):
    return "".join(random.choices(string.digits, k=length))

def check_wireless_ip(proxy_config, stop_event):
    global found_ips, current_progress, scraping_active
    
    while not stop_event.is_set():
        if len(found_ips) >= target_unique_ips:
            break
            
        lsid = generate_lsid()
        try:
            proxy_host = proxy_config['host']
            proxy_port = proxy_config['port']
            proxy_user_base = proxy_config['username']
            proxy_pass = proxy_config['password']
            
            current_user = f"{proxy_user_base}-Lsid-{lsid}-Life-{session_lifetime}"
            proxy_url = f"socks5://{current_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
            proxies = {"http": proxy_url, "https": proxy_url}
            
            api_url = "http://ip-api.com/json?fields=status,query,isp,countryCode"
            response = requests.get(api_url, proxies=proxies, timeout=15).json()
            
            if response.get("status") == "success":
                current_isp = response.get("isp", "")
                country_code = response.get("countryCode", "")
                ip = response.get("query")
                
                is_strictly_targeted = any(
                    target.lower() in current_isp.lower() for target in target_isps
                )
                
                if country_code == "US" and is_strictly_targeted:
                    with lock:
                        if ip not in found_ips and len(found_ips) < target_unique_ips:
                            found_ips.add(ip)
                            current_progress = len(found_ips)
                            
                            full_proxy_str = f"{proxy_host}:{proxy_port}:{current_user}:{proxy_pass}"
                            with open(current_filename, "a") as f:
                                f.write(f"{full_proxy_str}\n")
        except Exception:
            continue

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    global scraping_active, found_ips, current_progress, target_unique_ips, target_isps, max_threads, session_lifetime, current_filename
    
    if scraping_active:
        return jsonify({'error': 'স্ক্র্যাপিং ইতিমধ্যে চলছে!'}), 400
    
    data = request.json
    proxy_config = {
        'host': data.get('host'),
        'port': data.get('port'),
        'username': data.get('username'),
        'password': data.get('password')
    }
    
    # সেটিংস আপডেট
    target_unique_ips = int(data.get('quantity', 20))
    target_isps = data.get('target_isps', ["T-Mobile USA", "Verizon Business", "AT&T"])
    max_threads = int(data.get('threads', 20))
    session_lifetime = int(data.get('stick_time', 60))
    
    # ফাইল রিসেট
    current_filename = f"generated_proxies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    open(current_filename, "w").close()
    
    found_ips.clear()
    current_progress = 0
    scraping_active = True
    
    stop_event = threading.Event()
    
    def run_scraping():
        global scraping_active
        threads = []
        for _ in range(max_threads):
            t = threading.Thread(target=check_wireless_ip, args=(proxy_config, stop_event))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # সমস্ত থ্রেড শেষ হওয়ার জন্য অপেক্ষা
        while len(found_ips) < target_unique_ips and scraping_active:
            time.sleep(1)
        
        scraping_active = False
        for t in threads:
            t.join(timeout=1)
    
    thread = threading.Thread(target=run_scraping)
    thread.start()
    
    return jsonify({'message': 'স্ক্র্যাপিং শুরু হয়েছে!', 'filename': current_filename})

@app.route('/get_progress')
def get_progress():
    return jsonify({
        'progress': current_progress,
        'total': target_unique_ips,
        'active': scraping_active,
        'filename': current_filename
    })

@app.route('/download')
def download():
    filename = request.args.get('filename', current_filename)
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    return jsonify({'error': 'ফাইল পাওয়া যায়নি!'}), 404

@app.route('/stop_scraping', methods=['POST'])
def stop_scraping():
    global scraping_active
    scraping_active = False
    return jsonify({'message': 'স্ক্র্যাপিং বন্ধ করা হয়েছে!'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)