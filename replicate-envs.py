import requests
import json
import copy
import urllib3
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Disable SSL warnings for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --------------------------
# CONFIGURATION
# --------------------------

SOURCE_BASE_URL = os.environ.get("SOURCE_BASE_URL", "https://console.compute.sharonai.cloud")
TARGET_BASE_URL = os.environ.get("TARGET_BASE_URL", "https://console.compute-uat.sharonai.cloud")

# Object URLs
OBJECT_URLS = {
    "workflowhandlers": f"{SOURCE_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/workflowhandlers",
    "configcontexts": f"{SOURCE_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/configcontexts",
    "resourcetemplates": f"{SOURCE_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/resourcetemplates",
    "environmenttemplates": f"{SOURCE_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/environmenttemplates"
}

TARGET_OBJECT_URLS = {
    "workflowhandlers": f"{TARGET_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/workflowhandlers",
    "configcontexts": f"{TARGET_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/configcontexts",
    "resourcetemplates": f"{TARGET_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/resourcetemplates",
    "environmenttemplates": f"{TARGET_BASE_URL}/apis/eaas.envmgmt.io/v1/projects/system-catalog/environmenttemplates"
}

SOURCE_API_KEY = os.environ.get("SOURCE_API_KEY")
TARGET_API_KEY = os.environ.get("TARGET_API_KEY")

if not SOURCE_API_KEY or not TARGET_API_KEY:
    raise ValueError("Both SOURCE_API_KEY and TARGET_API_KEY environment variables must be set!")

VERIFY_SSL = False
MAX_WORKERS = 5  # threads for parallel posting

# --------------------------
# HELPERS
# --------------------------

def remove_unwanted_fields(item):
    """
    Clean an object before replication:
      - Remove metadata fields: id, modifiedAt, createdAt, projectID
      - Remove top-level status block
      - Remove 'sharing' block from spec if present
    """
    cleaned = copy.deepcopy(item)

    # Clean metadata
    meta = cleaned.get("metadata", {})
    for field in ["id", "modifiedAt", "createdAt", "projectID"]:
        meta.pop(field, None)
    cleaned["metadata"] = meta

    # Remove status if present
    cleaned.pop("status", None)

    # Remove sharing block from spec if present
    spec = cleaned.get("spec", {})
    if "sharing" in spec:
        spec.pop("sharing")
    cleaned["spec"] = spec

    return cleaned


def fetch_objects(url):
    headers = {
        "accept": "application/json",
        "X-API-KEY": SOURCE_API_KEY
    }
    print(f"📥 Fetching objects from {url} ...")
    response = requests.get(url, headers=headers, verify=VERIFY_SSL)
    response.raise_for_status()
    return response.json().get("items", [])


def post_object(target_url, obj):
    """Post object and return tuple (success: bool, name: str, message: str)"""
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-API-KEY": TARGET_API_KEY
    }

    name = obj["metadata"].get("name", "<unknown>")

    try:
        resp = requests.post(target_url, headers=headers, verify=VERIFY_SSL, json=obj)
        if resp.status_code in [200, 201]:
            return True, name, "Successfully created"
        elif resp.status_code == 409:
            return True, name, "Already exists (409 CONFLICT)"
        else:
            return False, name, f"Failed with status {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, name, f"Exception: {str(e)}"


def replicate_objects(source_url, target_url, debug=False):
    """Fetch objects and post them in parallel, returning successes and failures"""
    items = fetch_objects(source_url)
    print(f"Found {len(items)} objects\n")

    cleaned_objects = [remove_unwanted_fields(item) for item in items]

    success_list = []
    failure_list = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_index = {executor.submit(post_object, target_url, obj): idx for idx, obj in enumerate(cleaned_objects)}

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            raw_obj = items[idx]
            cleaned_obj = cleaned_objects[idx]

            success, name, message = future.result()

            if debug:
                print(f"\n================ Object #{idx + 1} (RAW) ================\n")
                print(json.dumps(raw_obj, indent=2))
                print(f"\n================ Object #{idx + 1} (CLEANED) ================\n")
                print(json.dumps(cleaned_obj, indent=2))

            if success:
                success_list.append((name, message))
                print(f"✅ {message}: {name}")
            else:
                failure_list.append((name, message))
                print(f"❌ {message}: {name}")

    return success_list, failure_list


# --------------------------
# MAIN FLOW
# --------------------------

def main():
    parser = argparse.ArgumentParser(description="Replicate objects in system-catalog.")
    parser.add_argument("--workflowhandlers", action="store_true", help="Replicate workflowhandlers objects")
    parser.add_argument("--configcontexts", action="store_true", help="Replicate configcontexts objects")
    parser.add_argument("--resourcetemplates", action="store_true", help="Replicate resourcetemplates objects")
    parser.add_argument("--environmenttemplates", action="store_true", help="Replicate environmenttemplates objects")
    parser.add_argument("--all", action="store_true", help="Replicate all object types")
    parser.add_argument("--debug", action="store_true", help="Print raw and cleaned JSON payloads")

    args = parser.parse_args()

    # Determine which object types to replicate
    object_types = []
    if args.workflowhandlers or args.all:
        object_types.append("workflowhandlers")
    if args.configcontexts or args.all:
        object_types.append("configcontexts")
    if args.resourcetemplates or args.all:
        object_types.append("resourcetemplates")
    if args.environmenttemplates or args.all:
        object_types.append("environmenttemplates")

    if not object_types:
        print("No replication type selected. Use --workflowhandlers, --configcontexts, --resourcetemplates, --environmenttemplates, or --all.")
        return

    overall_success = []
    overall_failures = []

    # Replicate each selected object type
    for obj_type in object_types:
        print(f"\n🔄 Replicating {obj_type} ...")
        source_url = OBJECT_URLS[obj_type]
        target_url = TARGET_OBJECT_URLS[obj_type]
        success, failures = replicate_objects(source_url, target_url, debug=args.debug)
        overall_success.extend(success)
        overall_failures.extend(failures)

    # --------------------------
    # SUMMARY REPORT
    # --------------------------
    print("\n==================== REPLICATION SUMMARY ====================\n")
    print(f"Total Successful: {len(overall_success)}")
    for name, msg in overall_success:
        print(f"✅ {name}: {msg}")

    print(f"\nTotal Failures: {len(overall_failures)}")
    for name, msg in overall_failures:
        print(f"❌ {name}: {msg}")

    print("\n==============================================================\n")


if __name__ == "__main__":
    main()

