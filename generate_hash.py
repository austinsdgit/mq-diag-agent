import bcrypt
import json

# Generate new hashes
admin_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt())
viewer_hash = bcrypt.hashpw(b'viewer123', bcrypt.gensalt())

print("Admin hash:", admin_hash.decode('utf-8'))
print("Viewer hash:", viewer_hash.decode('utf-8'))

# Test verification
print("\nTesting admin password:")
print("Direct bytes:", bcrypt.checkpw(b'admin123', admin_hash))
print("From string:", bcrypt.checkpw(b'admin123', admin_hash.decode('utf-8').encode('utf-8')))

# Create auth_users.json
users_data = {
    "users": {
        "admin": {
            "password": admin_hash.decode('utf-8'),
            "role": "admin"
        },
        "viewer": {
            "password": viewer_hash.decode('utf-8'),
            "role": "viewer"
        }
    }
}

with open('auth_users.json', 'w') as f:
    json.dump(users_data, f, indent=2)

print("\nauth_users.json created successfully")
