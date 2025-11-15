# Replicate Environments

A Python utility for replicating environment management objects (workflow handlers, config contexts, resource templates, and environment templates) between different sources and targets. The tool supports replication from/to API endpoints or local file systems, with automatic data cleaning and version management.

## Overview

This tool facilitates the migration and replication of environment management objects across different systems or environments. It can:

- Fetch objects from API endpoints or read from local JSON files
- Clean and transform objects by removing unwanted fields
- Save objects to local directories or post them to API endpoints
- Handle multiple versions of objects automatically
- Provide detailed success/failure reporting

## Features

- **Flexible Source/Target**: Supports both HTTP(S) URLs and local directories
- **Multiple Object Types**: Handles workflow handlers, config contexts, resource templates, and environment templates
- **Version Management**: Automatically fetches and processes all versions of objects
- **Data Cleaning**: Removes unwanted metadata fields, sharing configurations, and agent assignments
- **Dual Output**: When saving to disk, saves both raw and cleaned versions
- **Debug Mode**: Detailed logging for troubleshooting
- **Error Handling**: Comprehensive error reporting with success/failure summaries

## Prerequisites

- Python 3.6 or higher
- Required Python packages:
  - `requests`
  - `urllib3`

## Installation

1. Install required dependencies:

```bash
pip install requests urllib3
```

2. Make the script executable (optional):

```bash
chmod +x replicate-envs.py
```

## Usage

### Basic Syntax

```bash
python3 replicate-envs.py --source <SOURCE> --target <TARGET> --type <OBJECT_TYPE> [--debug]
```

### Required Arguments

- `--source`: Source location (URL starting with `http://` or `https://`, or local directory path)
- `--target`: Target location (URL starting with `http://` or `https://`, or local directory path)
- `--type`: Object type to replicate (one of: `workflowhandlers`, `configcontexts`, `resourcetemplates`, `environmenttemplates`)

### Optional Arguments

- `--debug`: Enable debug output (shows raw and cleaned JSON objects, API requests/responses)

### Environment Variables

The following environment variables must be set:

- `SOURCE_API_KEY`: API key for accessing the source (required when source is a URL)
- `TARGET_API_KEY`: API key for accessing the target (required when target is a URL)

Set them before running the script:

```bash
export SOURCE_API_KEY="your-source-api-key"
export TARGET_API_KEY="your-target-api-key"
```

Or inline:

```bash
SOURCE_API_KEY="key1" TARGET_API_KEY="key2" python3 replicate-envs.py --source ... --target ... --type ...
```

## Usage Examples

### 1. Replicate from API to Local Directory

Download workflow handlers from an API endpoint and save them to a local directory:

```bash
export SOURCE_API_KEY="source-api-key-here"
export TARGET_API_KEY="target-api-key-here"
python replicate-envs.py --source https://console.compute.customer.cloud \
                          --target ./output \
                          --type workflowhandlers
```

This will:
- Fetch all workflow handlers from the API
- Download all versions of each handler
- Save raw versions to `./output/workflowhandlers/raw/`
- Save cleaned versions to `./output/workflowhandlers/`
- Save the raw GET response to `./output/workflowhandlers/raw-dump-get.json`
- Create the output directory if it doesn't exist

### 2. Replicate from Local Directory to API

Upload resource templates from local JSON files to an API endpoint:

```bash
export SOURCE_API_KEY="source-api-key-here"
export TARGET_API_KEY="target-api-key-here"
python replicate-envs.py --source ./input \
                          --target https://console.compute-uat.customer.cloud \
                          --type resourcetemplates
```

This will:
- Read all JSON files from `./input/resourcetemplates/`
- Clean each object (removing IDs, timestamps, sharing, agents, etc.)
- POST each cleaned object to the target API
- Display success/failure summary at the end

### 3. Replicate from One API to Another API

Copy environment templates directly from one API endpoint to another:

```bash
export SOURCE_API_KEY="source-api-key-here"
export TARGET_API_KEY="target-api-key-here"
python replicate-envs.py --source https://console.compute.customer.cloud \
                          --target https://console.compute-uat.customer.cloud \
                          --type environmenttemplates
```

This will:
- Fetch all environment templates from the source API
- Fetch all versions of each template
- Clean each object
- POST each cleaned object to the target API
- Display success/failure summary

### 4. Replicate with Debug Output

Get detailed output for troubleshooting:

```bash
export SOURCE_API_KEY="source-api-key-here"
export TARGET_API_KEY="target-api-key-here"
python replicate-envs.py --source https://console.compute.customer.cloud \
                          --target ./output \
                          --type configcontexts \
                          --debug
```

Debug mode shows:
- Raw API responses from GET requests
- Raw object data before cleaning
- Cleaned object data after transformation
- POST payloads when uploading to API
- Version information for each object

### 5. Copy Between Local Directories

Copy and clean objects from one local directory to another:

