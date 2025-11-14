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

OBJECT_TYPES = ["workflowhandlers", "configcontexts", "resourcetemplates", "environmenttemplates"]

MAX_WORKERS = 5  # threads for parallel posting
VERIFY_SSL = False

# --------------------------
# HELPERS
# --------------------------

def remove_unwanted_fields(item):
    """Clean object for replication"""
    cleaned = copy.deepcopy(item)

    # Clean metadata
    meta = cleaned.get("metadata", {})
    for field in ["id", "modifiedAt", "createdAt", "projectID"]:
        meta.pop(field, None)
    cleaned["metadata"] = meta

    # Remove status
    cleaned.pop("status", None)

    # Remove sharing block from spec
    spec = cleaned.get("spec", {})
    if "sharing" in spec:
        spec.pop("sharing")
    cleaned["spec"] = spec

    return cleaned


def fetch_objects_from_url(url, api_key):
    """Fetch objects from URL"""
    headers = {"accept": "application/json", "X-API-KEY": api_key}
    print(f"📥 Fetching objects from {url} ...")
    response = requests.get(url, headers=headers, verify=VERIFY_SSL)
    response.raise_for_status()
    return response.json()


def fetch_objects_from_disk(source_dir, obj_type):
    """Load all JSON objects from source_dir/<obj_type>, ignoring raw subdirectory"""
    path = os.path.join(source_dir, obj_type)
    if not os.path.exists(path):
        print(f"⚠️  Source directory does not exist for {obj_type}: {path}")
        return []

    items = []
    for filename in os.listdir(path):
        filepath = os.path.join(path, filename)
        if os.path.isdir(filepath) and os.path.basename(filepath) == "raw":
            continue
        if filename.endswith(".json"):
            try:
                with open(filepath, "r") as f:
                    obj = json.load(f)
                    items.append(obj)
            except Exception as e:
                print(f"❌ Failed to load {filepath}: {e}")
    print(f"📥 Loaded {len(items)} objects from disk for {obj_type}")
    return items


def post_object_to_url(target_url, obj, api_key):
    """POST object to URL"""
    headers = {"accept": "application/json", "Content-Type": "application/json", "X-API-KEY": api_key}
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


def write_object_to_disk(target_dir, obj_type, obj, raw_blob=None):
    """Write object JSON to target_dir/<obj_type>/<name>.json; optionally store raw_blob in raw subdir"""
    obj_name = obj["metadata"].get("name", "unknown")
    obj_path = os.path.join(target_dir, obj_type)
    os.makedirs(obj_path, exist_ok=True)
    cleaned_file = os.path.join(obj_path, f"{obj_name}.json")

    try:
        with open(cleaned_file, "w") as f:
            json.dump(obj, f, indent=2)

        if raw_blob:
            raw_path = os.path.join(obj_path, "raw")
            os.makedirs(raw_path, exist_ok=True)
            raw_file = os.path.join(raw_path, f"{obj_name}.json")
            with open(raw_file, "w") as f:
                json.dump(raw_blob, f, indent=2)

        return True, obj_name, "Written to disk"
    except Exception as e:
        return False, obj_name, f"Failed to write to disk: {e}"


def replicate_objects(obj_type, source_base, target_base, source_api_key=None, target_api_key=None, debug=False):
    """Replicate objects for a given type from source to target (URL or disk)"""
    source_is_dir = not source_base.startswith("http")
    target_is_dir = not target_base.startswith("http")

    raw_dir = os.path.join(target_base, obj_type, "raw") if target_is_dir else None
    if raw_dir:
        os.makedirs(raw_dir, exist_ok=True)

    # Fetch objects
    if source_is_dir:
        items = fetch_objects_from_disk(source_base, obj_type)
        data_dump = None
    else:
        url = f"{source_base}/apis/eaas.envmgmt.io/v1/projects/system-catalog/{obj_type}"
        data = fetch_objects_from_url(url, source_api_key)
        items = data.get("items", [])

        # Save raw GET response if target is disk
        if target_is_dir:
            raw_dump_file = os.path.join(raw_dir, "raw-dump-get.json")
            with open(raw_dump_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"💾 Saved raw GET response to {raw_dump_file}")

    print(f"Found {len(items)} {obj_type} objects")

    success_list = []
    failure_list = []

    # Clean objects for posting/writing
    cleaned_objects = [remove_unwanted_fields(obj) for obj in items]

    # Parallel processing
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_index = {}
        for idx, cleaned_obj in enumerate(cleaned_objects):
            raw_obj = items[idx] if target_is_dir else None
            if target_is_dir:
                future = executor.submit(write_object_to_disk, target_base, obj_type, cleaned_obj, raw_blob=raw_obj)
            else:
                target_url = f"{target_base}/apis/eaas.envmgmt.io/v1/projects/system-catalog/{obj_type}"
                future = executor.submit(post_object_to_url, target_url, cleaned_obj, target_api_key)
            future_to_index[future] = idx

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            raw_obj = items[idx] if target_is_dir else None
            cleaned_obj = cleaned_objects[idx]
            success, name, message = future.result()

            if debug:
                print(f"\n================ {obj_type} Object #{idx+1} (RAW) ================\n")
                print(json.dumps(raw_obj, indent=2) if raw_obj else "(source from URL)")
                print(f"\n================ {obj_type} Object #{idx+1} (CLEANED) ================\n")
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
    parser = argparse.ArgumentParser(description="Replicate system-catalog objects with disk/URL support.")
    parser.add_argument("--workflowhandlers", action="store_true")
    parser.add_argument("--configcontexts", action="store_true")
    parser.add_argument("--resourcetemplates", action="store_true")
    parser.add_argument("--environmenttemplates", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--source", required=True, help="Source base URL or directory")
    parser.add_argument("--target", required=True, help="Target base URL or directory")
    args = parser.parse_args()

    # Determine object types
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
        print("No object types selected. Use --workflowhandlers, --configcontexts, --resourcetemplates, --environmenttemplates, or --all.")
        return

    source_is_dir = not args.source.startswith("http")
    target_is_dir = not args.target.startswith("http")

    if not source_is_dir and not os.environ.get("SOURCE_API_KEY"):
        raise ValueError("SOURCE_API_KEY environment variable must be set for source URL")
    if not target_is_dir and not os.environ.get("TARGET_API_KEY"):
        raise ValueError("TARGET_API_KEY environment variable must be set for target URL")

    source_api_key = os.environ.get("SOURCE_API_KEY")
    target_api_key = os.environ.get("TARGET_API_KEY")

    overall_success = []
    overall_failures = []

    for obj_type in object_types:
        print(f"\n🔄 Replicating {obj_type} ...")
        success, failures = replicate_objects(
            obj_type,
            source_base=args.source,
            target_base=args.target,
            source_api_key=source_api_key,
            target_api_key=target_api_key,
            debug=args.debug
        )
        overall_success.extend(success)
        overall_failures.extend(failures)

    # Summary
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
