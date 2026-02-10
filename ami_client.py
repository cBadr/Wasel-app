import socket
import time

class SimpleAMI:
    """
    فئة بسيطة للتعامل مع AMI (Asterisk Manager Interface)
    """
    def __init__(self, host, port, user, secret):
        self.host = host
        self.port = port
        self.user = user
        self.secret = secret
        self.sock = None
        self.connected = False

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            login_cmd = f"Action: Login\r\nUsername: {self.user}\r\nSecret: {self.secret}\r\n\r\n"
            self.sock.send(login_cmd.encode('utf-8'))
            response = self.read_response()
            if "Success" in response:
                self.connected = True
                return True
            return False
        except:
            self.connected = False
            return False

    def read_response(self):
        buffer = ""
        try:
            while True:
                chunk = self.sock.recv(4096).decode('utf-8')
                buffer += chunk
                if "\r\n\r\n" in buffer:
                    break
            return buffer
        except:
            return ""

    def send_command(self, cmd):
        if not self.connected:
            if not self.connect():
                return None
        try:
            full_cmd = f"{cmd}\r\n\r\n"
            self.sock.send(full_cmd.encode('utf-8'))
            return self.read_response()
        except:
            self.connected = False
            return None

    def get_dongle_statuses(self):
        cmd = "Action: Command\r\nCommand: dongle show devices"
        response = self.send_command(cmd)
        dongles = []
        if response:
            lines = response.split('\n')
            for line in lines:
                line_clean = line.strip()
                if not line_clean or "State" in line_clean or "--END COMMAND--" in line_clean or "Response:" in line_clean:
                    continue
                if line_clean.startswith("Output:"):
                    line_clean = line_clean.replace("Output:", "").strip()
                
                parts = line_clean.split()
                if len(parts) >= 3:
                    dongle_id = parts[0]
                    # البحث عن الحالة
                    status = "Unknown"
                    if "Free" in parts: status = "Free"
                    elif "Busy" in parts: status = "Busy"
                    elif "Connected" in parts: status = "Connected"
                    
                    dongles.append({'id': dongle_id, 'status': status})
        return dongles

    def get_queue_status(self):
        cmd = "Action: QueueSummary"
        response = self.send_command(cmd)
        queues = []
        if response:
            lines = response.split('\n')
            for line in lines:
                if line.startswith("Queue:"):
                    parts = line.split()
                    # Example: Queue: 800  LoggedIn: 0  Callers: 0  HoldTime: 0  TalkTime: 0  LongestHoldTime: 0
                    queue_data = {}
                    for i in range(0, len(parts), 2):
                        if i+1 < len(parts):
                            key = parts[i].replace(':', '')
                            value = parts[i+1]
                            queue_data[key] = value
                    queues.append(queue_data)
        return queues

    def get_trunk_status(self):
        # Trying SIP peers first (common in Issabel)
        cmd = "Action: Command\r\nCommand: sip show peers"
        response = self.send_command(cmd)
        trunks = []
        if response:
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if not line or "Name/username" in line or "Response:" in line or "--END COMMAND--" in line:
                    continue
                if line.startswith("Output:"):
                    line = line.replace("Output:", "").strip()
                
                # Check for trunk lines (usually contain IP/Port and Status)
                # Format: Name/username Host Dyn Forcerport Comedia ACL Port Status Description
                # Simple check: if it has 'OK' or 'UNREACHABLE' or 'Monitored'
                parts = line.split()
                if len(parts) > 2 and ('OK' in line or 'UNREACHABLE' in line or 'UNKNOWN' in line):
                    name = parts[0].split('/')[0]
                    status = "Unknown"
                    if "OK" in line:
                        status = "Online"
                    elif "UNREACHABLE" in line or "UNKNOWN" in line:
                        status = "Offline"
                    
                    # Extract latency if available (OK (5 ms))
                    latency = ""
                    if "(" in line and "ms)" in line:
                        latency = line.split("(")[-1].replace(")", "")
                    
                    trunks.append({'name': name, 'status': status, 'latency': latency})
        return trunks

    def spy_channel(self, spy_extension, target_channel, option='q'):
        """
        Initiate a ChanSpy call.
        spy_extension: The extension that will listen (e.g., SIP/100 or 100)
        target_channel: The channel to spy on (e.g., SIP/trunk-0001)
        option: ChanSpy option (q=quiet, w=whisper, B=barge)
        """
        # Ensure extension format
        if not '/' in spy_extension:
             # Assume SIP if not specified, or Local
             # Safer to use Local channel to ring the phone
             channel = f"Local/{spy_extension}@from-internal"
        else:
             channel = spy_extension

        cmd = f"""Action: Originate
Channel: {channel}
Application: ChanSpy
Data: {target_channel},{option}
Async: true
CallerID: "Monitor: {target_channel}"
"""
        return self.send_command(cmd)

    def get_free_dongles(self):
        """
        Wrapper for get_dongle_statuses to return only free dongle IDs
        """
        statuses = self.get_dongle_statuses()
        return [d['id'] for d in statuses if d['status'] == 'Free']

    def originate_call(self, channel, exten, context, priority, caller_id, timeout=30000):
        """
        بدء مكالمة
        """
        action = (
            f"Action: Originate\r\n"
            f"Channel: {channel}\r\n"
            f"Context: {context}\r\n"
            f"Exten: {exten}\r\n"
            f"Priority: {priority}\r\n"
            f"CallerID: {caller_id}\r\n"
            f"Timeout: {timeout}\r\n"
            f"Async: true"
        )
        response = self.send_command(action)
        return response and "Success" in response

    def originate_call_with_response(self, channel, exten, context, priority, caller_id, timeout=30000):
        """
        بدء مكالمة مع إرجاع الرد
        """
        action = (
            f"Action: Originate\r\n"
            f"Channel: {channel}\r\n"
            f"Context: {context}\r\n"
            f"Exten: {exten}\r\n"
            f"Priority: {priority}\r\n"
            f"CallerID: {caller_id}\r\n"
            f"Timeout: {timeout}\r\n"
            f"Async: true"
        )
        response = self.send_command(action)
        success = response and ("Success" in response or "queued" in response.lower())
        return success, response
