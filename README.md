# Terraform Plan Analyzer

A GitHub Action that analyzes Terraform plans for security and safety risks using Google's Gemini AI.

## Overview

This action examines your Terraform plan JSON output to identify potential security concerns, including:

- Exposed credentials or secrets
- Public access to sensitive resources
- Missing encryption
- Overly permissive IAM roles or security groups
- Resource configurations that don't follow security best practices
- Potential for data loss or unintended destruction of resources

The analysis is performed using Google's Gemini AI model, which evaluates the plan changes and provides structured feedback on security risks with appropriate severity levels.

## Features

- 🔒 Analyzes Terraform plans for security risks
- 🛡️ Provides severity-based categorization (Low, Medium, High, Critical)
- 📊 Generates markdown reports for PRs
- 📑 Creates simplified plan summaries for easier PR reviews
- 🚫 Can fail workflows when severe issues are detected
- 💬 Posts analysis results as PR comments automatically
- ⚙️ Configurable severity thresholds for reporting and failing
- ☁️ Support for pulling plans directly from Terraform Cloud/Enterprise

## Usage

### Prerequisites

1. Generate a JSON-formatted Terraform plan by running:
   ```bash
   terraform plan -out=tf.plan
   terraform show -json tf.plan > tf.plan.json
   ```
   OR configure the action to pull a plan directly from Terraform Cloud/Enterprise

