#!/usr/bin/env python3

import argparse
import json
import os
import sys
import google.generativeai as genai
from enum import Enum

class Severity(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3
    
    @classmethod
    def from_string(cls, s):
        return {
            'low': cls.LOW,
            'medium': cls.MEDIUM,
            'high': cls.HIGH,
            'critical': cls.CRITICAL
        }.get(s.lower(), cls.LOW)
    
    def __str__(self):
        return self.name.lower()

def setup_gemini_api(api_key):
    """Configure the Gemini API with the provided key."""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-pro')

def load_terraform_plan(plan_path):
    """Load a Terraform plan JSON file."""
    try:
        with open(plan_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading Terraform plan: {e}", file=sys.stderr)
        sys.exit(1)

def extract_plan_changes(plan_data):
    """Extract the relevant changes from the Terraform plan."""
    changes = []
    
    # Extract resource changes
    if 'resource_changes' in plan_data:
        for change in plan_data['resource_changes']:
            # Skip resources that aren't changing
            if change.get('change', {}).get('actions') == ['no-op']:
                continue
                
            resource_type = change.get('type', '')
            resource_name = change.get('name', '')
            actions = change.get('change', {}).get('actions', [])
            
            # Extract before and after values
            before = change.get('change', {}).get('before', {})
            after = change.get('change', {}).get('after', {})
            
            changes.append({
                'resource_type': resource_type,
                'resource_name': resource_name,
                'actions': actions,
                'before': before,
                'after': after
            })
    
    return changes

def generate_plan_summary(plan_data):
    """Generate a simplified summary of the Terraform plan."""
    summary = {
        'add': [],
        'change': [],
        'delete': [],
        'totals': {'add': 0, 'change': 0, 'delete': 0}
    }
    
    # Extract resource changes
    if 'resource_changes' in plan_data:
        for change in plan_data['resource_changes']:
            actions = change.get('change', {}).get('actions', [])
            resource_type = change.get('type', '')
            resource_name = change.get('name', '')
            address = change.get('address', f"{resource_type}.{resource_name}")
            
            # Skip no-ops
            if actions == ['no-op']:
                continue
                
            # Categorize by action type
            if 'create' in actions:
                summary['add'].append({
                    'address': address,
                    'type': resource_type,
                    'name': resource_name
                })
                summary['totals']['add'] += 1
            elif 'update' in actions or 'replace' in actions:
                action_type = 'update' if 'update' in actions else 'replace'
                summary['change'].append({
                    'address': address,
                    'type': resource_type,
                    'name': resource_name,
                    'action': action_type
                })
                summary['totals']['change'] += 1
            elif 'delete' in actions:
                summary['delete'].append({
                    'address': address,
                    'type': resource_type,
                    'name': resource_name
                })
                summary['totals']['delete'] += 1
    
    return summary

def analyze_plan_with_gemini(model, changes, severity_threshold):
    """Use Google's Gemini to analyze the Terraform plan for security risks."""
    
    # Prepare the prompt for Gemini
    prompt = f"""
    As a security expert, analyze this Terraform plan for security and safety risks.
    
    Terraform Plan Changes:
    ```json
    {json.dumps(changes, indent=2)}
    ```
    
    Identify any security concerns, including but not limited to:
    1. Exposed credentials or secrets
    2. Public access to sensitive resources
    3. Missing encryption
    4. Overly permissive IAM roles or security groups
    5. Resource configurations that don't follow security best practices
    6. Potential for data loss or unintended destruction of resources
    
    For each issue found:
    1. Assign a severity (LOW, MEDIUM, HIGH, CRITICAL)
    2. Explain the potential security impact
    3. Recommend specific fixes
    
    Format your response as a JSON array of issues with these fields:
    - resource_type: The type of Terraform resource
    - resource_name: The name of the resource
    - severity: The issue severity (LOW, MEDIUM, HIGH, CRITICAL)
    - description: A clear explanation of the security issue
    - impact: The potential security impact if this issue is exploited
    - recommendation: Specific actions to fix the issue
    
    Only include actual security concerns, not style or efficiency issues.
    """
    
    try:
        response = model.generate_content(prompt)
        
        # Parse the response to extract structured data
        try:
            # Try to find and parse JSON in the response
            content = response.text
            
            # Find JSON content within the text (it may be wrapped in markdown code blocks)
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_content = json_match.group(1)
            else:
                # Try to find any array in the text
                json_match = re.search(r'\[\s*{.*}\s*\]', content, re.DOTALL)
                if json_match:
                    json_content = json_match.group(0)
                else:
                    json_content = content
            
            issues = json.loads(json_content)
            
            # Filter issues by severity threshold
            threshold = Severity.from_string(severity_threshold)
            filtered_issues = []
            
            for issue in issues:
                issue_severity = Severity.from_string(issue.get('severity', 'LOW'))
                if issue_severity.value >= threshold.value:
                    filtered_issues.append(issue)
            
            return filtered_issues
            
        except json.JSONDecodeError:
            # If we can't parse JSON, return the raw response as a single issue
            return [{
                'resource_type': 'general',
                'resource_name': 'plan-wide',
                'severity': 'MEDIUM',
                'description': 'Analysis could not be structured properly',
                'impact': 'Unable to automatically process security concerns',
                'recommendation': 'Review the full analysis text',
                'full_text': response.text
            }]
            
    except Exception as e:
        print(f"Error analyzing plan with Gemini: {e}", file=sys.stderr)
        return [{
            'resource_type': 'error',
            'resource_name': 'analysis-failed',
            'severity': 'HIGH',
            'description': f'Failed to analyze plan: {str(e)}',
            'impact': 'Security risks might be present but couldn\'t be detected',
            'recommendation': 'Check the plan manually or fix the API error'
        }]

def generate_markdown_report(issues, plan_path, plan_data=None):
    """Generate a markdown report of the security issues and plan summary."""
    report = f"""# Terraform Plan Analysis

Plan file: `{plan_path}`
Generated: {os.popen('date').read().strip()}

"""

    # Add plan summary if plan_data is provided
    if plan_data:
        plan_summary = generate_plan_summary(plan_data)
        
        # Add plan summary section
        report += """## Plan Summary

| Operation | Count |
|-----------|-------|
"""
        report += f"| Create | {plan_summary['totals']['add']} |\n"
        report += f"| Update/Replace | {plan_summary['totals']['change']} |\n"
        report += f"| Delete | {plan_summary['totals']['delete']} |\n"
        
        # Add detailed resource changes
        if plan_summary['totals']['add'] > 0:
            report += "\n### Resources to Create\n\n"
            for resource in plan_summary['add']:
                report += f"- `{resource['address']}`\n"
                
        if plan_summary['totals']['change'] > 0:
            report += "\n### Resources to Update/Replace\n\n"
            for resource in plan_summary['change']:
                action = resource.get('action', 'update')
                report += f"- `{resource['address']}` ({action})\n"
                
        if plan_summary['totals']['delete'] > 0:
            report += "\n### Resources to Delete\n\n"
            for resource in plan_summary['delete']:
                report += f"- `{resource['address']}`\n"
        
        report += "\n"

    # Security issues section
    report += f"""## Security Findings Summary

Total issues found: {len(issues)}

| Severity | Count |
|----------|-------|
"""
    
    # Count issues by severity
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    for issue in issues:
        severity = issue.get('severity', '').lower()
        if severity in severity_counts:
            severity_counts[severity] += 1
    
    # Add severity counts to the report
    for severity, count in severity_counts.items():
        report += f"| {severity.upper()} | {count} |\n"
    
    # Add detailed findings
    if issues:
        report += "\n## Detailed Findings\n\n"
        
        for i, issue in enumerate(issues, 1):
            resource_type = issue.get('resource_type', 'Unknown')
            resource_name = issue.get('resource_name', 'Unknown')
            severity = issue.get('severity', 'UNKNOWN').upper()
            description = issue.get('description', 'No description provided')
            impact = issue.get('impact', 'No impact analysis provided')
            recommendation = issue.get('recommendation', 'No recommendations provided')
            
            report += f"### Issue {i}: {severity} - {resource_type}.{resource_name}\n\n"
            report += f"**Description**: {description}\n\n"
            report += f"**Potential Impact**: {impact}\n\n"
            report += f"**Recommendation**: {recommendation}\n\n"
            
            if 'full_text' in issue:
                report += f"**Full Analysis**:\n\n```\n{issue['full_text']}\n```\n\n"
            
            report += "---\n\n"
    else:
        report += "\nNo security issues detected at or above the specified threshold.\n"
    
    return report

def get_highest_severity(issues):
    """Get the highest severity level from the list of issues."""
    if not issues:
        return "none"
        
    severity_levels = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    highest = -1
    
    for issue in issues:
        sev = issue.get("severity", "").lower()
        if sev in severity_levels and severity_levels[sev] > highest:
            highest = severity_levels[sev]
    
    for sev, level in severity_levels.items():
        if level == highest:
            return sev
            
    return "none"

def main():
    parser = argparse.ArgumentParser(description='Analyze Terraform plan for security issues using Google Gemini.')
    parser.add_argument('--plan-path', required=True, help='Path to the Terraform plan JSON file')
    parser.add_argument('--api-key', required=True, help='Google Gemini API key')
    parser.add_argument('--severity-threshold', default='medium', choices=['low', 'medium', 'high', 'critical'], 
                        help='Minimum severity level to include in the report')
    parser.add_argument('--fail-level', default='high', choices=['low', 'medium', 'high', 'critical'],
                        help='Fail the action if issues at or above this severity are found')
    parser.add_argument('--output', default='tf-plan-analysis.md', help='Output file path')
    parser.add_argument('--include-plan-summary', action='store_true', default=True,
                        help='Include a simplified plan summary in the report')
    
    args = parser.parse_args()
    
    # Configure Gemini API
    model = setup_gemini_api(args.api_key)
    
    # Load the Terraform plan
    plan_data = load_terraform_plan(args.plan_path)
    
    # Extract changes from the plan
    changes = extract_plan_changes(plan_data)
    
    # Analyze the plan
    issues = analyze_plan_with_gemini(model, changes, args.severity_threshold)
    
    # Generate markdown report
    report = generate_markdown_report(issues, args.plan_path, plan_data if args.include_plan_summary else None)
    
    # Write the report to the output file
    with open(args.output, 'w') as f:
        f.write(report)
    
    # Get highest severity for GitHub output
    highest_severity = get_highest_severity(issues)
    
    # Set GitHub step outputs
    print(f"::set-output name=has_issues::{len(issues) > 0}")
    print(f"::set-output name=issue_count::{len(issues)}")
    print(f"::set-output name=highest_severity::{highest_severity}")
    
    # Determine exit code based on severity threshold
    fail_level = Severity.from_string(args.fail_level)
    highest_found = Severity.from_string(highest_severity)
    
    if highest_found.value >= fail_level.value and len(issues) > 0:
        print(f"Security issues found at or above {args.fail_level} severity level. See the report for details.")
        sys.exit(1)
    
    print(f"Analysis complete. Report written to {args.output}")
    sys.exit(0)

if __name__ == "__main__":
    main()