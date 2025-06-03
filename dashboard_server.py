from flask import Flask, jsonify, render_template, request, abort
import os
import json

app = Flask(__name__, template_folder='templates')

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
MODLOG_FILE = os.path.join(DATA_DIR, 'modlog.json')

# Dummy user session for demo purposes
# In real app, replace with proper auth and session management
def get_current_user_role():
    # For demo, assume user is admin
    return "admin"

@app.route('/')
def index():
    return render_template('dashboard_v2.html')

@app.route('/modlogs')
def modlogs():
    role = get_current_user_role()
    if role not in ['admin', 'owner']:
        return abort(403, description="No access")

    limit = request.args.get('limit', default=50, type=int)
    try:
        with open(MODLOG_FILE, 'r') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []

    # Sort logs by time descending
    logs_sorted = sorted(logs, key=lambda x: x.get('time', ''), reverse=True)
    return jsonify(logs_sorted[:limit])

@app.route('/users')
def users():
    role = get_current_user_role()
    if role not in ['admin', 'owner']:
        return abort(403, description="No access")

    profiles_file = os.path.join(DATA_DIR, 'profiles.json')

    try:
        with open(profiles_file, 'r') as f:
            profiles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        profiles = {}

    merged_users = []
    for user_id, profile in profiles.items():
        stats = profile.get("stats", {})
        merged_user = {
            "user_id": user_id,
            "name": profile.get("name", ""),
            "role": profile.get("role", ""),
            "level": stats.get("level", 1),
            "xp": stats.get("xp", 0),
            "messages": stats.get("messages", 0),
            "time_spent": stats.get("time_spent", 0)
        }
        merged_users.append(merged_user)

    return jsonify(merged_users)
    
@app.route('/achievements')
def achievements():
    role = get_current_user_role()
    if role not in ['admin', 'owner']:
        return abort(403, description="No access")

    profiles_file = os.path.join(DATA_DIR, 'profiles.json')

    try:
        with open(profiles_file, 'r') as f:
            profiles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        profiles = {}

    achievements_data = []
    for user_id, profile in profiles.items():
        achievements = profile.get("achievements", [])
        achievements_data.append({
            "user_id": user_id,
            "name": profile.get("name", ""),
            "achievements": achievements
        })

    return jsonify(achievements_data)

@app.route('/leaderboard')
def leaderboard():
    role = get_current_user_role()
    if role not in ['admin', 'owner']:
        return abort(403, description="No access")

    profiles_file = os.path.join(DATA_DIR, 'profiles.json')

    try:
        with open(profiles_file, 'r') as f:
            profiles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        profiles = {}

    leaderboard_data = []
    for user_id, profile in profiles.items():
        stats = profile.get("stats", {})
        wallet = profile.get("wallet", {})
        achievements = profile.get("achievements", [])
        leaderboard_data.append({
            "user_id": user_id,
            "name": profile.get("name", ""),
            "xp": stats.get("xp", 0),
            "level": stats.get("level", 1),
            "coins": wallet.get("coins", 0),
            "achievements_count": len(achievements)
        })

    # Sort by XP descending by default
    leaderboard_data.sort(key=lambda x: x["xp"], reverse=True)

    return jsonify(leaderboard_data)

@app.route('/inventory/<user_id>')
def inventory(user_id):
    role = get_current_user_role()
    if role not in ['admin', 'owner']:
        return abort(403, description="No access")

    profiles_file = os.path.join(DATA_DIR, 'profiles.json')

    try:
        with open(profiles_file, 'r') as f:
            profiles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        profiles = {}

    profile = profiles.get(user_id)
    if not profile:
        return jsonify({"error": "User not found"}), 404

    inventory = profile.get("inventory", [])
    return jsonify({
        "user_id": user_id,
        "name": profile.get("name", ""),
        "inventory": inventory
    })

if __name__ == '__main__':
    app.run(debug=True)
