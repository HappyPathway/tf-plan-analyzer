#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import requests

def fetch_plan_from_tfc(token, host, organization, workspace, run_id=None, output_path=None):
    """
    Fetch a plan JSON file from Terraform Cloud/Enterprise.
    
    Args:
        token: API token for Terraform Cloud/Enterprise
        host: Hostname for Terraform Cloud/Enterprise instance
        organization: Organization name in Terraform Cloud/Enterprise
        workspace: Workspace name in Terraform Cloud/Enterprise
        run_id: Optional specific run ID to fetch (if not provided, will fetch latest)
        output_path: Path to save the plan JSON file
    
    Returns:
        Path to the downloaded plan JSON file
    """
    # Set up API headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.api+json"
    }
    
    api_base = f"https://{host}/api/v2"
    
    # Step 1: Find the workspace ID
    workspace_url = f"{api_base}/organizations/{organization}/workspaces/{workspace}"
    try:
        response = requests.get(workspace_url, headers=headers)
        response.raise_for_status()
        workspace_data = response.json()
        workspace_id = workspace_data["data"]["id"]
        print(f"Found workspace ID: {workspace_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error finding workspace: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    
    # Step 2: Find the run ID (either specified or latest)
    if run_id:
        run_id_to_use = run_id
        print(f"Using specified run ID: {run_id_to_use}")
    else:
        # Get the latest run
        runs_url = f"{api_base}/workspaces/{workspace_id}/runs?page[size]=1"
        try:
            response = requests.get(runs_url, headers=headers)
            response.raise_for_status()
            runs_data = response.json()
            if not runs_data["data"]:
                print("No runs found for this workspace", file=sys.stderr)
                sys.exit(1)
            run_id_to_use = runs_data["data"][0]["id"]
            print(f"Using latest run ID: {run_id_to_use}")
        except requests.exceptions.RequestException as e:
            print(f"Error finding latest run: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}", file=sys.stderr)
            sys.exit(1)
    
    # Step 3: Get the plan ID from the run
    run_url = f"{api_base}/runs/{run_id_to_use}"
    try:
        response = requests.get(run_url, headers=headers)
        response.raise_for_status()
        run_data = response.json()
        
        # Check run status - plan must be completed
        run_status = run_data["data"]["attributes"]["status"]
        if run_status not in ["planned", "planned_and_finished", "applied", "completed"]:
            print(f"Run is not in a completed plan state. Current status: {run_status}", file=sys.stderr)
            sys.exit(1)
        
        # Get the plan ID
        plan_id = run_data["data"]["relationships"]["plan"]["data"]["id"]
        print(f"Found plan ID: {plan_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error getting run details: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    
    # Step 4: Get the plan JSON export
    plan_url = f"{api_base}/plans/{plan_id}/json-output"
    try:
        response = requests.get(plan_url, headers=headers)
        response.raise_for_status()
        plan_data = response.json()
        
        # Save to file
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(plan_data, f, indent=2)
            print(f"Plan JSON saved to {output_path}")
            return output_path
        else:
            return plan_data
    except requests.exceptions.RequestException as e:
        print(f"Error getting plan JSON: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Fetch Terraform plan JSON from Terraform Cloud/Enterprise')
    parser.add_argument('--token', required=True, help='API token for Terraform Cloud/Enterprise')
    parser.add_argument('--host', default='app.terraform.io', help='Hostname for Terraform Cloud/Enterprise instance')
    parser.add_argument('--organization', required=True, help='Organization name in Terraform Cloud/Enterprise')
    parser.add_argument('--workspace', required=True, help='Workspace name in Terraform Cloud/Enterprise')
    parser.add_argument('--run-id', help='Specific run ID to pull plan from (if not specified, will use latest run)')
    parser.add_argument('--output', required=True, help='Path to save the plan JSON file')
    
    args = parser.parse_args()
    
    fetch_plan_from_tfc(
        token=args.token,
        host=args.host,
        organization=args.organization,
        workspace=args.workspace,
        run_id=args.run_id,
        output_path=args.output
    )
    
    sys.exit(0)

if __name__ == "__main__":
    main()