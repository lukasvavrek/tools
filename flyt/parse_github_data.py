#!/usr/bin/env python

# https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests

import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
from collections import defaultdict
import os
from typing import List, Dict, Any, Generator, Optional
import logging
import argparse
import re
from urllib.parse import parse_qs, urlparse
import json
import hashlib
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class RateLimit:
    """Class to track GitHub API rate limit information."""
    remaining: int
    limit: int
    reset_time: datetime

    @classmethod
    def from_response(cls, response: requests.Response) -> 'RateLimit':
        return cls(
            remaining=int(response.headers.get('X-RateLimit-Remaining', 0)),
            limit=int(response.headers.get('X-RateLimit-Limit', 0)),
            reset_time=datetime.fromtimestamp(int(response.headers.get('X-RateLimit-Reset', 0)))
        )


class Cache:
    def __init__(self, cache_dir: str = '.github_cache', ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()

    def _get_cache_key(self, url: str, params: Dict) -> str:
        """Generate a unique cache key for the request."""
        content = f"{url}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, url: str, params: Dict) -> Optional[List]:
        """Retrieve data from cache if valid."""
        cache_key = self._get_cache_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        with self._lock:
            try:
                with cache_file.open() as f:
                    cached_data = json.load(f)

                cached_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cached_time > self.ttl:
                    return None

                return cached_data['data']
            except (json.JSONDecodeError, KeyError):
                return None

    def set(self, url: str, params: Dict, data: List):
        """Store data in cache."""
        cache_key = self._get_cache_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

        with self._lock:
            with cache_file.open('w') as f:
                json.dump(cache_data, f)


class GitHubTeamAnalyzer:
    def __init__(self, token: str, org: str, team_slug: str, repo: str,
                 verbose: bool = False, cache_ttl: int = 24, max_workers: int = 5):
        """
        Initialize the GitHub Team Analyzer.

        Args:
            token (str): GitHub Personal Access Token
            org (str): Organization name
            team_slug (str): Team identifier
            repo (str): Repository name
            verbose (bool): Enable verbose logging
            cache_ttl (int): Cache TTL in hours
            max_workers (int): Maximum number of parallel workers
        """
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = 'https://api.github.com'
        self.org = org
        self.team_slug = team_slug
        self.repo = repo
        self.max_workers = max_workers

        # Set up logging
        self.logger = logging.getLogger('GitHubAnalyzer')
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)

        # Initialize cache
        self.cache = Cache(ttl_hours=cache_ttl)

        # Rate limit tracking
        self.rate_limit = None
        self._rate_limit_lock = threading.Lock()

    def _update_rate_limit(self, response: requests.Response):
        """Update rate limit information from response."""
        with self._rate_limit_lock:
            self.rate_limit = RateLimit.from_response(response)
            remaining_percent = (self.rate_limit.remaining / self.rate_limit.limit) * 100

            if remaining_percent < 20:
                self.logger.warning(
                    f"Rate limit running low: {self.rate_limit.remaining}/{self.rate_limit.limit} "
                    f"requests remaining. Resets at {self.rate_limit.reset_time}"
                )

    def _wait_for_rate_limit(self):
        """Wait if rate limit is exceeded."""
        with self._rate_limit_lock:
            if self.rate_limit and self.rate_limit.remaining == 0:
                wait_time = (self.rate_limit.reset_time - datetime.now()).total_seconds()
                if wait_time > 0:
                    self.logger.warning(f"Rate limit exceeded. Waiting {wait_time:.0f} seconds...")
                    time.sleep(wait_time + 1)

    def _get_next_page_url(self, response: requests.Response) -> str:
        """Extract next page URL from Link header."""
        link_header = response.headers.get('Link')
        if not link_header:
            return None

        links = {}
        for link in link_header.split(', '):
            parts = link.split('; ')
            url = re.sub(r'[<>]', '', parts[0])
            rel = re.search(r'rel="(\w+)"', parts[1]).group(1)
            links[rel] = url

        return links.get('next')

    def _paginated_get(self, url: str, params: Dict = None) -> List[Dict]:
        """
        Make a paginated GET request to GitHub API with caching.

        Args:
            url (str): Base URL for the request
            params (dict): Query parameters

        Returns:
            List[Dict]: Complete list of items from all pages
        """
        # Check cache first
        cached_data = self.cache.get(url, params or {})
        if cached_data is not None:
            self.logger.debug(f"Cache hit for {url}")
            return cached_data

        self.logger.debug(f"Cache miss for {url}")
        all_data = []
        current_url = url
        current_params = params or {}
        page_num = 1

        while current_url:
            self._wait_for_rate_limit()

            self.logger.debug(f"Fetching page {page_num} from {current_url}")
            response = requests.get(
                current_url,
                headers=self.headers,
                params=current_params if current_url == url else None
            )
            response.raise_for_status()

            self._update_rate_limit(response)

            data = response.json()
            if not isinstance(data, list):
                all_data = [data]
                break

            all_data.extend(data)
            current_url = self._get_next_page_url(response)
            page_num += 1

        # Store in cache
        self.cache.set(url, params or {}, all_data)
        return all_data

    def get_team_members(self) -> List[Dict[str, Any]]:
        """Fetch all team members."""
        self.logger.debug(f"Fetching team members for {self.org}/{self.team_slug}")
        url = f"{self.base_url}/orgs/{self.org}/teams/{self.team_slug}/members"

        members = self._paginated_get(url)
        self.logger.info(f"Found {len(members)} team members")
        return members

    def _fetch_all_pr_data(self, days: int = 90) -> Dict[str, Any]:
        """
        Fetch all PR-related data upfront and build lookup tables.
        Uses updated date filtering and processes PRs in batches to handle large repositories.

        Returns:
            Dict containing PR data, reviews, and comments indexed by PR number
        """
        self.logger.info("Fetching all PR data upfront...")
        # Make cutoff_date timezone-aware
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        def is_pr_in_range(pr: Dict) -> bool:
            """Check if PR was updated within our date range."""
            # GitHub returns UTC timestamps, so we parse them as UTC
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', ''))
            updated_at = updated_at.replace(tzinfo=timezone.utc)
            return updated_at >= cutoff_date

        # Get PRs in batches, sorted by updated date
        prs_url = f"{self.base_url}/repos/{self.org}/{self.repo}/pulls"
        relevant_prs = []

        # First try to get from cache
        cached_data = self.cache.get(prs_url, {
            'state': 'all',
            'sort': 'updated',
            'direction': 'desc',
            'days': days
        })

        if cached_data is not None:
            self.logger.debug(f"Cache hit for PRs")
            relevant_prs = cached_data
        else:
            self.logger.debug(f"Cache miss for PRs")

            for state in ['closed', 'open']:
                page = 1
                while True:
                    self._wait_for_rate_limit()

                    self.logger.debug(f"Fetching {state} PRs page {page}")
                    response = requests.get(
                        prs_url,
                        headers=self.headers,
                        params={
                            'state': state,
                            'sort': 'updated',
                            'direction': 'desc',
                            'per_page': 100,
                            'page': page
                        }
                    )
                    response.raise_for_status()
                    self._update_rate_limit(response)

                    batch = response.json()
                    if not batch:
                        break

                    # Check if we've gone past our date range
                    oldest_pr = batch[-1]
                    oldest_date = datetime.fromisoformat(oldest_pr['updated_at'].replace('Z', ''))
                    oldest_date = oldest_date.replace(tzinfo=timezone.utc)

                    # Filter PRs in this batch
                    relevant_batch = [pr for pr in batch if is_pr_in_range(pr)]
                    relevant_prs.extend(relevant_batch)

                    # If the oldest PR in this batch is before our cutoff, we can stop
                    if oldest_date < cutoff_date:
                        break

                    page += 1

            # Cache the filtered PRs
            self.cache.set(prs_url, {
                'state': 'all',
                'sort': 'updated',
                'direction': 'desc',
                'days': days
            }, relevant_prs)

        self.logger.info(f"Found {len(relevant_prs)} relevant PRs")

        # Build lookup tables
        pr_data = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            def process_pr(pr):
                pr_number = pr['number']

                try:
                    # Get reviews
                    reviews_url = f"{self.base_url}/repos/{self.org}/{self.repo}/pulls/{pr_number}/reviews"
                    reviews = self._paginated_get(reviews_url)

                    # Get review comments (inline comments)
                    review_comments_url = f"{self.base_url}/repos/{self.org}/{self.repo}/pulls/{pr_number}/comments"
                    review_comments = self._paginated_get(review_comments_url)

                    # Get PR comments (discussions)
                    comments_url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues/{pr_number}/comments"
                    comments = self._paginated_get(comments_url)

                    return pr_number, {
                        'pr': pr,
                        'reviews': reviews,
                        'review_comments': review_comments,
                        'comments': comments
                    }
                except Exception as e:
                    self.logger.error(f"Error processing PR #{pr_number}: {str(e)}")
                    return None

            # Process PRs in parallel with chunking for better memory management
            chunk_size = 50
            for i in range(0, len(relevant_prs), chunk_size):
                chunk = relevant_prs[i:i + chunk_size]
                self.logger.debug(f"Processing PRs {i} to {i + len(chunk)}")

                future_to_pr = {executor.submit(process_pr, pr): pr for pr in chunk}

                for future in as_completed(future_to_pr):
                    result = future.result()
                    if result:
                        pr_number, data = result
                        pr_data[pr_number] = data

        self.logger.info("Completed fetching all PR data")
        return pr_data

    def generate_team_report(self, days: int = 90) -> pd.DataFrame:
        """Generate a comprehensive team report."""
        self.logger.info(f"Generating team report for the last {days} days")

        # Get all team members
        members = self.get_team_members()

        # Fetch all PR data upfront
        pr_data = self._fetch_all_pr_data(days)

        # Process member stats
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_member = {
                executor.submit(self.get_member_stats, member['login'], days, pr_data): member['login']
                for member in members
            }

            stats = []
            for future in as_completed(future_to_member):
                username = future_to_member[future]
                try:
                    stats.append(future.result())
                except Exception as e:
                    self.logger.error(f"Error processing stats for {username}: {str(e)}")

        return pd.DataFrame(stats)

    def get_member_stats(self, username: str, days: int = 90, pr_data: Dict = None) -> Dict[str, Any]:
        """
        Get statistics for a specific team member using pre-fetched PR data.
        """
        self.logger.debug(f"Processing stats for user: {username}")
        since = (datetime.now() - timedelta(days=days)).isoformat()

        # Get commits
        commits_url = f"{self.base_url}/repos/{self.org}/{self.repo}/commits"
        commits = self._paginated_get(commits_url, {'author': username, 'since': since})

        # Initialize counters
        created_prs = []
        review_stats = defaultdict(int)
        review_comments_count = 0
        pr_comments_count = 0

        # Process PR data from lookup
        for pr_number, data in pr_data.items():
            pr = data['pr']

            # Check if user created this PR
            if pr['user']['login'] == username:
                created_prs.append(pr)

            # Count user's reviews
            for review in data['reviews']:
                if review['user']['login'] == username:
                    review_stats[review['state']] += 1

            # Count review comments
            review_comments_count += len([
                c for c in data['review_comments']
                if c['user']['login'] == username
            ])

            # Count PR comments
            pr_comments_count += len([
                c for c in data['comments']
                if c['user']['login'] == username
            ])

        total_comments = review_comments_count + pr_comments_count
        total_reviews = sum(review_stats.values())

        # Calculate contribution score
        contribution_score = (
                len(commits) * 1 +  # 1 point per commit
                len(created_prs) * 3 +  # 3 points per PR created
                review_stats['APPROVED'] * 2 +  # 2 points per approval
                review_stats['CHANGES_REQUESTED'] * 2 +  # 2 points per review requesting changes
                review_stats['COMMENTED'] * 1 +  # 1 point per review comment
                total_comments * 1  # 1 point per comment
        )

        return {
            'username': username,
            'commit_count': len(commits),
            'pr_count': len(created_prs),
            'reviews_given': total_reviews,
            'reviews_approved': review_stats['APPROVED'],
            'reviews_changes_requested': review_stats['CHANGES_REQUESTED'],
            'reviews_commented': review_stats['COMMENTED'],
            'review_comments': review_comments_count,
            'pr_comments': pr_comments_count,
            'total_comments': total_comments,
            'contribution_score': contribution_score
        }

    def get_rate_limit_info(self) -> str:
        """Get formatted rate limit information."""
        if not self.rate_limit:
            return "Rate limit information not available yet"

        reset_time = self.rate_limit.reset_time.strftime('%Y-%m-%d %H:%M:%S')
        return (f"API Rate Limit: {self.rate_limit.remaining}/{self.rate_limit.limit} "
                f"requests remaining (Resets at {reset_time})")


