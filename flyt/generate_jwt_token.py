#!/usr/bin/env python

import argparse
import base64
from dataclasses import dataclass, field
import jwt
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DEBUG = 1


@dataclass
class TokenContext:
    secret: str

    @dataclass
    class Claims:
        exp: datetime = datetime.now(timezone.utc) + timedelta(days=1)

        def __init__(self):
            self.exp = datetime.now(timezone.utc) + timedelta(days=1)
            # Load all values from environment variables
            self.applicationId = os.getenv('JWT_APPLICATION_ID')
            self.applicationName = os.getenv('JWT_APPLICATION_NAME')
            self.applicationHostname = os.getenv('JWT_APPLICATION_HOSTNAME')
            self.orgId = os.getenv('JWT_ORG_ID')
            self.customerGuid = os.getenv('JWT_CUSTOMER_GUID')
            self.employeeId = os.getenv('JWT_EMPLOYEE_ID')
            self.employeeFullName = os.getenv('JWT_EMPLOYEE_FULL_NAME')
            self.employeeInitials = os.getenv('JWT_EMPLOYEE_INITIALS')
            self.employeeBirthNumber = os.getenv('JWT_EMPLOYEE_BIRTH_NUMBER')
            self.employeeRoleName = os.getenv('JWT_EMPLOYEE_ROLE_NAME')
            self.employeeRoleId = os.getenv('JWT_EMPLOYEE_ROLE_ID')
            self.positionId = os.getenv('JWT_POSITION_ID')
            self.orgUnits = os.getenv('JWT_ORG_UNITS')
            self.accessPoints = os.getenv('JWT_ACCESS_POINTS')
            self.employeeAffiliationsIds = os.getenv('JWT_EMPLOYEE_AFFILIATIONS_IDS')
            self.employeeGroupsIds = os.getenv('JWT_EMPLOYEE_GROUPS_IDS')
            self.employeeTeamsIds = os.getenv('JWT_EMPLOYEE_TEAMS_IDS')
            self.scope = os.getenv('JWT_SCOPE', '').split(',')

            # Validate that required environment variables are set
            required_vars = [
                'JWT_APPLICATION_ID',
                'JWT_APPLICATION_NAME',
                'JWT_APPLICATION_HOSTNAME',
                'JWT_ORG_ID',
                'JWT_CUSTOMER_GUID',
                'JWT_EMPLOYEE_ID',
                'JWT_SCOPE'
            ]

            missing_vars = [var for var in required_vars if not os.getenv(var)]
            if missing_vars:
                raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    claims: Claims = field(default_factory=Claims)


def main():
    parser = argparse.ArgumentParser(description='Utility for generating JWT tokens for Flyt')
    parser.add_argument('-s', '--secret', help='Secret key for JWT token')
    args = parser.parse_args()

    # Use provided secret or fall back to environment variable
    secret = args.secret or os.getenv('JWT_DEVELOPMENT_SECRET')
    if not secret:
        raise ValueError("JWT secret must be provided either as an argument or in JWT_DEVELOPMENT_SECRET environment variable")

    context = TokenContext(secret)
    token = generate_jwt_token(context)
    print(token)


def generate_jwt_token(context: TokenContext) -> str:
    # get str from base64 encoded secret
    key = base64.b64decode(context.secret)

    # generate jwt token with claims
    token = jwt.encode(context.claims.__dict__, key, algorithm='HS256')

    return token


if __name__ == '__main__':
    main()
