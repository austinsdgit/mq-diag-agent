import bcrypt
import json

# Test the existing hash first
existing_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIq.Zu3u8m"
print("Testing existing hash with 'admin123':", bcrypt.checkpw(b'admin123', existing_hash.encode('utf-8')))
print("Testing existing hash with 'secret':", bcrypt.checkpw(b'secret', existing_hash.encode('utf-8')))

# Generate fresh hashes
print("\nGenerating new hashes...")
admin_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')
viewer_hash = bcrypt.hashpw(b'viewer123', bcrypt.gensalt()).decode('utf-8')

print(f"New admin hash: {admin_hash}")
print(f"New viewer hash: {viewer_hash}")

# Verify new hashes work
print("\nVerifying new admin hash:", bcrypt.checkpw(b'admin123', admin_hash.encode('utf-8')))
print("Verifying new viewer hash:", bcrypt.checkpw(b'viewer123', viewer_hash.encode('utf-8')))

# Create new auth_users.json
users_data = {
    "users": {
        "admin": {
            "password": admin_hash,
            "role": "admin"
        },
        "viewer": {
            "password": viewer_hash,
            "role": "viewer"
        }
    }
}

with open('auth_users.json', 'w') as f:
    json.dump(users_data, f, indent=2)

print("\nauth_users.json updated successfully!")
