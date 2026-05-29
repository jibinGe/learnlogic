#!/bin/bash

# Configuration
# SERVER_IP="13.232.143.33" # Prod server
SERVER_IP="65.0.193.46" # Dev sever
PEM_FILE="/Users/nexonetics/Desktop/Learnogic/LearnogicFullstack/learnlogic/imp/learnogic_key.pem"
SERVER_APP_DIR="/home/ubuntu/learnogic"  # Path on the server
LOCAL_APP_DIR="/Users/nexonetics/Desktop/Learnogic/LearnogicFullstack/learnlogic"  # Path on your local machine

# ssh -i /Users/jibin_george/Desktop/learnlogic/imp/learnogic_key.pem ubuntu@13.205.53.126

# scp -i $PEM_FILE ubuntu@$SERVER_IP:${SERVER_APP_DIR}/sql_app.db ${LOCAL_APP_DIR}/

echo "Downloaded from $SERVER_IP"
# ssh -i /Users/jibin_george/Desktop/learnlogic/imp/learnogic_key.pem ubuntu@13.235.73.80
# Make sure PEM file has correct permissions
chmod 400 $PEM_FILE

# Connect to server and setup
# ssh -i $PEM_FILE ubuntu@$SERVER_IP << ENDSSH  
#     # Update system
#     sudo apt update && sudo apt upgrade -y

#     # Install required packages
#     sudo apt install -y python3-pip python3-venv nginx

#     # Create application directory if it doesn't exist
#     mkdir -p ${SERVER_APP_DIR}

#     # Install Python dependencies
#     cd ${SERVER_APP_DIR}
#     python3 -m venv venv
#     source venv/bin/activate
#     pip install -r 

#     # Setup Nginx
#     sudo nano /etc/nginx/sites-available/fastapi << EOF
# server {
#     listen 80;
#     server_name prod-api.learnogic.com;

#     location / {
#         proxy_pass http://127.0.0.1:8000;
#         proxy_set_header Host \$host;
#         proxy_set_header X-Real-IP \$remote_addr;
#         proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto \$scheme;
#     }
# }
# EOF

#     # Enable the Nginx site
#     sudo ln -sf /etc/nginx/sites-available/fastapi /etc/nginx/sites-enabled/
#     sudo rm -f /etc/nginx/sites-enabled/default
#     sudo systemctl restart nginx

#     # Setup systemd service
#     sudo tee /etc/systemd/system/fastapi.service << EOF
# [Unit]
# Description=FastAPI application
# After=network.target

# [Service]
# User=ubuntu
# Group=ubuntu
# WorkingDirectory=${SERVER_APP_DIR}
# Environment="PATH=${SERVER_APP_DIR}/venv/bin"
# ExecStart=${SERVER_APP_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# Restart=always

# [Install]
# WantedBy=multi-user.target
# EOF

#     # Start and enable the service
#     sudo systemctl daemon-reload
#     sudo systemctl start fastapi
#     sudo systemctl enable fastapi
# ENDSSH

# Copy application files
scp -i $PEM_FILE -r ${LOCAL_APP_DIR}/app ubuntu@$SERVER_IP:${SERVER_APP_DIR}/
scp -i $PEM_FILE ${LOCAL_APP_DIR}/requirements.txt ubuntu@$SERVER_IP:${SERVER_APP_DIR}/
scp -i $PEM_FILE ${LOCAL_APP_DIR}/.env ubuntu@$SERVER_IP:${SERVER_APP_DIR}/
scp -i $PEM_FILE ${LOCAL_APP_DIR}/sql_app.db ubuntu@$SERVER_IP:${SERVER_APP_DIR}/

# scp -i $PEM_FILE ubuntu@$SERVER_IP:${SERVER_APP_DIR}/sql_app.db ${LOCAL_APP_DIR}/

# Restart the service
ssh -i $PEM_FILE ubuntu@$SERVER_IP "sudo systemctl restart fastapi"

echo "Deployment completed!"