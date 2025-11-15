#!/usr/bin/env python3
"""
Replicate environment management objects between API endpoints or to/from disk.

This script replicates workflowhandlers, configcontexts, resourcetemplates, 
environmenttemplates, computeprofiles, and serviceprofiles between different API endpoints or saves/loads them from disk.
Objects are cleaned (removing IDs, timestamps, sharing, agents, etc.) before replication.

Requirements:
    - Python 3
    - Environment variables: SOURCE_API_KEY and TARGET_API_KEY must be set
    - Dependencies: requests, urllib3

Usage:
    python replicate-envs.py --source SOURCE --target TARGET --type OBJECT_TYPE [--debug]

Arguments:
    --source    Source URL (e.g., https://console.compute.customer.cloud) or directory path
    --target    Target URL (e.g., https://console.compute-uat.customer.cloud) or directory path  
    --type      Object type to replicate: workflowhandlers, configcontexts,
                resourcetemplates, environmenttemplates, computeprofiles, or serviceprofiles
    --debug     Enable debug output (optional)

Examples:

    1. Replicate from API to local directory:
       export SOURCE_API_KEY="source-api-key-here"
       export TARGET_API_KEY="target-api-key-here"
       python replicate-envs.py --source https://console.compute.customer.cloud \
                                 --target ./output \
                                 --type workflowhandlers

    2. Replicate from local directory to API:
       python replicate-envs.py --source ./input \
                                 --target https://console.compute-uat.customer.cloud \
                                 --type resourcetemplates

    3. Replicate from one API to another API:
       python replicate-envs.py --source https://console.compute.customer.cloud \
                                 --target https://console.compute-uat.customer.cloud \
                                 --type environmenttemplates

    4. Replicate with debug output:
       python replicate-envs.py --source https://console.compute.customer.cloud \
                                 --target ./output \
                                 --type configcontexts \
                                 --debug

    5. Copy between local directories:
       python replicate-envs.py --source ./input \
                                 --target ./output \
                                 --type workflowhandlers

Output:
    When target is a directory:
        - Creates directory structure: target/OBJECT_TYPE/
        - Saves raw versions: target/OBJECT_TYPE/raw/NAME-VERSION.json
        - Saves cleaned versions: target/OBJECT_TYPE/NAME-VERSION.json
        - Saves raw GET response: target/OBJECT_TYPE/raw-dump-get.json

    When target is an API URL:
        - POSTs cleaned objects to the target API
        - Displays success/failure summary at the end
"""

import os
import sys
import json
import copy
import argparse
import requests
import urllib3
from pathlib import Path

# --------------------------
# Disable SSL warnings
# --------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --------------------------
# Configuration Defaults
# --------------------------
PROJECT = "system-catalog"
OBJECT_TYPES = [
    "workflowhandlers",
    "configcontexts",
    "resourcetemplates",
    "environmenttemplates",
    "computeprofiles",
    "serviceprofiles"
]
VERIFY_SSL = False

# API namespace mapping: maps object types to their API namespace
API_NAMESPACE_MAP = {
    "workflowhandlers": "eaas.envmgmt.io",
    "configcontexts": "eaas.envmgmt.io",
    "resourcetemplates": "eaas.envmgmt.io",
    "environmenttemplates": "eaas.envmgmt.io",
    "computeprofiles": "paas.envmgmt.io",
    "serviceprofiles": "paas.envmgmt.io"
}

# --------------------------
# Helpers
# --------------------------

def remove_unwanted_fields(obj):
    cleaned = copy.deepcopy(obj)
    meta = cleaned.get("metadata", {})
    for field in ["id", "modifiedAt", "createdAt", "projectID", "createdBy", "modifiedBy"]:
        meta.pop(field, None)
    meta["project"] = PROJECT
    cleaned["metadata"] = meta
    # Remove sharing and agents if present
    if "spec" in cleaned and isinstance(cleaned["spec"], dict):
        cleaned["spec"].pop("sharing", None)
        cleaned["spec"].pop("agents", None)
        # Remove agents from hooks if present
        hooks = cleaned["spec"].get("hooks")
        if hooks and isinstance(hooks, dict):
            for hook_type, hook_list in hooks.items():
                if isinstance(hook_list, list):
                    for hook_item in hook_list:
                        if isinstance(hook_item, dict):
                            hook_item.pop("agents", None)
    # Remove top-level status if present
    cleaned.pop("status", None)
    return cleaned

def build_source_url(base_url: str, project: str, object_type: str) -> str:
    api_namespace = API_NAMESPACE_MAP.get(object_type, "eaas.envmgmt.io")
    return f"{base_url.rstrip('/')}/apis/{api_namespace}/v1/projects/{project}/{object_type}"

def fetch_objects_from_url(url, api_key, debug=False):
    # Append ?limit=100&offset=0&order=DESC&orderBy=createdAt to the url
    url = f"{url}?limit=100&offset=0&order=DESC&orderBy=createdAt"
    headers = {"accept": "application/json", "X-API-KEY": api_key}
    resp = requests.get(url, headers=headers, verify=VERIFY_SSL)
    resp.raise_for_status()
    data = resp.json()
    if debug:
        print(f"\n[DEBUG] Raw GET data from {url}:\n{json.dumps(data, indent=2)}")
    return data.get("items", [])