```bash
export SOURCE_API_KEY="source-api-key-here"
export TARGET_API_KEY="target-api-key-here"
python replicate-envs.py --source ./input \
                          --target ./output \
                          --type workflowhandlers
```

This will:
- Read all JSON files from `./input/workflowhandlers/`
- Clean each object
- Save raw versions to `./output/workflowhandlers/raw/`
- Save cleaned versions to `./output/workflowhandlers/`
- Create the output directory structure if it doesn't exist

## Object Types

The following object types are supported:

- `workflowhandlers`: Workflow handler definitions
- `configcontexts`: Configuration context objects
- `resourcetemplates`: Resource template definitions
- `environmenttemplates`: Environment template definitions

## Data Cleaning

The tool automatically cleans objects before saving or posting by:

### Removed Metadata Fields
- `id`
- `modifiedAt`
- `createdAt`
- `projectID`
- `createdBy`
- `modifiedBy`

### Metadata Updates
- Sets `metadata.project` to `"system-catalog"` (configurable in code)

### Removed Spec Fields
- `spec.sharing`: Sharing configuration
- `spec.agents`: Agent assignments at the spec level

### Removed Hook Agent Fields
- `agents` field from all hook items (e.g., in `spec.hooks.onInit`, `spec.hooks.onDeploy`, etc.)

### Removed Top-Level Fields
- `status`: Status information

## File Structure

When saving to a local directory, the tool creates the following structure:

```
<target-dir>/
├── <object-type>/
│   ├── raw-dump-get.json          # Raw GET response (only when source is URL)
│   ├── raw/                        # Raw objects directory
│   │   ├── <name>.json            # Object without version
│   │   ├── <name>-<version>.json  # Object with version
│   │   └── ...
│   ├── <name>.json                # Cleaned object without version
│   ├── <name>-<version>.json       # Cleaned object with version
│   └── ...
```

### Example Structure

```
output/
└── environmenttemplates/
    ├── raw-dump-get.json
    ├── raw/
    │   ├── system-netris-tenant.json
    │   ├── system-netris-tenant-1.4.json
    │   └── system-serverless-pods-v4.0.json
    ├── system-netris-tenant.json
    ├── system-netris-tenant-1.4.json
    └── system-serverless-pods-v4.0.json
```

## API Endpoint Format

The tool constructs API endpoints using the following format:

```
{base_url}/apis/eaas.envmgmt.io/v1/projects/{project}/{object_type}
```

Where:
- `base_url`: The source/target URL you provide
- `project`: Hardcoded as `"system-catalog"` (configurable in code)
- `object_type`: The object type specified with `--type`

For fetching versions:
```
{base_url}/apis/eaas.envmgmt.io/v1/projects/{project}/{object_type}/{name}/versions
```

## API Query Parameters

When fetching objects from a URL, the tool automatically appends:
- `limit=100`
- `offset=0`
- `order=DESC`
- `orderBy=createdAt`

## Output Summary

After execution, the tool displays a summary:

```
==================== Replication Summary ====================
✅ Successes (5):
  - environmenttemplates/system-netris-tenant (1.4)
  - environmenttemplates/system-serverless-pods (v4.0)
  ...
❌ Failures (0):
```

## Error Handling

- **Missing Environment Variables**: Script exits with error message if API keys are not set
- **API Errors**: HTTP errors are caught and reported in the failures list
- **Version Fetch Errors**: If fetching versions fails, falls back to using the base object
- **File Errors**: File read/write errors are handled gracefully

## Troubleshooting

### Issue: "Environment variables SOURCE_API_KEY and TARGET_API_KEY must be set"

**Solution**: Ensure both environment variables are exported before running the script, even if one is not used (e.g., when source or target is a local directory).

### Issue: SSL Certificate Verification Errors

**Solution**: The script disables SSL verification by default (`VERIFY_SSL = False`). If you need to enable it, modify the code.

### Issue: Objects not appearing in target

**Solution**: 
- Check API keys are correct
- Verify network connectivity
- Use `--debug` flag to see API responses
- Check the failures list in the summary output

### Issue: Version fetching fails

**Solution**: The script will fall back to using the base object if version fetching fails. Check the warning messages in the output.

### Issue: Files not saved to disk

**Solution**: 
- Verify write permissions for the target directory
- Check that the target path exists or can be created
- Review error messages in the output

## Configuration

To modify default settings, edit the constants at the top of `replicate-envs.py`:

- `PROJECT`: Default project name (default: `"system-catalog"`)
- `OBJECT_TYPES`: List of supported object types
- `VERIFY_SSL`: SSL certificate verification (default: `False`)

## Security Notes

- API keys are passed via environment variables (not command line) for security
- SSL verification is disabled by default - enable it in production environments
- Sensitive data in objects (like credentials) is preserved as-is during replication

## Limitations

- Maximum 100 objects per API call (pagination not implemented)
- Only processes objects in the `system-catalog` project (configurable in code)
- SSL verification is disabled by default
- Does not handle object dependencies or relationships

## License

This script is provided as-is for internal use.

