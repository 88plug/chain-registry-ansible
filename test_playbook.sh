#!/bin/bash

# Directory containing playbooks
PLAYBOOK_DIR="/root"

# Log file
LOGFILE="$PLAYBOOK_DIR/playbook_results.log"

# Function to stop service
stop_service() {
    local service_name="$1"
    echo "Stopping service: $service_name"
    systemctl disable --now "$service_name"
}

# Loop through all .yml files in the directory
for playbook in "$PLAYBOOK_DIR"/*.yml; do
    echo "Running playbook: $playbook" | tee -a "$LOGFILE"
    ansible-playbook -i hosts.ini "$playbook" >> "$LOGFILE" 2>&1

    # Check if playbook execution was successful
    status=$?
    if [ $status -ne 0 ]; then
        echo "Playbook $playbook failed with status $status" | tee -a "$LOGFILE"
        # Extract service name from playbook filename
        service_name=$(basename "$playbook" .yml | cut -d '_' -f 2-)
        # Stop the service related to the playbook
        stop_service "$service_name"
        # Exit if you want the script to stop on the first failure
        # exit $status
    else
        echo "Playbook $playbook completed successfully" | tee -a "$LOGFILE"
    fi
done

echo "All playbooks have been processed." | tee -a "$LOGFILE"
