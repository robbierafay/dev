#!/bin/bash

# Check for mandatory argument
if [ -z "$1" ]; then
  echo "Usage: $0 <ACTION>"
  echo "Example: $0 start|stop"
  exit 1
fi

ACTION=$1
INSTANCES=$(grep keepon ~/oci_instances.txt | awk '{print $1}')

for inst in $INSTANCES; do
  echo
  echo "###############################################"
  echo "[+] Performing '${ACTION}' on OCI instance $inst"
  oci compute instance action --instance-id "$inst" --action "$ACTION"
  echo
  echo "###############################################"
  echo
done

