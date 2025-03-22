#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime

def fetch_plan_from_tfc(token, host, organization, workspace, run_id=None, pr_number=None, branch=None, output_path=None, max_wait_minutes=15):
    """
    Fetch a plan JSON file from Terraform Cloud/Enterprise.
    
    Args:
        token: API token for Terraform Cloud/Enterprise
        host: Hostname for Terraform Cloud/Enterprise instance
        organization: Organization name in Terraform Cloud/Enterprise
        workspace: Workspace name in Terraform Cloud/Enterprise
        run_id: Optional specific run ID to fetch (if not specified, will use latest matching run)
        pr_number: Optional PR number to find the speculative plan for
        branch: Optional branch name to find the plan for
        output_path: Path to save the plan JSON file
        max_wait_minutes: Maximum time to wait for plan completion in minutes
    
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
    
    # Step 2: Find the run ID (specific, or from PR/branch, or latest)
    if run_id:
        run_id_to_use = run_id
        print(f"Using specified run ID: {run_id_to_use}")
    else:
        # Get runs for the workspace - use page[size]=20 to get more runs
        runs_url = f"{api_base}/workspaces/{workspace_id}/runs?page[size]=20"
        try:
            response = requests.get(runs_url, headers=headers)
            response.raise_for_status()
            runs_data = response.json()
            
            if not runs_data.get("data"):
                print("No runs found for this workspace", file=sys.stderr)
                sys.exit(1)
            
            matching_runs = []
            
            # If we have PR or branch info, look for matching speculative plans
            if pr_number or branch:
                search_type = "PR #" + str(pr_number) if pr_number else "branch " + branch
                print(f"Searching for speculative plans for {search_type}")
                
                for run in runs_data["data"]:
                    # Check if it's a speculative plan
                    is_speculative = run["attributes"].get("is-speculative", False)
                    if not is_speculative:
                        continue
                    
                    # Get the configuration version for more details
                    if "configuration-version" in run["relationships"]:
                        config_version_id = run["relationships"]["configuration-version"]["data"]["id"]
                        config_version_url = f"{api_base}/configuration-versions/{config_version_id}"
                        
                        try:
                            cv_response = requests.get(config_version_url, headers=headers)
                            cv_response.raise_for_status()
                            cv_data = cv_response.json()
                            
                            # Store the creation time for sorting
                            created_at = run["attributes"].get("created-at", "")
                            run_status = run["attributes"].get("status", "")
                            
                            # Check for PR number in ingress attributes
                            if pr_number and "ingress-attributes" in cv_data["data"]["attributes"]:
                                ingress_attrs = cv_data["data"]["attributes"]["ingress-attributes"]
                                if "pull-request-number" in ingress_attrs and str(ingress_attrs["pull-request-number"]) == str(pr_number):
                                    matching_runs.append({
                                        "run_id": run["id"],
                                        "created_at": created_at,
                                        "status": run_status
                                    })
                                    print(f"Found speculative plan for PR #{pr_number}, created at {created_at}, status: {run_status}")
                            
                            # Check for branch name in ingress attributes
                            if branch and "ingress-attributes" in cv_data["data"]["attributes"]:
                                ingress_attrs = cv_data["data"]["attributes"]["ingress-attributes"]
                                if "branch" in ingress_attrs and ingress_attrs["branch"] == branch:
                                    matching_runs.append({
                                        "run_id": run["id"],
                                        "created_at": created_at,
                                        "status": run_status
                                    })
                                    print(f"Found speculative plan for branch {branch}, created at {created_at}, status: {run_status}")
                        except requests.exceptions.RequestException:
                            # If we can't get config version info, continue to next run
                            continue
            
            # Use latest matching run or fall back to the latest run
            if matching_runs:
                # Sort by created_at in descending order to get the latest
                matching_runs.sort(key=lambda x: x["created_at"], reverse=True)
                
                # First try to find a run that's already completed
                completed_run = None
                in_progress_run = None
                
                for run in matching_runs:
                    status = run["status"]
                    # If we find a completed run, use it
                    if status in ["planned", "planned_and_finished", "applied", "completed"]:
                        completed_run = run
                        break
                    # Otherwise track the latest in-progress run
                    elif status in ["pending", "planning", "cost_estimating"]:
                        if in_progress_run is None:
                            in_progress_run = run
                
                if completed_run:
                    run_id_to_use = completed_run["run_id"]
                    print(f"Using latest completed speculative plan with ID: {run_id_to_use}, created at {completed_run['created_at']}")
                elif in_progress_run:
                    run_id_to_use = in_progress_run["run_id"]
                    print(f"No completed plans found. Using latest in-progress plan with ID: {run_id_to_use}, status: {in_progress_run['status']}")
                    print(f"Will wait for plan to complete (up to {max_wait_minutes} minutes)")
                else:
                    # If no run is in a valid state, use the latest one anyway
                    run_id_to_use = matching_runs[0]["run_id"]
                    print(f"No suitable plans found. Using latest plan with ID: {run_id_to_use}, status: {matching_runs[0]['status']}")
            else:
                if pr_number or branch:
                    print(f"No matching speculative plans found for {search_type}. Using latest run instead.", file=sys.stderr)
                
                run_id_to_use = runs_data["data"][0]["id"]
                print(f"Using latest run ID: {run_id_to_use}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error finding runs: {e}", file=sys.stderr)
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
        run_status = run_data["data"]["attributes"].get("status")
        if run_status not in ["planned", "planned_and_finished", "applied", "completed"]:
            print(f"Run is not in a completed plan state. Current status: {run_status}", file=sys.stderr)
            print(f"Waiting for plan to complete... (up to {max_wait_minutes} minutes)")
            
            # Calculate wait parameters
            max_retries = max_wait_minutes * 6  # Check every 10 seconds, so 6 tries per minute
            retry_count = 0
            
            # Wait for the plan to complete
            while retry_count < max_retries and run_status not in ["planned", "planned_and_finished", "applied", "completed"]:
                time.sleep(10)
                retry_count += 1
                
                # Calculate elapsed time for better logging
                elapsed_min = int(retry_count * 10 / 60)
                elapsed_sec = (retry_count * 10) % 60
                
                # Check status again
                response = requests.get(run_url, headers=headers)
                response.raise_for_status()
                run_data = response.json()
                run_status = run_data["data"]["attributes"].get("status")
                print(f"Current status: {run_status} (waited {elapsed_min}m {elapsed_sec}s, max {max_wait_minutes}m)")
                
                # If the run has errored or been canceled, fail early
                if run_status in ["errored", "canceled", "discarded"]:
                    print(f"Run has {run_status}. Cannot proceed.", file=sys.stderr)
                    sys.exit(1)
            
            if run_status not in ["planned", "planned_and_finished", "applied", "completed"]:
                print(f"Run did not complete in the allowed time ({max_wait_minutes} minutes). Final status: {run_status}", file=sys.stderr)
                sys.exit(1)
            
            print(f"Plan completed with status: {run_status}")
        
        # Get the plan ID - Handle the nested structure carefully
        if "relationships" not in run_data["data"]:
            print("Run data doesn't contain relationships", file=sys.stderr)
            sys.exit(1)
        
        if "plan" not in run_data["data"]["relationships"]:
            print("Run doesn't have plan data in relationships", file=sys.stderr)
            sys.exit(1)
            
        plan_data = run_data["data"]["relationships"]["plan"].get("data")
        if not plan_data or "id" not in plan_data:
            print("Plan data not found in run", file=sys.stderr)
            sys.exit(1)
            
        plan_id = plan_data["id"]
        print(f"Found plan ID: {plan_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error getting run details: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Error parsing run data: Missing key {e}", file=sys.stderr)
        print(f"Run data structure: {json.dumps(run_data, indent=2)}", file=sys.stderr)
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
    parser.add_argument('--run-id', help='Specific run ID to pull plan from (if not specified, will find best match or use latest run)')
    parser.add_argument('--pr-number', help='Pull request number to find the speculative plan for')
    parser.add_argument('--branch', help='Branch name to find the plan for')
    parser.add_argument('--output', required=True, help='Path to save the plan JSON file')
    parser.add_argument('--max-wait-minutes', type=int, default=15, help='Maximum time in minutes to wait for a plan to complete')
    
    args = parser.parse_args()
    
    fetch_plan_from_tfc(
        token=args.token,
        host=args.host,
        organization=args.organization,
        workspace=args.workspace,
        run_id=args.run_id,
        pr_number=args.pr_number,
        branch=args.branch,
        output_path=args.output,
        max_wait_minutes=args.max_wait_minutes
    )
    
    sys.exit(0)

if __name__ == "__main__":
    main()