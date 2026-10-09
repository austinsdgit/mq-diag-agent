# MQ Diagnostic Agent Authentication

## Overview
The MQ Diagnostic Agent uses HTTP Basic Authentication to protect API endpoints.

## Default Users

### Admin User
- **Username**: `admin`
- **Password**: `admin123`
- **Role**: admin
- **Permissions**: Full access to all operations

### Viewer User
- **Username**: `viewer`
- **Password**: `viewer123`
- **Role**: viewer
- **Permissions**: Read-only access

## Configuration

User credentials are stored in `users.json` with bcrypt-hashed passwords.

### Password Format
Passwords are hashed using bcrypt with cost factor 12:
```python
import bcrypt
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
```

### Adding New Users

1. Generate a bcrypt hash for the password:
```python
import bcrypt
password = "your_password"
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
print(hashed.decode('utf-8'))
```

2. Add the user to `users.json`:
```json
{
  "users": {
    "newuser": {
      "password": "$2b$12$...",
      "role": "admin"
    }
  }
}
```

3. Rebuild and redeploy the Docker image.

## API Authentication

All API endpoints (except `/health`) require HTTP Basic Authentication.

### Example with curl
```bash
curl -u admin:admin123 http://localhost:8000/api/deadq/messages
```

### Example with Python requests
```python
import requests
from requests.auth import HTTPBasicAuth

response = requests.get(
    'http://localhost:8000/api/deadq/messages',
    auth=HTTPBasicAuth('admin', 'admin123')
)
```

### Frontend Authentication
The frontend automatically prompts for credentials and includes them in all API requests.

## Security Notes

⚠️ **IMPORTANT**: Change the default passwords in production!

1. Generate new bcrypt hashes for production passwords
2. Update `users.json` with the new hashes
3. Rebuild the Docker image
4. Deploy to your environment

## Troubleshooting

### 401 Unauthorized
- Check username and password are correct
- Verify the user exists in `users.json`
- Ensure the password hash is valid

### 403 Forbidden
- User is authenticated but lacks permissions for the operation
- Check the user's role in `users.json`