def fetch_versions_from_url(base_url, project, object_type, name, api_key, debug=False):
    api_namespace = API_NAMESPACE_MAP.get(object_type, "eaas.envmgmt.io")
    version_url = f"{base_url.rstrip('/')}/apis/{api_namespace}/v1/projects/{project}/{object_type}/{name}/versions"
    headers = {"accept": "application/json", "X-API-KEY": api_key}
    resp = requests.get(version_url, headers=headers, verify=VERIFY_SSL)
    resp.raise_for_status()
    data = resp.json()
    versions = data.get("items", [])
    if debug:
        print(f"\n[DEBUG] Versions for {name} ({object_type}): {[v.get('spec', {}).get('version', '') for v in versions]}")
    return versions

def save_to_disk(obj, target_dir, object_type, name, version=None, raw=False):
    base_dir = Path(target_dir) / object_type
    if raw:
        base_dir = base_dir / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{name}"
    if version:
        filename += f"-{version}"
    filename += ".json"
    file_path = base_dir / filename
    with open(file_path, "w") as f:
        json.dump(obj, f, indent=2)
    return file_path

def post_object_to_url(obj, url, api_key, debug=False):
    headers = {"accept": "application/json", "Content-Type": "application/json", "X-API-KEY": api_key}
    name = obj["metadata"].get("name", "<unknown>")
    resp = requests.post(url, headers=headers, verify=VERIFY_SSL, json=obj)
    if debug:
        print(f"\n[DEBUG] POST payload for {name}:\n{json.dumps(obj, indent=2)}")
    if resp.status_code in [200, 201]:
        return True, None
    else:
        return False, f"{resp.status_code}: {resp.text}"

def replicate_objects(object_type, source, target, source_api_key, target_api_key, debug=False):
    successes = []
    failures = []

    source_is_url = source.startswith("http")
    target_is_url = target.startswith("http")

    # Create target directory if it doesn't exist (only if target is a directory path)
    if not target_is_url:
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)

    # Determine source items
    if source_is_url:
        url = build_source_url(source, PROJECT, object_type)
        items = fetch_objects_from_url(url, source_api_key, debug)
        # Save raw GET response if target is disk
        if not target_is_url:
            raw_get_path = Path(target) / object_type / "raw-dump-get.json"
            raw_get_path.parent.mkdir(parents=True, exist_ok=True)
            with open(raw_get_path, "w") as f:
                json.dump(items, f, indent=2)
    else:
        # Read JSON files from disk
        object_dir = Path(source) / object_type
        items = []
        for file_path in object_dir.glob("*.json"):
            with open(file_path) as f:
                items.append(json.load(f))

    for item in items:
        name = item["metadata"].get("name", "<unknown>")
        versions = []
        if source_is_url:
            # Fetch all versions (computeprofiles and serviceprofiles don't support versions)
            if object_type in ["computeprofiles", "serviceprofiles"]:
                versions = [item]
            else:
                try:
                    versions = fetch_versions_from_url(source, PROJECT, object_type, name, source_api_key, debug)
                except Exception as e:
                    print(f"⚠️ Failed to fetch versions for {name}: {e}")
                    versions = [item]
        else:
            versions = [item]

        for version_obj in versions:
            version_name = version_obj.get("spec", {}).get("version")
            cleaned = remove_unwanted_fields(version_obj)

            # Debug print
            if debug:
                print(f"\n[DEBUG] Raw object:\n{json.dumps(version_obj, indent=2)}")
                print(f"\n[DEBUG] Cleaned object:\n{json.dumps(cleaned, indent=2)}")

            # Save to disk
            if not target_is_url:
                save_to_disk(version_obj, target, object_type, name, version_name, raw=True)
                save_to_disk(cleaned, target, object_type, name, version_name, raw=False)

            # Post to URL
            if target_is_url:
                target_url = build_source_url(target, PROJECT, object_type)
                success, error = post_object_to_url(cleaned, target_url, target_api_key, debug)
                if success:
                    successes.append(f"{object_type}/{name} ({version_name})")
                else:
                    failures.append(f"{object_type}/{name} ({version_name}) => {error}")
            else:
                successes.append(f"{object_type}/{name} ({version_name})")

    return successes, failures

# --------------------------
# Main
# --------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Source URL or directory")
    parser.add_argument("--target", required=True, help="Target URL or directory")
    parser.add_argument("--type", required=True, choices=OBJECT_TYPES, help="Object type to replicate")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    source_api_key = os.getenv("SOURCE_API_KEY")
    target_api_key = os.getenv("TARGET_API_KEY")
    if not source_api_key or not target_api_key:
        print("❌ Environment variables SOURCE_API_KEY and TARGET_API_KEY must be set")
        sys.exit(1)

    successes, failures = replicate_objects(
        args.type,
        args.source,
        args.target,
        source_api_key,
        target_api_key,
        debug=args.debug
    )

    print("\n==================== Replication Summary ====================")
    print(f"✅ Successes ({len(successes)}):")
    for s in successes:
        print(f"  - {s}")
    print(f"❌ Failures ({len(failures)}):")
    for f in failures:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
