#!/usr/bin/python3

TOKEN = ''

url = 'https://apijira.visma.com'

# curl -H "Authorization: Bearer <yourToken>" https://{baseUrlOfYourInstance}/rest/api/content

import requests

# do GET using url and /rest/api/2/issue/VFSOS-389 
# get the issue

# make a get request 
response = requests.get(url + '/rest/api/2/issue/VFSOS-389', headers={'Authorization': 'Bearer ' + TOKEN})

# print request status
print(response.status_code)

# print response content
#print(response.content)

# print description of the issue
print(response.json()['fields']['summary'])






# authenticate with JIRA


# duplicate issue VFSOS-389

# update reporter to me
# update story title
# update story description if provided -m
