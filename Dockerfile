FROM python:3.11-slim

# Install IBM MQ client libraries and build tools
RUN apt-get update && \
    apt-get install -y wget curl gnupg2 gcc g++ make && \
    cd /tmp && \
    wget https://public.dhe.ibm.com/ibmdl/export/pub/software/websphere/messaging/mqdev/redist/9.3.0.0-IBM-MQC-Redist-LinuxX64.tar.gz && \
    mkdir -p /opt/mqm && \
    tar -xzf 9.3.0.0-IBM-MQC-Redist-LinuxX64.tar.gz -C /opt/mqm && \
    rm -rf /tmp/9.3.0.0-IBM-MQC-Redist-LinuxX64.tar.gz && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set MQ environment variables
ENV LD_LIBRARY_PATH=/opt/mqm/lib64:$LD_LIBRARY_PATH
ENV PATH=/opt/mqm/bin:$PATH

# Create /IBM and /.mqm directories with proper permissions for MQ client
RUN mkdir -p /IBM && chmod 777 /IBM && \
    mkdir -p /.mqm && chmod 777 /.mqm

# Set working directory
WORKDIR /app

# Upgrade pip and install build dependencies
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies in stages
RUN pip install --no-cache-dir pymqi
RUN pip install --no-cache-dir pydantic==1.10.12 python-dotenv
RUN pip install --no-cache-dir pydantic-settings
RUN pip install --no-cache-dir "mcp==1.27.1"
RUN pip install --no-cache-dir fastapi==0.100.0 uvicorn[standard]==0.23.0 httpx==0.24.1
RUN pip install --no-cache-dir websockets==12.0 requests==2.31.0 bcrypt>=4.0.0

# Copy MCP server code
COPY ibm-mq-mcp-server /app/ibm-mq-mcp-server

# Copy agent code
COPY backend/ /app/backend/
COPY frontend/index.html /app/frontend/index.html
COPY frontend/login.html /app/frontend/login.html
COPY frontend/queue-monitor.html /app/frontend/queue-monitor.html
COPY users.json /app/users.json
COPY auth_users.json /app/auth_users.json

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
