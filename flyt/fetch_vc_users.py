#!/usr/bin/python3

import vc_common as vc
import argparse

DEBUG = 1


def main():
    parser = argparse.ArgumentParser(description='Utility for fetching users from Visma Connect')

    parser.add_argument('-T', '--token', action='store_true', help='Access token')
    parser.add_argument('-s', '--scope', nargs='+', help='List of scopes to authorize for')

    parser.add_argument('-d', '--domains', nargs='+', help='A list of domains to process')
    parser.add_argument('-f', '--force', action='store_true', help='Force action without domains')
    parser.add_argument('-l', '--list', action='store_true', help='List users')
    parser.add_argument('-c', '--count', action='store_true', help='Count users')

    args = parser.parse_args()

    if args.token:
        if args.scope:
            print(vc.get_access_token(' '.join(args.scope)))
        else:
            print(vc.get_access_token())
        exit(0)

    if not args.domains:
        if args.force:
            fetch_paged_users(vc.get_access_token(), domain=None)
        else:
            print('No domains specified, this could be performance intensive. '
                  'Use --force if you want to do it anyway. Exiting.')
        exit(0)

    access_token = vc.get_access_token()

    if args.count:
        for domain in args.domains:
            try:
                users = vc.fetch_users(access_token, domain)

                print(f'{domain} total users: {users["total_users"]}')
            except Exception as e:
                print(f'{e}')

    if args.list:
        for domain in args.domains:
            try:
                fetch_paged_users(access_token, domain)
            except Exception as e:
                print(f'{e}')


def fetch_paged_users(access_token, domain, page=1):
    users = vc.fetch_users(access_token, domain)

    for user in users['users']:
        print(f'{user["email"]}')

    if users['total_pages'] > page:
        fetch_paged_users(access_token, domain, page + 1)


if __name__ == '__main__':
    main()
