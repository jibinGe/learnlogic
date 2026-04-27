#!/bin/bash

# Configuration
# SERVER_IP="13.232.143.33"  # Prod
# SERVER_IP="65.0.193.46"  # Test
PEM_FILE="/Users/jibin_george/Desktop/learnlogic/imp/learnogic_key.pem"
SERVER_APP_DIR="/home/ubuntu/learnogic"  # Path on the server
LOCAL_APP_DIR="/Users/jibin_george/Desktop/learnlogic"  # Path on your local machine

# Make sure PEM file has correct permissions
chmod 400 $PEM_FILE

scp -i $PEM_FILE ubuntu@$SERVER_IP:${SERVER_APP_DIR}/sql_app.db ${LOCAL_APP_DIR}/ # download
# scp -i $PEM_FILE ${LOCAL_APP_DIR}/sql_app.db ubuntu@$SERVER_IP:${SERVER_APP_DIR}/ # upload


echo "Deployment completed!"