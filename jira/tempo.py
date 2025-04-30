#!/usr/bin/env -S uv run --script

# /// script
# dependencies = [
#   "requests",
#   "pandas",
#   "argparse",
#   "python-dotenv",
# ]
# ///

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor

import requests
import argparse
import pandas as pd
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("tempo")

# Enable debug logging if DEBUG env var is set
if os.getenv("DEBUG"):
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug logging enabled via DEBUG environment variable")

# Base URL for Jira API
BASE_URL = "https://jira.visma.com"

class JiraTempoClient:
    """Client for interacting with Jira Tempo API."""
    
    def __init__(self, base_url: str, token: str):
        """
        Initialize the Jira Tempo client.
        
        Args:
            base_url: Base URL for the Jira API
            token: Authentication token for API access
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                     data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the Jira Tempo API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters for the request
            data: JSON body data for the request
            
        Returns:
            Parsed JSON response from the API
            
        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making {method} request to {url}")
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, params=params, json=data)
            elif method.upper() == "PUT":
                response = self.session.put(url, params=params, json=data)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return {}
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            raise

    # Specific endpoint methods
    
    def get_myself(self) -> Dict[str, Any]:
        """
        Get information about the current user.
        
        Returns:
            Dict containing user information including key, name, email, etc.
            
        Example response:
        {
            "self": "https://jira.visma.com/rest/api/2/user?username=lukas.vavrek",
            "key": "JIRAUSER50417",
            "name": "lukas.vavrek",
            "emailAddress": "lukas.vavrek@visma.com",
            "displayName": "Lukáš Vavrek",
            ...
        }
        """
        endpoint = "rest/api/2/myself"
        return self._make_request("GET", endpoint)
        
    def get_teams(self) -> List[Dict[str, Any]]:
        """
        Get information about teams the current user belongs to.
        
        Returns:
            List of dicts containing team information including id, name, lead, etc.
            
        Example response:
        [
            {
                "id": 591,
                "name": "Flyt Social",
                "lead": "JIRAUSER50417",
                "leadUser": {
                    "name": "lukas.vavrek",
                    "key": "JIRAUSER50417",
                    "displayname": "Lukáš Vavrek"
                },
                ...
            },
            ...
        ]
        """
        endpoint = "rest/tempo-teams/2/team/"
        
        # Use multiple expand parameters properly as separate query parameters
        # The API expects: ?expand=leaduser&expand=teamprogram
        # Not: ?expand=teamprogram,leaduser
        params = [
            ("expand", "leaduser"),
            ("expand", "teamprogram")
        ]
        
        # Make the request and convert params list to proper query parameters
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making GET request to {url} with params {params}")
        
        try:
            # Need to handle params manually to support multiple parameters with the same name
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return []
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            raise
            
    def get_team_members(self, team_id: int) -> List[Dict[str, Any]]:
        """
        Get members of a specific team by team ID.
        
        Args:
            team_id: The ID of the team to fetch members for
            
        Returns:
            List of dicts containing team member information
            
        Example response:
        [
            {
                "id": 5699,
                "member": {
                    "teamMemberId": 5699,
                    "name": "arminas.bekampis",
                    "type": "USER",
                    "key": "JIRAUSER57951",
                    "displayname": "Arminas Bekampis",
                    ...
                },
                "membership": {
                    "id": 5795,
                    "role": {
                        "id": 1,
                        "name": "Member",
                        "default": true
                    },
                    "availability": "100",
                    "status": "active",
                    ...
                },
                ...
            },
            ...
        ]
        """
        endpoint = f"rest/tempo-teams/2/team/{team_id}/member"
        
        # Make the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making GET request to {url}")
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return []
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            raise
    
    def get_timesheet_approvals(self, team_id: int, period_start_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get timesheet approval information for a team.
        
        Args:
            team_id: The ID of the team to fetch timesheet approvals for
            period_start_date: The start date of the period to fetch approvals for.
                               If None, defaults to the first day of the current month.
                               
        Returns:
            Dict containing timesheet approval information for the team
            
        Example response:
        {
            "team": {
                "id": 591,
                "name": "Flyt Social"
            },
            "period": {
                "dateFrom": "2025-04-01",
                "dateTo": "2025-04-30"
            },
            "approvals": [
                {
                    "user": {
                        "name": "marek.cigas",
                        "key": "JIRAUSER55035",
                        "displayName": "Marek Cigas"
                    },
                    "status": "waiting_for_approval",
                    "workedSeconds": 576000,
                    "submittedSeconds": 576000,
                    "requiredSeconds": 576000,
                    ...
                },
                ...
            ]
        }
        """
        # If no period start date provided, use the first day of the current month
        if period_start_date is None:
            today = date.today()
            period_start_date = date(today.year, today.month, 1)
        
        # Format date as YYYY-MM-DD
        formatted_date = period_start_date.strftime("%Y-%m-%d")
        
        endpoint = "rest/tempo-timesheets/4/timesheet-approval"
        params = {
            "teamId": team_id,
            "periodStartDate": formatted_date
        }
        
        # Make the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making GET request to {url} with params {params}")
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return {}
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            raise
    
    def search_worklogs(self, from_date: str, to_date: str, worker_keys: List[str]) -> List[Dict[str, Any]]:
        """
        Search for worklogs by date range and worker keys.
        
        Args:
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            worker_keys: List of worker keys (e.g., ["JIRAUSER93736"])
            
        Returns:
            List of worklog entries
            
        Example response:
        [
            {
                "timeSpent": "4h",
                "timeSpentSeconds": 14400,
                "comment": "Working on issue VFSOS-1867",
                "issue": {
                    "key": "VFSOS-1867",
                    "summary": "Add new payment to decision from submenuitem Payments"
                },
                "worker": "JIRAUSER93736",
                "started": "2025-04-01 08:00:00.000"
            },
            ...
        ]
        """
        endpoint = "rest/tempo-timesheets/4/worklogs/search"
        
        # Prepare request body
        data = {
            "from": from_date,
            "to": to_date,
            "worker": worker_keys
        }
        
        # Make the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making POST request to {url} with data {data}")
        
        try:
            response = self.session.post(url, json=data)
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return []
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            raise
    
    def summarize_worklogs_by_issue(self, worklogs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Summarize worklog data by issue.
        
        Args:
            worklogs: List of worklog entries from search_worklogs
            
        Returns:
            Dictionary with issue keys as keys and summary information as values
        """
        summary = {}
        
        for worklog in worklogs:
            issue = worklog.get('issue', {})
            issue_key = issue.get('key', 'No Issue')
            issue_summary = issue.get('summary', 'No Summary')
            time_spent_seconds = worklog.get('timeSpentSeconds', 0)
            
            if issue_key not in summary:
                summary[issue_key] = {
                    'key': issue_key,
                    'summary': issue_summary,
                    'total_seconds': 0,
                    'total_hours': 0,
                    'total_days': 0,
                    'worklog_count': 0,
                    'dates': set()
                }
            
            # Update total time
            summary[issue_key]['total_seconds'] += time_spent_seconds
            summary[issue_key]['total_hours'] = summary[issue_key]['total_seconds'] / 3600
            summary[issue_key]['total_days'] = summary[issue_key]['total_hours'] / 8  # Assuming 8-hour workday
            summary[issue_key]['worklog_count'] += 1
            
            # Track unique dates
            if 'started' in worklog:
                started_date = worklog['started'].split()[0]  # Extract YYYY-MM-DD part
                summary[issue_key]['dates'].add(started_date)
        
        # Convert sets to counts of unique days for easier display
        for issue_key in summary:
            summary[issue_key]['unique_days'] = len(summary[issue_key]['dates'])
            del summary[issue_key]['dates']  # Remove the set as it's not needed anymore
        
        return summary


def parse_args():
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Track TEMPO timesheets via Jira API")
    
    # Add arguments
    parser.add_argument("--whoami", action="store_true", help="Show current user information")
    parser.add_argument("--teams", action="store_true", help="List all teams you belong to")
    parser.add_argument("--team-members", type=int, metavar="TEAM_ID", help="List members of a specific team by ID")
    
    # Add timesheet approvals command
    parser.add_argument("--approvals", type=int, metavar="TEAM_ID", help="Show timesheet approvals for a team")
    parser.add_argument("--period-start", type=str, metavar="YYYY-MM-DD", 
                       help="Start date for approval period (default: first day of current month)")
    parser.add_argument("--status", type=str, nargs="+", choices=["waiting_for_approval", "open", "approved"],
                       help="Filter by specific status(es). Can specify multiple values.")
    parser.add_argument("--simple", action="store_true", help="Use simplified display format (hide user keys)")
    parser.add_argument("--show-vacation", action="store_true", help="Show vacation days taken (ADM-65)")
    
    # Add worklog summary command
    parser.add_argument("--worklogs", type=str, metavar="USER_KEY", help="Show worklog summary for a specific user")
    parser.add_argument("--from-date", type=str, metavar="YYYY-MM-DD", 
                       help="Start date for worklog period (default: first day of current month)")
    parser.add_argument("--to-date", type=str, metavar="YYYY-MM-DD", 
                       help="End date for worklog period (default: last day of current month)")
    
    return parser.parse_args()


def main():
    """
    Main entry point for the script.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    # Get token from environment variable
    token = os.getenv("JIRA_TOKEN")
    if not token:
        logger.error("Please set JIRA_TOKEN environment variable")
        sys.exit(1)
    
    # Parse command line arguments
    args = parse_args()
    
    # Initialize the Jira Tempo client
    client = JiraTempoClient(BASE_URL, token)
    
    # Execute requested operation
    if args.whoami:
        try:
            user_info = client.get_myself()
            print("\nUser Information:")
            print(f"Key:          {user_info.get('key', 'N/A')}")
            print(f"Name:         {user_info.get('name', 'N/A')}")
            print(f"Email:        {user_info.get('emailAddress', 'N/A')}")
            print(f"Display Name: {user_info.get('displayName', 'N/A')}")
        except Exception as e:
            logger.error(f"Failed to retrieve user information: {e}")
            sys.exit(1)
    elif args.teams:
        try:
            # Get current user info to identify teams where user is lead
            user_info = client.get_myself()
            current_user_key = user_info.get('key')
            
            # Get teams
            teams = client.get_teams()
            
            # Debug: log a sample team to verify the structure
            if teams and len(teams) > 0:
                logger.debug(f"Sample team structure: {json.dumps(teams[0], indent=2)}")
            
            if not teams:
                print("\nYou don't belong to any teams.")
            else:
                print("\nYour Teams:")
                print("-" * 80)
                print(f"{'ID':^8} | {'Name':<30} | {'Leader':<25} | {'You are leader':^15}")
                print("-" * 80)
                
                for team in teams:
                    team_id = team.get('id', 'N/A')
                    team_name = team.get('name', 'N/A')
                    
                    # Get leader information
                    lead_user = team.get('leadUser', {})
                    
                    # The key is 'displayname' (lowercase) in the JSON response
                    lead_name = lead_user.get('displayname', lead_user.get('name', 'N/A'))
                    logger.debug(f"Team: {team_name}, Lead user: {lead_user}, Lead name: {lead_name}")
                    
                    # Get leader's key
                    lead_key = lead_user.get('key')
                    
                    # Check if current user is the lead by comparing keys
                    is_lead = lead_key and lead_key == current_user_key
                    lead_marker = "✓" if is_lead else ""
                    
                    print(f"{team_id:^8} | {team_name:<30} | {lead_name:<25} | {lead_marker:^15}")
            
        except Exception as e:
            logger.error(f"Failed to retrieve teams information: {e}")
            sys.exit(1)
    elif args.team_members is not None:
        try:
            team_id = args.team_members
            
            # Get team members
            members = client.get_team_members(team_id)
            
            if not members:
                print(f"\nNo members found for team ID {team_id}")
            else:
                print(f"\nMembers of Team ID {team_id}:")
                print("-" * 80)
                print(f"{'ID':^8} | {'Name':<25} | {'Username':<20} | {'Role':<15} | {'Status':<10}")
                print("-" * 80)
                
                for member in members:
                    # Extract member information with proper fallbacks
                    member_info = member.get('member', {})
                    membership = member.get('membership', {})
                    
                    member_id = member.get('id', 'N/A')
                    display_name = member_info.get('displayname', member_info.get('name', 'N/A'))
                    username = member_info.get('name', 'N/A')
                    
                    # Get role and status information
                    role = membership.get('role', {})
                    role_name = role.get('name', 'N/A')
                    status = membership.get('status', 'N/A')
                    
                    print(f"{member_id:^8} | {display_name:<25} | {username:<20} | {role_name:<15} | {status:<10}")
                
        except Exception as e:
            logger.error(f"Failed to retrieve team members: {e}")
            sys.exit(1)
    elif args.approvals is not None:
        try:
            team_id = args.approvals
            
            # Parse period start date if provided
            period_start_date = None
            if args.period_start:
                try:
                    year, month, day = map(int, args.period_start.split('-'))
                    period_start_date = date(year, month, day)
                except ValueError:
                    logger.error(f"Invalid date format: {args.period_start}. Use YYYY-MM-DD.")
                    sys.exit(1)
            
            # Get timesheet approvals
            approval_data = client.get_timesheet_approvals(team_id, period_start_date)
            
            if not approval_data or 'approvals' not in approval_data or not approval_data['approvals']:
                print(f"\nNo approval data found for team ID {team_id}")
            else:
                # Get period info
                period = approval_data.get('period', {})
                date_from = period.get('dateFrom', 'N/A')
                date_to = period.get('dateTo', 'N/A')
                
                # Get team info
                team = approval_data.get('team', {})
                team_name = team.get('name', f"Team {team_id}")
                
                # Fetch vacation data if requested
                vacation_data = {}
                if args.show_vacation:
                    period = approval_data.get('period', {})
                    from_date = period.get('dateFrom')
                    to_date = period.get('dateTo')
                    
                    if from_date and to_date:
                        for approval in approval_data['approvals']:
                            user = approval.get('user', {})
                            user_key = user.get('key')
                            
                            if user_key:
                                try:
                                    # Search worklogs for ADM-65 (vacation) entries
                                    worklogs = client.search_worklogs(from_date, to_date, [user_key])
                                    vacation_hours = 0
                                    vacation_days = 0
                                    
                                    for worklog in worklogs:
                                        issue = worklog.get('issue', {})
                                        if issue.get('key') == 'ADM-65':
                                            # Sum up vacation hours
                                            vacation_hours += worklog.get('timeSpentSeconds', 0) / 3600
                                    
                                    # Calculate days (assuming 8-hour workday)
                                    vacation_days = vacation_hours / 8
                                    
                                    # Store vacation data
                                    vacation_data[user_key] = {
                                        'hours': vacation_hours,
                                        'days': vacation_days
                                    }
                                except Exception as e:
                                    logger.warning(f"Could not fetch vacation data for {user_key}: {e}")
                
                # Print header
                print(f"\nTimesheet Approvals for {team_name} ({date_from} to {date_to}):")
                
                # Determine what columns to show
                if args.simple:
                    # Simple mode (no user keys)
                    if args.show_vacation:
                        # With vacation data
                        print("-" * 140)
                        print(f"{'Name':<25} | {'Status':<20} | {'Completion':^15} | {'Worked (h)':^12} | {'Required (h)':^12} | {'Submitted (h)':^12} | {'Vacation (d)':^12} | {'Vacation (h)':^12}")
                        print("-" * 140)
                    else:
                        # Without vacation data
                        print("-" * 100)
                        print(f"{'Name':<25} | {'Status':<20} | {'Completion':^15} | {'Worked (h)':^12} | {'Required (h)':^12} | {'Submitted (h)':^12}")
                        print("-" * 100)
                else:
                    # Full mode (with user keys)
                    if args.show_vacation:
                        # With vacation data
                        print("-" * 160)
                        print(f"{'Name':<25} | {'User Key':<20} | {'Status':<20} | {'Completion':^15} | {'Worked (h)':^12} | {'Required (h)':^12} | {'Submitted (h)':^12} | {'Vacation (d)':^12} | {'Vacation (h)':^12}")
                        print("-" * 160)
                    else:
                        # Without vacation data
                        print("-" * 130)
                        print(f"{'Name':<25} | {'User Key':<20} | {'Status':<20} | {'Completion':^15} | {'Worked (h)':^12} | {'Required (h)':^12} | {'Submitted (h)':^12}")
                        print("-" * 130)
                
                # Count totals for the summary
                total_members = 0
                total_worked_hours = 0
                total_required_hours = 0
                total_submitted_hours = 0
                filtered_count = 0
                
                # Calculate and display completion percentages for each user
                for approval in approval_data['approvals']:
                    user = approval.get('user', {})
                    display_name = user.get('displayName', user.get('name', 'N/A'))
                    user_key = user.get('key', 'N/A')
                    
                    status = approval.get('status', 'N/A')
                    worked_seconds = approval.get('workedSeconds', 0)
                    required_seconds = approval.get('requiredSeconds', 0) 
                    submitted_seconds = approval.get('submittedSeconds', 0)
                    
                    # Apply status filter if specified
                    if args.status and status not in args.status:
                        # Count in totals but skip display
                        filtered_count += 1
                        total_members += 1
                        total_worked_hours += worked_seconds / 3600
                        total_required_hours += required_seconds / 3600
                        total_submitted_hours += submitted_seconds / 3600
                        continue
                    
                    # Count in totals
                    total_members += 1
                    total_worked_hours += worked_seconds / 3600
                    total_required_hours += required_seconds / 3600
                    total_submitted_hours += submitted_seconds / 3600
                    
                    # Convert seconds to hours (for display purposes)
                    worked_hours = worked_seconds / 3600
                    required_hours = required_seconds / 3600
                    submitted_hours = submitted_seconds / 3600
                    
                    # Calculate completion percentage
                    completion_pct = 0
                    if required_seconds > 0:
                        completion_pct = (worked_seconds / required_seconds) * 100
                    
                    # Colorize status for better readability
                    status_display = status.replace('_', ' ').title()
                    
                    # Format all numeric values with right alignment within their columns
                    # This ensures decimal points align while maintaining column appearance
                    completion_str = f"{completion_pct:6.1f}%"
                    worked_str = f"{worked_hours:6.1f}"
                    required_str = f"{required_hours:6.1f}"
                    submitted_str = f"{submitted_hours:6.1f}"
                    
                    # Get vacation data if available
                    vacation_hours = 0
                    vacation_days = 0
                    if args.show_vacation and user_key in vacation_data:
                        vacation_hours = vacation_data[user_key]['hours']
                        vacation_days = vacation_data[user_key]['days']
                    
                    # Format with proper alignment
                    vacation_hours_str = f"{vacation_hours:6.1f}"
                    vacation_days_str = f"{vacation_days:6.1f}"
                    
                    # Choose output format based on options
                    if args.simple:
                        # Simple mode (no user keys)
                        if args.show_vacation:
                            # With vacation data
                            print(f"{display_name:<25} | {status_display:<20} | {completion_str:^15} | {worked_str:^12} | {required_str:^12} | {submitted_str:^12} | {vacation_days_str:^12} | {vacation_hours_str:^12}")
                        else:
                            # Without vacation data
                            print(f"{display_name:<25} | {status_display:<20} | {completion_str:^15} | {worked_str:^12} | {required_str:^12} | {submitted_str:^12}")
                    else:
                        # Full mode (with user keys)
                        if args.show_vacation:
                            # With vacation data
                            print(f"{display_name:<25} | {user_key:<20} | {status_display:<20} | {completion_str:^15} | {worked_str:^12} | {required_str:^12} | {submitted_str:^12} | {vacation_days_str:^12} | {vacation_hours_str:^12}")
                        else:
                            # Without vacation data
                            print(f"{display_name:<25} | {user_key:<20} | {status_display:<20} | {completion_str:^15} | {worked_str:^12} | {required_str:^12} | {submitted_str:^12}")
                
                # Display summary information if there were any filtered results
                if filtered_count > 0 or args.status:
                    print("-" * 100)
                    total_completion = 0
                    if total_required_hours > 0:
                        total_completion = (total_worked_hours / total_required_hours) * 100
                    
                    # Format numerical values for consistent alignment
                    total_completion_str = f"{total_completion:6.1f}%"
                    total_worked_str = f"{total_worked_hours:6.1f}"
                    total_required_str = f"{total_required_hours:6.1f}"
                    total_submitted_str = f"{total_submitted_hours:6.1f}"
                    
                    # Format summary line based on display mode
                    if args.simple:
                        # Simple mode (no user keys)
                        if args.show_vacation:
                            # With vacation data
                            print(f"{'SUMMARY':<25} | {f'Showing {total_members-filtered_count} of {total_members}':<20} | {total_completion_str:^15} | {total_worked_str:^12} | {total_required_str:^12} | {total_submitted_str:^12} | {' ':^12} | {' ':^12}")
                        else:
                            # Simple mode without vacation
                            print(f"{'SUMMARY':<25} | {f'Showing {total_members-filtered_count} of {total_members}':<20} | {total_completion_str:^15} | {total_worked_str:^12} | {total_required_str:^12} | {total_submitted_str:^12}")
                    else:
                        if args.show_vacation:
                            # Full mode with vacation
                            print(f"{'SUMMARY':<25} | {'-':<20} | {f'Showing {total_members-filtered_count} of {total_members}':<20} | {total_completion_str:^15} | {total_worked_str:^12} | {total_required_str:^12} | {total_submitted_str:^12} | {' ':^12} | {' ':^12}")
                        else:
                            # Full mode without vacation
                            print(f"{'SUMMARY':<25} | {'-':<20} | {f'Showing {total_members-filtered_count} of {total_members}':<20} | {total_completion_str:^15} | {total_worked_str:^12} | {total_required_str:^12} | {total_submitted_str:^12}")
                    
                    if args.status:
                        status_list = ', '.join(args.status)
                        print(f"\nFiltered by status: {status_list}")
                
        except Exception as e:
            logger.error(f"Failed to retrieve timesheet approvals: {e}")
            sys.exit(1)
    elif args.worklogs is not None:
        try:
            # Parse date range
            from_date = args.from_date
            to_date = args.to_date
            
            # If dates not specified, use current month for from_date
            if not from_date:
                today = date.today()
                first_day = date(today.year, today.month, 1)
                from_date = first_day.strftime("%Y-%m-%d")
                
            # If to_date not specified, calculate last day of the month based on from_date
            if not to_date:
                # Parse from_date
                from_year, from_month, from_day = map(int, from_date.split('-'))
                
                # Calculate last day of the from_date's month
                if from_month == 12:
                    last_day = date(from_year + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day = date(from_year, from_month + 1, 1) - timedelta(days=1)
                    
                to_date = last_day.strftime("%Y-%m-%d")
            
            # Get worklog data
            worklogs = client.search_worklogs(from_date, to_date, [args.worklogs])
            
            if not worklogs:
                print(f"\nNo worklog data found for user {args.worklogs} in the period {from_date} to {to_date}")
            else:
                # Get summary by issue
                issue_summary = client.summarize_worklogs_by_issue(worklogs)
                
                # Display summary
                print(f"\nWorklog Summary for {args.worklogs} ({from_date} to {to_date}):")
                print("-" * 120)
                print(f"{'Issue Key':<12} | {'Summary':<50} | {'Hours':^8} | {'Days':^8} | {'Unique Days':^12} | {'Entries':^8}")
                print("-" * 120)
                
                # Sort issues by most hours spent
                sorted_issues = sorted(issue_summary.values(), key=lambda x: x['total_hours'], reverse=True)
                
                total_hours = 0
                total_days = 0
                for issue in sorted_issues:
                    # Track totals
                    total_hours += issue['total_hours']
                    total_days += issue['total_days']
                    
                    # Format values
                    hours_str = f"{issue['total_hours']:6.1f}"
                    days_str = f"{issue['total_days']:6.1f}"
                    unique_days_str = f"{issue['unique_days']:^12}"
                    entries_str = f"{issue['worklog_count']:^8}"
                    
                    # Truncate summary if too long
                    summary = issue['summary']
                    if len(summary) > 47:
                        summary = summary[:44] + "..."
                    
                    print(f"{issue['key']:<12} | {summary:<50} | {hours_str:^8} | {days_str:^8} | {unique_days_str} | {entries_str}")
                
                # Print totals
                print("-" * 120)
                total_hours_str = f"{total_hours:6.1f}"
                total_days_str = f"{total_days:6.1f}"
                print(f"{'TOTAL':<12} | {'All Issues':<50} | {total_hours_str:^8} | {total_days_str:^8} | {' ':^12} | {len(worklogs):^8}")
                
        except Exception as e:
            logger.error(f"Failed to retrieve worklog data: {e}")
            sys.exit(1)
    else:
        # If no operation specified, show help
        if len(sys.argv) == 1:
            parse_args().__class__.print_help()
    

if __name__ == "__main__":
    main()