def main():
    parser = argparse.ArgumentParser(description='Analyze GitHub team statistics')
    parser.add_argument('--org', required=True, help='GitHub organization name')
    parser.add_argument('--team', required=True, help='Team slug')
    parser.add_argument('--repo', required=True, help='Repository name')
    parser.add_argument('--days', type=int, default=90, help='Number of days to analyze')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--cache-ttl', type=int, default=24, help='Cache TTL in hours')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers')
    parser.add_argument('--no-cache', action='store_true', help='Disable caching')
    args = parser.parse_args()

    token = os.getenv('GITHUB_TOKEN')
    if not token:
        raise ValueError("Please set GITHUB_TOKEN environment variable")

    # Initialize analyzer
    analyzer = GitHubTeamAnalyzer(
        token=token,
        org=args.org,
        team_slug=args.team,
        repo=args.repo,
        verbose=args.verbose,
        cache_ttl=0 if args.no_cache else args.cache_ttl,
        max_workers=args.workers
    )

    # Generate report
    print("\nStarting analysis...")
    start_time = time.time()

    df = analyzer.generate_team_report(days=args.days)
    df_sorted = df.sort_values('contribution_score', ascending=False)

    end_time = time.time()

    # Print report
    print("\nTeam Activity Report (Last 90 days)")
    print("=" * 50)
    print(df_sorted.to_string(index=False))

    print("\nTeam Summary:")
    print("=" * 50)
    print(f"Total Commits: {df['commit_count'].sum()}")
    print(f"Total PRs: {df['pr_count'].sum()}")
    print(f"Total Reviews: {df['reviews_given'].sum()}")
    print(f"Total Comments: {df['total_comments'].sum()}")
    print(f"Most Active Member: {df_sorted.iloc[0]['username']}")
    print(f"Average Reviews per Member: {df['reviews_given'].mean():.1f}")
    print(f"Average Comments per Member: {df['total_comments'].mean():.1f}")

    print("\nPerformance Statistics:")
    print("=" * 50)
    print(f"Analysis completed in {end_time - start_time:.2f} seconds")
    print(analyzer.get_rate_limit_info())


if __name__ == "__main__":
    main()