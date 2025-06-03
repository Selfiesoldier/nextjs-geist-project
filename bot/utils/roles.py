import json
import os

ROLES_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'roles.json')

ROLE_HIERARCHY = {
    "user": 1,
    "trusted": 2,
    "admin": 3,
    "owner": 4
}

def load_roles():
    try:
        with open(ROLES_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"owners": [], "admins": [], "trusted": []}

def save_roles(roles):
    with open(ROLES_FILE, 'w') as f:
        json.dump(roles, f, indent=2)

def get_role(user_id):
    roles = load_roles()
    if user_id in roles.get("owners", []):
        return "owner"
    elif user_id in roles.get("admins", []):
        return "admin"
    elif user_id in roles.get("trusted", []):
        return "trusted"
    else:
        return "user"

def require_role(user_id, minimum_level):
    user_role = get_role(user_id)
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(minimum_level, 0)
    return user_level >= required_level
