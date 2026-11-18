from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from datetime import datetime
import sqlite3
import os
import csv
import io

app = FastAPI(title="Project 22 - AI Voice Cloud Classroom Access Gate")

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/access_logs.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id TEXT,
        student_name TEXT,
        roll_no TEXT,
        subnet TEXT,
        vpc_zone TEXT,
        direction TEXT,
        latency_ms INTEGER,
        status TEXT,
        timestamp TEXT
    )
""")
conn.commit()

AUTHORIZED_TAGS = {
    "RFID-101": {"name": "Aarav Sharma", "roll": "25CAI014", "subnet": "10.0.1.0/24", "zone": "CS-Cloud-Lab"},
    "RFID-102": {"name": "Priya Verma", "roll": "25CAI029", "subnet": "10.0.1.0/24", "zone": "CS-Cloud-Lab"},
    "RFID-103": {"name": "Rohan Das", "roll": "25CAI042", "subnet": "10.0.2.0/24", "zone": "Research-VPC"},
    "RFID-104": {"name": "Ananya Iyer", "roll": "25CAI051", "subnet": "10.0.2.0/24", "zone": "Research-VPC"}
}

active_inside = set()
lockdown_mode = False
event_counter = 0

latest_state = {
    "event_id": 0,
    "status": "IDLE",
    "direction": "NONE",
    "tag_id": "NONE",
    "student": "Awaiting RFID Tap...",
    "roll": "--",
    "subnet": "0.0.0.0/0",
    "zone": "STANDBY",
    "latency_ms": 0,
    "timestamp": "--",
    "lockdown": False,
    "voice_text": "System ready.",
    "gpio": {"r": 0, "g": 0, "b": 1}
}

@app.post("/scan")
def process_scan(tag_id: str = Form(...), mode: str = Form("AUTO")):
    global latest_state, event_counter
    event_counter += 1
    tag_id = tag_id.strip().upper()
    now = datetime.now().strftime("%H:%M:%S")
    latency = 14 + (len(tag_id) * 2)

    if lockdown_mode:
        student = AUTHORIZED_TAGS[tag_id]["name"] if tag_id in AUTHORIZED_TAGS else "Unknown Intruder"
        roll = AUTHORIZED_TAGS[tag_id]["roll"] if tag_id in AUTHORIZED_TAGS else "INTRUDER"
        subnet = "0.0.0.0/0"
        zone = "VPC-LOCKDOWN-DROP"
        direction = "BLOCKED"
        status = "DENIED"
        voice_text = "Entry denied. Emergency lockdown is active."
        gpio = {"r": 1, "g": 0, "b": 0}
    elif tag_id in AUTHORIZED_TAGS:
        info = AUTHORIZED_TAGS[tag_id]
        student = info["name"]
        roll = info["roll"]
        subnet = info["subnet"]
        zone = info["zone"]

        if mode == "OUT" or (mode == "AUTO" and tag_id in active_inside):
            active_inside.discard(tag_id)
            direction = "OUT"
            status = "CHECKED_OUT"
            voice_text = f"Out. Goodbye {student}."
            gpio = {"r": 0, "g": 0, "b": 1}
        else:
            active_inside.add(tag_id)
            direction = "IN"
            status = "ALLOWED"
            voice_text = f"Entry allowed. Welcome {student}."
            gpio = {"r": 0, "g": 1, "b": 0}
    else:
        student = "Unregistered Intruder"
        roll = "UNAUTHORIZED"
        subnet = "192.168.99.0/24"
        zone = "QUARANTINE-ACL"
        direction = "BLOCKED"
        status = "DENIED"
        voice_text = "Entry denied. Unauthorized tag detected."
        gpio = {"r": 1, "g": 0, "b": 0}

    cursor.execute(
        "INSERT INTO logs (tag_id, student_name, roll_no, subnet, vpc_zone, direction, latency_ms, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (tag_id, student, roll, subnet, zone, direction, latency, status, now)
    )
    conn.commit()

    latest_state = {
        "event_id": event_counter,
        "status": status,
        "direction": direction,
        "tag_id": tag_id,
        "student": student,
        "roll": roll,
        "subnet": subnet,
        "zone": zone,
        "latency_ms": latency,
        "timestamp": now,
        "lockdown": lockdown_mode,
        "voice_text": voice_text,
        "gpio": gpio
    }
    return JSONResponse(latest_state)

@app.post("/toggle-lockdown")
def toggle_lockdown():
    global lockdown_mode, latest_state, event_counter
    event_counter += 1
    lockdown_mode = not lockdown_mode
    if lockdown_mode:
        latest_state = {
            "event_id": event_counter,
            "status": "DENIED",
            "direction": "LOCK",
            "tag_id": "SYS-LOCK",
            "student": "EMERGENCY VPC LOCKDOWN",
            "roll": "ADMIN-OVERRIDE",
            "subnet": "ALL-SUBNETS",
            "zone": "LOCKDOWN-ACTIVE",
            "latency_ms": 5,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "lockdown": True,
            "voice_text": "Entry denied. Emergency lockdown activated.",
            "gpio": {"r": 1, "g": 0, "b": 0}
        }
    else:
        latest_state = {
            "event_id": event_counter,
            "status": "IDLE",
            "direction": "NONE",
            "tag_id": "NONE",
            "student": "Lockdown Lifted • Gate Ready",
            "roll": "--",
            "subnet": "0.0.0.0/0",
            "zone": "STANDBY",
            "latency_ms": 0,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "lockdown": False,
            "voice_text": "Lockdown lifted. Gate is ready.",
            "gpio": {"r": 0, "g": 0, "b": 1}
        }
    return JSONResponse({"lockdown": lockdown_mode, "latest": latest_state})

@app.post("/register")
def register_tag(tag_id: str = Form(...), name: str = Form(...), roll: str = Form(...), subnet: str = Form(...), zone: str = Form(...)):
    tag_id = tag_id.strip().upper()
    AUTHORIZED_TAGS[tag_id] = {
        "name": name.strip(),
        "roll": roll.strip().upper(),
        "subnet": subnet.strip(),
        "zone": zone.strip()
    }
    return JSONResponse({"message": f"Provisioned {tag_id}", "tags": AUTHORIZED_TAGS})

@app.post("/reset")
def reset_gate():
    global latest_state, lockdown_mode, event_counter
    event_counter += 1
    lockdown_mode = False
    active_inside.clear()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    latest_state = {
        "event_id": event_counter,
        "status": "IDLE",
        "direction": "NONE",
        "tag_id": "NONE",
        "student": "Awaiting RFID Tap...",
        "roll": "--",
        "subnet": "0.0.0.0/0",
        "zone": "STANDBY",
        "latency_ms": 0,
        "timestamp": "--",
        "lockdown": False,
        "voice_text": "System reset complete.",
        "gpio": {"r": 0, "g": 0, "b": 1}
    }
    return JSONResponse(latest_state)

@app.get("/api/status")
def get_esp32_status():
    return latest_state

@app.get("/export-csv")
def export_csv():
    cursor.execute("SELECT id, timestamp, tag_id, student_name, roll_no, direction, subnet, vpc_zone, latency_ms, status FROM logs ORDER BY id DESC")
    rows = cursor.fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Log_ID", "Timestamp", "RFID_Tag", "Student_Name", "Roll_No", "Direction", "Subnet_CIDR", "VPC_Zone", "Latency_ms", "Gate_Decision"])
    writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Project22_Access_Audit.csv"}
    )

@app.get("/api/dashboard-data")
def get_dashboard_data():
    cursor.execute("SELECT tag_id, student_name, roll_no, direction, subnet, vpc_zone, latency_ms, status, timestamp FROM logs ORDER BY id DESC LIMIT 12")
    rows = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM logs WHERE status='ALLOWED'")
    allowed_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE status='DENIED'")
    denied_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE status='CHECKED_OUT'")
    out_count = cursor.fetchone()[0]

    logs_list = [
        {
            "tag_id": r[0],
            "student": r[1],
            "roll": r[2],
            "direction": r[3],
            "subnet": r[4],
            "zone": r[5],
            "latency": r[6],
            "status": r[7],
            "time": r[8]
        } for r in rows
    ]

    return JSONResponse({
        "latest": latest_state,
        "allowed": allowed_count,
        "denied": denied_count,
        "checked_out": out_count,
        "inside_now": len(active_inside),
        "inside_tags": list(active_inside),
        "total": allowed_count + denied_count + out_count,
        "lockdown": lockdown_mode,
        "logs": logs_list
    })

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Project 22 | AI Voice Cloud Access Command Center</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #04070f;
                --panel: rgba(13, 20, 36, 0.85);
                --border: rgba(56, 189, 248, 0.18);
                --cyan: #38bdf8;
                --indigo: #818cf8;
                --green: #10b981;
                --red: #f43f5e;
                --amber: #f59e0b;
                --text: #f8fafc;
                --muted: #94a3b8;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0; padding: 18px; font-family: 'Inter', sans-serif; color: var(--text);
                background-color: var(--bg);
                background-image: 
                    radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.13) 0px, transparent 50%),
                    radial-gradient(at 100% 0%, rgba(129, 140, 248, 0.13) 0px, transparent 50%),
                    linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px);
                background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px;
                min-height: 100vh;
            }
            .wrap { max-width: 1420px; margin: auto; }

            .topbar {
                display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;
                background: var(--panel); border: 1px solid var(--border);
                backdrop-filter: blur(16px); border-radius: 16px; padding: 14px 22px; margin-bottom: 18px;
            }
            .title-group h1 {
                margin: 0; font-family: 'Space Grotesk', sans-serif; font-size: 21px;
                background: linear-gradient(90deg, #fff, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }
            .title-group p { margin: 3px 0 0 0; font-size: 12px; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
            
            .top-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
            .status-chip {
                padding: 6px 12px; border-radius: 999px; font-size: 11px; font-weight: 700;
                font-family: 'JetBrains Mono', monospace; display: flex; align-items: center; gap: 6px;
                background: rgba(16, 185, 129, 0.1); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3);
            }
            .blink { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 1.4s infinite; }
            @keyframes pulse { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(0.75); opacity: 0.4; } }

            .btn-top {
                padding: 8px 14px; border-radius: 10px; border: 1px solid var(--border);
                background: #131c31; color: var(--text); font-size: 12px; font-weight: 600;
                cursor: pointer; transition: 0.2s; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
            }
            .btn-top:hover { border-color: var(--cyan); background: #192540; }
            .btn-voice.on { border-color: rgba(56, 189, 248, 0.5); color: var(--cyan); background: rgba(56, 189, 248, 0.12); }
            .btn-lockdown { border-color: rgba(244, 63, 94, 0.4); color: #fda4af; }
            .btn-lockdown.active { background: var(--red); color: white; border-color: var(--red); box-shadow: 0 0 20px rgba(244, 63, 94, 0.5); }

            .main-grid { display: grid; grid-template-columns: 375px 1fr; gap: 18px; }
            .card {
                background: var(--panel); border: 1px solid var(--border);
                backdrop-filter: blur(14px); border-radius: 16px; padding: 18px;
            }
            .sec-label {
                font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px;
                color: var(--cyan); font-weight: 700; margin: 0 0 12px 0;
                display: flex; justify-content: space-between; align-items: center;
            }

            .hw-stage {
                background: linear-gradient(180deg, #070c18 0%, #0b1326 100%);
                border: 1px solid #1e293b; border-radius: 14px; padding: 15px; margin-bottom: 14px;
            }
            .esp-board {
                display: flex; align-items: center; justify-content: space-between;
                background: #111827; border: 1px solid #374151; border-radius: 10px; padding: 11px;
            }
            .esp-chip {
                background: #1f2937; border: 1px solid #4b5563; border-radius: 6px; padding: 8px 10px;
                font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #e5e7eb;
            }
            .gpio-pins { display: flex; flex-direction: column; gap: 5px; font-family: 'JetBrains Mono', monospace; font-size: 10px; }
            .pin-row { display: flex; align-items: center; gap: 6px; }
            .wire { width: 24px; height: 3px; border-radius: 2px; background: #334155; transition: 0.3s; }
            .resistor { width: 15px; height: 6px; background: #d97706; border-radius: 2px; border: 1px solid #fbbf24; }
            
            .rgb-bulb-wrap { text-align: center; }
            .rgb-bulb {
                width: 62px; height: 62px; border-radius: 50%; margin: 0 auto 5px auto;
                background: var(--cyan); box-shadow: 0 0 30px var(--cyan), inset 0 0 14px #fff;
                transition: all 0.3s ease; border: 2px solid rgba(255,255,255,0.5);
            }
            .gate-readout { margin-top: 11px; text-align: center; padding-top: 10px; border-top: 1px dashed #1e293b; }
            .gate-readout h2 { margin: 0; font-family: 'Space Grotesk', sans-serif; font-size: 19px; letter-spacing: 0.8px; }
            .gate-readout p { margin: 4px 0 0 0; font-size: 11.5px; font-family: 'JetBrains Mono', monospace; color: var(--muted); }
            .ai-speech-bar {
                margin-top: 8px; padding: 6px 10px; border-radius: 8px; background: rgba(56, 189, 248, 0.08);
                border: 1px solid rgba(56, 189, 248, 0.2); font-size: 11px; color: #bae6fd;
                font-family: 'JetBrains Mono', monospace;
            }

            .student-row {
                background: #0a101f; border: 1px solid #1e293b; border-radius: 12px;
                padding: 10px 12px; margin-bottom: 9px; display: flex; justify-content: space-between; align-items: center;
                transition: 0.2s;
            }
            .student-row.inside { border-left: 3px solid var(--green); }
            .st-info strong { font-size: 13px; display: block; }
            .st-info small { font-size: 11px; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
            .st-actions { display: flex; gap: 6px; }
            .btn-in, .btn-out, .btn-deny {
                padding: 6px 10px; border-radius: 7px; border: none; font-size: 11px; font-weight: 700;
                cursor: pointer; font-family: 'JetBrains Mono', monospace; transition: 0.15s;
            }
            .btn-in { background: rgba(16, 185, 129, 0.18); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.4); }
            .btn-in:hover { background: var(--green); color: #04070f; }
            .btn-out { background: rgba(245, 158, 11, 0.18); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.4); }
            .btn-out:hover { background: var(--amber); color: #04070f; }
            .btn-deny { background: rgba(244, 63, 94, 0.18); color: var(--red); border: 1px solid rgba(244, 63, 94, 0.4); }
            .btn-deny:hover { background: var(--red); color: white; }

            .ctrl-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
            .btn-exec { padding: 10px; border-radius: 10px; border: none; font-weight: 700; font-size: 12px; cursor: pointer; }
            .btn-primary { background: linear-gradient(135deg, #38bdf8, #818cf8); color: #04070f; }
            .btn-ghost { background: #1e293b; color: #e2e8f0; }

            .kpi-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
            .kpi-box { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 14px 18px; }
            .kpi-box span { font-size: 11px; color: var(--muted); font-weight: 600; text-transform: uppercase; }
            .kpi-box h3 { margin: 5px 0 0 0; font-size: 25px; font-family: 'JetBrains Mono', monospace; }

            .vpc-map {
                display: grid; grid-template-columns: 1fr 50px 1fr 50px 1fr; align-items: center;
                background: #070c18; border: 1px solid #1e293b; border-radius: 14px; padding: 15px; margin-bottom: 18px;
            }
            .vpc-node {
                background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 11px; text-align: center; transition: 0.3s;
            }
            .vpc-node h4 { margin: 0 0 3px 0; font-size: 13px; }
            .vpc-node small { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--muted); }
            .vpc-node.lit-green { border-color: var(--green); box-shadow: 0 0 20px rgba(16,185,129,0.3); }
            .vpc-node.lit-red { border-color: var(--red); box-shadow: 0 0 20px rgba(244,63,94,0.35); }
            .vpc-node.lit-amber { border-color: var(--amber); box-shadow: 0 0 20px rgba(245,158,11,0.3); }
            .vpc-node.lit-cyan { border-color: var(--cyan); box-shadow: 0 0 20px rgba(56,189,248,0.3); }
            .pipe-line { text-align: center; font-family: 'JetBrains Mono', monospace; color: var(--cyan); font-size: 14px; font-weight: bold; }

            .analytics-grid { display: grid; grid-template-columns: 1fr 265px; gap: 18px; margin-bottom: 18px; }
            table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
            th { text-align: left; padding: 9px 10px; color: var(--muted); border-bottom: 1px solid #1e293b; font-size: 11px; text-transform: uppercase; }
            td { padding: 9px 10px; border-bottom: 1px solid rgba(30,41,59,0.6); }
            .pill-allow { background: rgba(16,185,129,0.14); color: var(--green); border: 1px solid rgba(16,185,129,0.35); padding: 3px 9px; border-radius: 99px; font-size: 10.5px; font-weight: 700; }
            .pill-out { background: rgba(245,158,11,0.14); color: var(--amber); border: 1px solid rgba(245,158,11,0.35); padding: 3px 9px; border-radius: 99px; font-size: 10.5px; font-weight: 700; }
            .pill-deny { background: rgba(244,63,94,0.14); color: var(--red); border: 1px solid rgba(244,63,94,0.35); padding: 3px 9px; border-radius: 99px; font-size: 10.5px; font-weight: 700; }

            .cw-terminal {
                background: #03050a; border: 1px solid #1e293b; border-radius: 12px; padding: 12px 16px;
                font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: #38bdf8;
                height: 115px; overflow-y: auto; line-height: 1.6;
            }
            .cw-line-ok { color: #34d399; }
            .cw-line-out { color: #fbbf24; }
            .cw-line-err { color: #fb7185; }

            input, select {
                width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid #1e293b;
                background: #070c18; color: white; margin-bottom: 8px; font-size: 12.5px;
            }
            @media (max-width: 1080px) {
                .main-grid, .analytics-grid { grid-template-columns: 1fr; }
                .kpi-strip { grid-template-columns: repeat(2, 1fr); }
                .vpc-map { grid-template-columns: 1fr; gap: 8px; }
            }
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="topbar">
                <div class="title-group">
                    <h1>AI-VOICE VIRTUAL CLASSROOM ACCESS GATE</h1>
                    <p>PROJECT 22 • AWS IoT CORE + LAMBDA IAM + REAL-TIME VOICE & BUZZER TELEMETRY</p>
                </div>
                <div class="top-actions">
                    <div class="status-chip"><div class="blink"></div> ESP32-WROOM SYNCED</div>
                    <button id="voiceToggleBtn" class="btn-top btn-voice on" onclick="toggleVoice()">AI Voice & Buzzer: ON</button>
                    <a href="/export-csv" class="btn-top">Export CSV</a>
                    <button id="lockdownBtn" class="btn-top btn-lockdown" onclick="toggleLockdown()">VPC Lockdown: OFF</button>
                </div>
            </div>

            <div class="main-grid">
                <div>
                    <div class="card" style="margin-bottom:18px;">
                        <div class="sec-label">
                            <span>ESP32 + RGB Breadboard Twin</span>
                            <span style="color:#64748b;">GPIO 25/26/27</span>
                        </div>

                        <div class="hw-stage">
                            <div class="esp-board">
                                <div class="esp-chip">
                                    <strong>ESP32-S</strong><br>
                                    <span style="color:#38bdf8;">WiFi: ACTIVE</span><br>
                                    <span style="color:#9ca3af;">Poll: 1.5s</span>
                                </div>

                                <div class="gpio-pins">
                                    <div class="pin-row"><span>D25(R)</span><div class="wire" id="wireR"></div><div class="resistor"></div></div>
                                    <div class="pin-row"><span>D26(G)</span><div class="wire" id="wireG"></div><div class="resistor"></div></div>
                                    <div class="pin-row"><span>D27(B)</span><div class="wire" id="wireB"></div><div class="resistor"></div></div>
                                </div>

                                <div class="rgb-bulb-wrap">
                                    <div class="rgb-bulb" id="rgbBulb"></div>
                                    <span style="font-size:10px;font-family:'JetBrains Mono',monospace;color:#94a3b8;">RGB LED</span>
                                </div>
                            </div>

                            <div class="gate-readout">
                                <h2 id="bannerStatus" style="color:var(--cyan);">SYSTEM STANDBY</h2>
                                <p id="bannerStudent">Awaiting RFID Tag Scan...</p>
                                <p id="bannerSubnet" style="color:var(--cyan);">Route: 0.0.0.0/0</p>
                                <div class="ai-speech-bar" id="aiSpeechText">AI Voice: "System ready."</div>
                            </div>
                        </div>

                        <div class="sec-label">
                            <span>Student RFID Cards (Entry / Exit)</span>
                            <span style="color:var(--green);" id="insideBadge">Inside: 0</span>
                        </div>

                        <div class="student-row" id="row-RFID-101">
                            <div class="st-info">
                                <strong>Aarav Sharma (RFID-101)</strong>
                                <small>25CAI014 • 10.0.1.0/24</small>
                            </div>
                            <div class="st-actions">
                                <button class="btn-in" onclick="scanCard('RFID-101', 'IN')">IN</button>
                                <button class="btn-out" onclick="scanCard('RFID-101', 'OUT')">OUT</button>
                            </div>
                        </div>

                        <div class="student-row" id="row-RFID-102">
                            <div class="st-info">
                                <strong>Priya Verma (RFID-102)</strong>
                                <small>25CAI029 • 10.0.1.0/24</small>
                            </div>
                            <div class="st-actions">
                                <button class="btn-in" onclick="scanCard('RFID-102', 'IN')">IN</button>
                                <button class="btn-out" onclick="scanCard('RFID-102', 'OUT')">OUT</button>
                            </div>
                        </div>

                        <div class="student-row" id="row-RFID-103">
                            <div class="st-info">
                                <strong>Rohan Das (RFID-103)</strong>
                                <small>25CAI042 • 10.0.2.0/24</small>
                            </div>
                            <div class="st-actions">
                                <button class="btn-in" onclick="scanCard('RFID-103', 'IN')">IN</button>
                                <button class="btn-out" onclick="scanCard('RFID-103', 'OUT')">OUT</button>
                            </div>
                        </div>

                        <div class="student-row" style="border-color:rgba(244,63,94,0.35);">
                            <div class="st-info">
                                <strong style="color:#fda4af;">Unknown Intruder (RFID-999)</strong>
                                <small style="color:var(--red);">Unauthorized Tag Test</small>
                            </div>
                            <div class="st-actions">
                                <button class="btn-deny" onclick="scanCard('RFID-999', 'IN')">TEST DENY</button>
                            </div>
                        </div>

                        <div class="ctrl-pair">
                            <button class="btn-exec btn-primary" onclick="autoDemo()">Run AI Voice Demo</button>
                            <button class="btn-exec btn-ghost" onclick="resetGate()">Reset Gate</button>
                        </div>
                    </div>

                    <div class="card">
                        <div class="sec-label"><span>Provision New Student Tag</span></div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                            <input type="text" id="regTag" placeholder="RFID-105">
                            <input type="text" id="regRoll" placeholder="Roll: 25CAI088">
                        </div>
                        <input type="text" id="regName" placeholder="Student Full Name">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                            <select id="regSubnet">
                                <option value="10.0.1.0/24">10.0.1.0/24</option>
                                <option value="10.0.2.0/24">10.0.2.0/24</option>
                            </select>
                            <select id="regZone">
                                <option value="CS-Cloud-Lab">CS-Cloud-Lab</option>
                                <option value="Research-VPC">Research-VPC</option>
                            </select>
                        </div>
                        <button class="btn-exec btn-primary" style="width:100%;" onclick="registerNewTag()">Authorize & Grant Entry</button>
                    </div>
                </div>

                <div>
                    <div class="kpi-strip">
                        <div class="kpi-box">
                            <span>Students Inside Lab</span>
                            <h3 id="kpiInside" style="color:var(--cyan);">0</h3>
                        </div>
                        <div class="kpi-box">
                            <span>Entries Granted (IN)</span>
                            <h3 id="kpiAllowed" style="color:var(--green);">0</h3>
                        </div>
                        <div class="kpi-box">
                            <span>Check-Outs (OUT)</span>
                            <h3 id="kpiOut" style="color:var(--amber);">0</h3>
                        </div>
                        <div class="kpi-box">
                            <span>Intrusions Blocked</span>
                            <h3 id="kpiDenied" style="color:var(--red);">0</h3>
                        </div>
                    </div>

                    <div class="vpc-map">
                        <div class="vpc-node" id="nodeEdge">
                            <h4>ESP32 RFID Edge</h4>
                            <small>TLS / HTTP POST</small>
                        </div>
                        <div class="pipe-line">══▶</div>
                        <div class="vpc-node" id="nodeLambda">
                            <h4>Lambda IAM Engine</h4>
                            <small>IN / OUT & ACL Check</small>
                        </div>
                        <div class="pipe-line">══▶</div>
                        <div class="vpc-node" id="nodeTarget">
                            <h4 id="targetZoneTitle">Target VPC Subnet</h4>
                            <small id="targetZoneSub">Awaiting Packet...</small>
                        </div>
                    </div>

                    <div class="analytics-grid">
                        <div class="card">
                            <div class="sec-label">
                                <span>DynamoDB / SQLite Subnet Access Ledger</span>
                                <span style="color:#64748b;">LIVE TELEMETRY</span>
                            </div>
                            <div style="overflow-x:auto;">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Time</th>
                                            <th>Tag</th>
                                            <th>Student</th>
                                            <th>Event</th>
                                            <th>VPC Subnet</th>
                                            <th>Decision</th>
                                        </tr>
                                    </thead>
                                    <tbody id="ledgerBody">
                                        <tr><td colspan="6" style="text-align:center;color:#64748b;">Click IN, OUT, or TEST DENY on any student card.</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div class="card" style="display:flex;flex-direction:column;justify-content:space-between;">
                            <div class="sec-label"><span>Access Telemetry Split</span></div>
                            <div style="position:relative;height:190px;">
                                <canvas id="donutChart"></canvas>
                            </div>
                            <div style="text-align:center;font-size:11px;color:var(--muted);margin-top:8px;">
                                Real-time IN / OUT / DENIED Ratio
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="sec-label">
                            <span>AWS CloudWatch / IoT Core Live Execution Stream</span>
                            <span style="color:var(--green);">● TELEMETRY ACTIVE</span>
                        </div>
                        <div class="cw-terminal" id="cwLogs">
                            <div>[SYSTEM] AI Voice & Buzzer Engine initialized on port 8080...</div>
                            <div>[IOT-CORE] Ready for RFID Entry (IN), Exit (OUT), and Security Alerts...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let soundEnabled = true;
            let audioCtx = null;

            function getAudioContext() {
                if (!audioCtx) {
                    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                    audioCtx = new AudioContextClass();
                }
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume();
                }
                return audioCtx;
            }

            function playTone(freq, type, startOffset, duration, volume = 0.35) {
                try {
                    const ctx = getAudioContext();
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = type;
                    osc.frequency.setValueAtTime(freq, ctx.currentTime + startOffset);
                    gain.gain.setValueAtTime(volume, ctx.currentTime + startOffset);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startOffset + duration);
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(ctx.currentTime + startOffset);
                    osc.stop(ctx.currentTime + startOffset + duration);
                } catch (e) {}
            }

            function playBuzzerForStatus(status) {
                if (!soundEnabled) return;
                if (status === 'ALLOWED') {
                    playTone(880, 'sine', 0, 0.14, 0.35);
                    playTone(1174.66, 'sine', 0.15, 0.22, 0.35);
                } else if (status === 'CHECKED_OUT') {
                    playTone(784, 'triangle', 0, 0.16, 0.35);
                    playTone(523.25, 'triangle', 0.18, 0.26, 0.35);
                } else {
                    playTone(180, 'sawtooth', 0, 0.16, 0.45);
                    playTone(150, 'sawtooth', 0.20, 0.16, 0.45);
                    playTone(130, 'sawtooth', 0.40, 0.28, 0.45);
                }
            }

            function speakAI(text) {
                try {
                    if (!soundEnabled || !('speechSynthesis' in window) || !text) return;
                    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
                        window.speechSynthesis.cancel();
                    }
                    const utter = new SpeechSynthesisUtterance(text);
                    utter.lang = 'en-US';
                    utter.rate = 1.02;
                    utter.volume = 1.0;
                    window.speechSynthesis.speak(utter);
                } catch (e) {}
            }

            function primeSpeech() {
                try {
                    if (soundEnabled && 'speechSynthesis' in window) {
                        const silent = new SpeechSynthesisUtterance('');
                        silent.volume = 0;
                        window.speechSynthesis.speak(silent);
                    }
                } catch (e) {}
            }

            function toggleVoice() {
                soundEnabled = !soundEnabled;
                const btn = document.getElementById('voiceToggleBtn');
                if (soundEnabled) {
                    btn.classList.add('on');
                    btn.innerText = 'AI Voice & Buzzer: ON';
                    playTone(880, 'sine', 0, 0.15, 0.3);
                    speakAI('AI voice and buzzer enabled.');
                } else {
                    btn.classList.remove('on');
                    btn.innerText = 'AI Voice & Buzzer: OFF';
                    try { window.speechSynthesis.cancel(); } catch (e) {}
                }
            }

            function appendLog(msg, cls = '') {
                const box = document.getElementById('cwLogs');
                const div = document.createElement('div');
                if (cls) div.className = cls;
                div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
                box.prepend(div);
            }

            const chart = new Chart(document.getElementById('donutChart').getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: ['Entry (IN)', 'Exit (OUT)', 'Denied'],
                    datasets: [{ data: [1, 0, 0], backgroundColor: ['#10b981', '#f59e0b', '#f43f5e'], borderWidth: 0 }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, cutout: '72%',
                    plugins: { legend: { position: 'bottom', labels: { color: '#cbd5e1', font: { size: 11 } } } }
                }
            });

            async function scanCard(tag, mode = 'AUTO') {
                getAudioContext();
                primeSpeech();
                appendLog(`IoT-Core received RFID tap: {"tag_id": "${tag}", "mode": "${mode}"}`);
                const fd = new FormData();
                fd.append('tag_id', tag);
                fd.append('mode', mode);
                const res = await fetch('/scan', { method: 'POST', body: fd });
                const data = await res.json();

                const logCls = data.status === 'ALLOWED' ? 'cw-line-ok' : (data.status === 'CHECKED_OUT' ? 'cw-line-out' : 'cw-line-err');
                appendLog(`Lambda IAM -> ${data.status} [${data.direction}] | ${data.student} | ${data.subnet}`, logCls);
                await syncUI();

                playBuzzerForStatus(data.status);
                speakAI(data.voice_text);
            }

            async function toggleLockdown() {
                getAudioContext();
                primeSpeech();
                const res = await fetch('/toggle-lockdown', { method: 'POST' });
                const data = await res.json();
                appendLog(data.lockdown ? 'ALERT: Emergency VPC Lockdown ENABLED!' : 'INFO: VPC Lockdown lifted.', data.lockdown ? 'cw-line-err' : 'cw-line-ok');
                await syncUI();
                playBuzzerForStatus(data.lockdown ? 'DENIED' : 'ALLOWED');
                speakAI(data.latest.voice_text);
            }

            async function resetGate() {
                getAudioContext();
                primeSpeech();
                const res = await fetch('/reset', { method: 'POST' });
                const data = await res.json();
                appendLog('System reset & logs cleared.');
                await syncUI();
                playBuzzerForStatus('CHECKED_OUT');
                speakAI(data.voice_text);
            }

            async function registerNewTag() {
                getAudioContext();
                primeSpeech();
                const tag = document.getElementById('regTag').value.trim();
                const name = document.getElementById('regName').value.trim();
                const roll = document.getElementById('regRoll').value.trim() || '25CAI099';
                const subnet = document.getElementById('regSubnet').value;
                const zone = document.getElementById('regZone').value;
                if (!tag || !name) return alert('Enter Tag ID and Student Name.');
                const fd = new FormData();
                fd.append('tag_id', tag); fd.append('name', name);
                fd.append('roll', roll); fd.append('subnet', subnet); fd.append('zone', zone);
                await fetch('/register', { method: 'POST', body: fd });
                appendLog(`IAM Policy Provisioned: ${tag} (${name}) -> ${subnet}`, 'cw-line-ok');
                document.getElementById('regTag').value = '';
                document.getElementById('regName').value = '';
                document.getElementById('regRoll').value = '';
                await scanCard(tag, 'IN');
            }

            function autoDemo() {
                getAudioContext();
                primeSpeech();
                const steps = [
                    { tag: 'RFID-101', mode: 'IN' },
                    { tag: 'RFID-999', mode: 'IN' },
                    { tag: 'RFID-101', mode: 'OUT' }
                ];
                steps.forEach((s, i) => {
                    setTimeout(() => scanCard(s.tag, s.mode), i * 2600);
                });
            }

            async function syncUI() {
                const res = await fetch('/api/dashboard-data');
                const d = await res.json();

                document.getElementById('kpiInside').innerText = d.inside_now;
                document.getElementById('insideBadge').innerText = `Inside: ${d.inside_now}`;
                document.getElementById('kpiAllowed').innerText = d.allowed;
                document.getElementById('kpiOut').innerText = d.checked_out;
                document.getElementById('kpiDenied').innerText = d.denied;

                ['RFID-101', 'RFID-102', 'RFID-103'].forEach(t => {
                    const el = document.getElementById(`row-${t}`);
                    if (el) {
                        if (d.inside_tags.includes(t)) el.classList.add('inside');
                        else el.classList.remove('inside');
                    }
                });

                const lBtn = document.getElementById('lockdownBtn');
                if (d.lockdown) {
                    lBtn.classList.add('active');
                    lBtn.innerText = 'VPC Lockdown: ACTIVE';
                } else {
                    lBtn.classList.remove('active');
                    lBtn.innerText = 'VPC Lockdown: OFF';
                }

                const st = d.latest.status;
                const bulb = document.getElementById('rgbBulb');
                const bStatus = document.getElementById('bannerStatus');
                const wR = document.getElementById('wireR');
                const wG = document.getElementById('wireG');
                const wB = document.getElementById('wireB');

                const nEdge = document.getElementById('nodeEdge');
                const nLam = document.getElementById('nodeLambda');
                const nTar = document.getElementById('nodeTarget');

                wR.style.background = '#334155'; wG.style.background = '#334155'; wB.style.background = '#334155';
                nEdge.className = 'vpc-node'; nLam.className = 'vpc-node'; nTar.className = 'vpc-node';

                if (st === 'ALLOWED') {
                    bulb.style.background = '#10b981';
                    bulb.style.boxShadow = '0 0 38px #10b981, inset 0 0 14px #fff';
                    bStatus.style.color = '#10b981';
                    bStatus.innerText = 'ENTRY GRANTED (IN)';
                    wG.style.background = '#10b981';
                    nEdge.classList.add('lit-green'); nLam.classList.add('lit-green'); nTar.classList.add('lit-green');
                } else if (st === 'CHECKED_OUT') {
                    bulb.style.background = '#f59e0b';
                    bulb.style.boxShadow = '0 0 38px #f59e0b, inset 0 0 14px #fff';
                    bStatus.style.color = '#f59e0b';
                    bStatus.innerText = 'CHECKED OUT (EXIT)';
                    wB.style.background = '#f59e0b';
                    nEdge.classList.add('lit-amber'); nLam.classList.add('lit-amber'); nTar.classList.add('lit-amber');
                } else if (st === 'DENIED') {
                    bulb.style.background = '#f43f5e';
                    bulb.style.boxShadow = '0 0 38px #f43f5e, inset 0 0 14px #fff';
                    bStatus.style.color = '#f43f5e';
                    bStatus.innerText = 'ACCESS DENIED';
                    wR.style.background = '#f43f5e';
                    nEdge.classList.add('lit-red'); nLam.classList.add('lit-red'); nTar.classList.add('lit-red');
                } else {
                    bulb.style.background = '#38bdf8';
                    bulb.style.boxShadow = '0 0 30px #38bdf8, inset 0 0 14px #fff';
                    bStatus.style.color = '#38bdf8';
                    bStatus.innerText = 'SYSTEM STANDBY';
                    wB.style.background = '#38bdf8';
                    nEdge.classList.add('lit-cyan');
                }

                document.getElementById('bannerStudent').innerText = `${d.latest.student} (${d.latest.tag_id})`;
                document.getElementById('bannerSubnet').innerText = `Route: ${d.latest.subnet} [${d.latest.zone}]`;
                document.getElementById('aiSpeechText').innerText = `AI Voice: "${d.latest.voice_text}"`;
                document.getElementById('targetZoneTitle').innerText = d.latest.zone;
                document.getElementById('targetZoneSub').innerText = d.latest.subnet;

                const tbody = document.getElementById('ledgerBody');
                if (d.logs.length > 0) {
                    tbody.innerHTML = d.logs.map(l => {
                        let badgeClass = l.status === 'ALLOWED' ? 'pill-allow' : (l.status === 'CHECKED_OUT' ? 'pill-out' : 'pill-deny');
                        return `
                        <tr>
                            <td style="font-family:'JetBrains Mono',monospace;color:#94a3b8;">${l.time}</td>
                            <td style="font-family:'JetBrains Mono',monospace;color:#38bdf8;font-weight:700;">${l.tag_id}</td>
                            <td><strong>${l.student}</strong><br><small style="color:#64748b;">${l.roll}</small></td>
                            <td><strong>${l.direction}</strong></td>
                            <td style="font-family:'JetBrains Mono',monospace;">${l.subnet}</td>
                            <td><span class="${badgeClass}">${l.status}</span></td>
                        </tr>`;
                    }).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b;">Click IN, OUT, or TEST DENY on any student card.</td></tr>';
                }

                if (d.total > 0) {
                    chart.data.datasets[0].data = [d.allowed, d.checked_out, d.denied];
                    chart.update();
                }
            }

            setInterval(syncUI, 2000);
            syncUI();
        </script>
    </body>
    </html>
    """