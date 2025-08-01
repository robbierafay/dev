#!/bin/bash

set -euo pipefail

# Check for required argument
if [ $# -ne 1 ]; then
  echo "Usage: $0 <instance-name>"
  exit 1
fi

# Set required variables
INSTANCE_NAME="$1"
COMPARTMENT_ID="ocid1.tenancy.oc1..aaaaaaaaaa3ghjcqbrbzmssbzhxzhxf24rpmuyxbaxwcj2axwoqkpd56ljkq"
SUBNET_ID="ocid1.subnet.oc1.phx.aaaaaaaagil52gwydmofgsunyyy7vyv4pz7jp2rfrac5p2uro3ezuyomoiwa"
AVAILABILITY_DOMAIN="PaOl:PHX-AD-1"
SHAPE="VM.Standard.E4.Flex"
IMAGE_ID="ocid1.image.oc1.phx.aaaaaaaa7vfcxlrhixvjz457yvgs22f3676uzw7rdodw7w4jptmgorzroqda" # Ubuntu24.04
BOOT_VOLUME_SIZE_GB=300
OCID_FILE=~/oci_instances.txt
SSH_PUBLIC_KEY='/opt/rafay/keys/oci.pub'
SSH_PRIVATE_KEY='/opt/rafay/keys/oci'
SSH_CONFIG=~/.ssh/config

# Define cloud-init script for disk expansion and root partition resize
CLOUD_INIT=$(cat <<EOF
#cloud-config
runcmd:
  - sudo dd iflag=direct if=/dev/sda of=/dev/null count=1
  - echo "1" | sudo tee /sys/class/block/sda/device/rescan
  - sudo growpart /dev/sda 1
  - sudo resize2fs /dev/sda1
EOF
)

# Launch the instance with expanded root volume and cloud-init
echo "Launching instance: $INSTANCE_NAME with ${BOOT_VOLUME_SIZE_GB}GB root volume"
LAUNCH_OUTPUT=$(oci compute instance launch \
    --compartment-id $COMPARTMENT_ID \
    --availability-domain "$AVAILABILITY_DOMAIN" \
    --shape $SHAPE \
    --subnet-id $SUBNET_ID \
    --assign-public-ip true \
    --display-name $INSTANCE_NAME \
    --image-id $IMAGE_ID \
    --shape-config '{"ocpus": 8.0, "memoryInGBs": 128.0}' \
    --metadata '{"ssh_authorized_keys":"'"$(cat $SSH_PUBLIC_KEY)"'", "user_data":"'"$(echo "$CLOUD_INIT" | base64 | tr -d '\n')"'"}' \
    --boot-volume-size-in-gbs ${BOOT_VOLUME_SIZE_GB})

INSTANCE_ID=$(echo "$LAUNCH_OUTPUT" | jq -r '.data.id')
echo "Instance launched with OCID: $INSTANCE_ID"

# Wait for the instance to be in RUNNING state
echo "Waiting for instance to enter RUNNING state..."
for i in {1..30}; do
  STATE=$(oci compute instance get --instance-id "$INSTANCE_ID" --query 'data."lifecycle-state"' --raw-output)
  echo "  Current state: $STATE"
  if [[ "$STATE" == "RUNNING" ]]; then
    echo "Instance is now in RUNNING state."
    break
  fi
  sleep 10
done

# Optional: fail if it never became RUNNING
if [[ "$STATE" != "RUNNING" ]]; then
  echo "ERROR: Instance did not reach RUNNING state within expected time." >&2
  exit 1
fi


# Get the public IP address
PUBLIC_IP=$(oci compute instance list-vnics \
  --instance-id "$INSTANCE_ID" \
  --query 'data[0]."public-ip"' \
  --raw-output)

echo "Instance is now running. Public IP: $PUBLIC_IP"

# Append instance ID to file
echo "$INSTANCE_ID" >> "$OCID_FILE"
echo "Instance OCID appended to $OCID_FILE"

# Add to ~/.ssh/config
echo "Updating SSH config at $SSH_CONFIG"
{
  echo ""
  echo "Host $INSTANCE_NAME  # $INSTANCE_ID"
  echo "  Hostname $PUBLIC_IP"
  echo "  StrictHostKeyChecking no"
  echo "  IdentityFile $SSH_PRIVATE_KEY"
  echo "  User ubuntu"
} >> "$SSH_CONFIG"

echo "Done. You can now SSH using: ssh $INSTANCE_NAME"

