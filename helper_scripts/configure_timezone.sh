#!/bin/bash

# Get the hostname
HOSTNAME=$(hostname)

# Set the timezone to America/Mexico_City
sudo timedatectl set-timezone America/Mexico_City

# Get the current timezone line
CURRENT_TIMEZONE=$(timedatectl | grep "Time zone")

# Print the hostname and current timezone line
echo "$HOSTNAME, $CURRENT_TIMEZONE"