2. Get a Google Gemini API key from [Google AI Studio](https://ai.google.dev/)

### Basic Example with Local Plan

```yaml
name: Terraform Security Analysis

on:
  pull_request:
    branches: [ main ]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        
      - name: Terraform Init
        run: terraform init
      
      - name: Terraform Plan
        run: |
          terraform plan -out=tf.plan
          terraform show -json tf.plan > tf.plan.json
      
      - name: Analyze Terraform Plan
        uses: HappyPathway/tf-plan-analyzer@v1
        with:
          plan_path: tf.plan.json
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

### Example with Terraform Cloud/Enterprise

```yaml
name: Terraform Cloud Security Analysis

on:
  pull_request:
    branches: [ main ]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Analyze Terraform Plan from Terraform Cloud
        uses: HappyPathway/tf-plan-analyzer@v1
        with:
          tfc_enabled: 'true'
          tfc_token: ${{ secrets.TFC_TOKEN }}
          tfc_organization: 'your-organization'
          tfc_workspace: 'your-workspace'
          # Optional: specific run ID
          # tfc_run_id: 'run-abc123'
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Using with Terraform Cloud/Enterprise Speculative Plans

When working with pull requests and Terraform Cloud/Enterprise, speculative plans are automatically generated when a PR is created on a branch that's configured in your workspace. To ensure the analyzer examines the correct speculative plan for your PR, you can use the PR number or branch parameters:

```yaml
name: Analyze Terraform Plan from PR
on:
  pull_request:
    branches: [ main ]
    paths:
      - '**.tf'

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Analyze Terraform Plan from PR
        uses: HappyPathway/tf-plan-analyzer@v1
        with:
          tfc_enabled: 'true'
          tfc_token: ${{ secrets.TFC_TOKEN }}
          tfc_organization: 'your-organization'
          tfc_workspace: 'your-workspace'
          # Use the PR number to find the corresponding speculative plan
          tfc_pr_number: ${{ github.event.pull_request.number }}
          # For workspaces that take longer to plan, increase the wait time (default: 15)
          tfc_max_wait_minutes: '30'
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          issue_severity_threshold: 'medium'
          fail_on_severity: 'high'
```

This workflow will:
1. Be triggered whenever a PR that modifies `.tf` files is opened or updated
2. Find the speculative plan in Terraform Cloud/Enterprise that corresponds to the PR
3. Wait up to 30 minutes for the plan to complete (configurable with `tfc_max_wait_minutes`)
4. Analyze that plan for security issues
5. Post the results as a comment on the PR

For complex repository structures where you're not sure which TFC workspace will be triggered, you can specify the branch name instead:

```yaml
# Example using branch name instead of PR number
- name: Analyze Terraform Plan
  uses: HappyPathway/tf-plan-analyzer@v1
  with:
    tfc_enabled: 'true'
    tfc_token: ${{ secrets.TFC_TOKEN }}
    tfc_organization: 'your-organization'
    tfc_workspace: 'your-workspace'
    # Use the branch name to find the corresponding speculative plan
    tfc_branch: ${{ github.head_ref }}
    tfc_max_wait_minutes: '45'  # Longer wait for complex infrastructure
    gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input                   | Description                                                       | Required | Default           |
|-------------------------|-------------------------------------------------------------------|----------|-------------------|
| `plan_path`             | Path to the Terraform plan JSON file (not required if using TFC/TFE) | No\*     | -                 |
| `gemini_api_key`        | Google Gemini API key                                            | Yes      | -                 |
| `github_token`          | GitHub token for creating PR comments with results                | Yes      | -                 |
| `issue_severity_threshold` | Minimum severity level to include in the report                | No       | medium            |
| `fail_on_severity`      | The action will fail if issues at or above this severity are found| No       | high              |
| `include_plan_summary`  | Include a simplified plan summary in the report                   | No       | true              |
| `tfc_enabled`           | Enable pulling plan from Terraform Cloud/Enterprise               | No       | false             |
| `tfc_token`             | API token for Terraform Cloud/Enterprise                          | No\*\*   | -                 |
| `tfc_host`              | Hostname for Terraform Cloud/Enterprise instance                  | No       | app.terraform.io  |
| `tfc_organization`      | Organization name in Terraform Cloud/Enterprise                   | No\*\*   | -                 |
| `tfc_workspace`         | Workspace name in Terraform Cloud/Enterprise                      | No\*\*   | -                 |
| `tfc_run_id`            | Specific run ID to pull plan from (if not specified, uses latest) | No       | -                 |
| `tfc_max_wait_minutes`  | Maximum wait time in minutes for the plan to complete             | No       | 15                |

\* Required if `tfc_enabled` is false  
\*\* Required if `tfc_enabled` is true

## Outputs

| Output              | Description                                             |
|---------------------|---------------------------------------------------------|
| `has_issues`        | True if security issues were found above the threshold   |
| `issue_count`       | Number of security issues found                         |
| `highest_severity`  | Highest severity level found (low, medium, high, critical) |

## Example Analysis in PR Comment

The action generates a detailed security analysis as a PR comment that looks like this:

```markdown
## 🛡️ Terraform Plan Security Analysis
# Terraform Plan Analysis
Plan file: `tf.plan.json`
Generated: Thu Mar 21 10:38:42 PDT 2025

## Plan Summary

| Operation | Count |
|-----------|-------|
| Create | 2 |
| Update/Replace | 1 |
| Delete | 0 |

### Resources to Create

- `aws_s3_bucket.data_bucket`
- `aws_iam_role.lambda_role`

### Resources to Update/Replace

- `aws_security_group.web_sg` (update)

## Security Findings Summary

Total issues found: 2

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 0 |

## Detailed Findings

### Issue 1: HIGH - aws_s3_bucket.data_bucket

**Description**: The S3 bucket is configured with public read access.

**Potential Impact**: Unauthorized users can access potentially sensitive data stored in the bucket.

**Recommendation**: Set `acl` to `private` instead of `public-read` and implement more granular access controls using IAM policies.

---

### Issue 2: MEDIUM - aws_security_group.web_sg

**Description**: Security group allows inbound access from any IP address (0.0.0.0/0) to port 22 (SSH).

**Potential Impact**: Exposing SSH to the internet increases the attack surface and risk of brute force attacks.

**Recommendation**: Restrict SSH access to specific trusted IP ranges or implement a bastion host architecture.

---
*Generated by the [Terraform Plan Analyzer](https://github.com/HappyPathway/tf-plan-analyzer) Action*
```

## Testing the Action

This repository includes two GitHub Actions workflows that demonstrate how to test and use this action:

1. **Manual Testing Workflow** (`.github/workflows/test-action.yml`):  
   This workflow can be triggered manually from the Actions tab and allows you to choose between testing with a local Terraform plan or pulling from Terraform Cloud.

2. **PR Analysis Workflow** (`.github/workflows/pr-analysis.yml`):  
   This workflow automatically runs when a PR includes changes to Terraform files and posts the analysis as a PR comment.

### Prerequisites for Testing

To test this action in your own repository, you'll need to set up the following secrets:

- `GEMINI_API_KEY`: Your Google Gemini API key
- For Terraform Cloud testing:
  - `TFC_TOKEN`: Your Terraform Cloud/Enterprise API token
  - `TFC_ORG`: Your Terraform Cloud/Enterprise organization name
  - `TFC_WORKSPACE`: The workspace name where you want to pull plans from

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.