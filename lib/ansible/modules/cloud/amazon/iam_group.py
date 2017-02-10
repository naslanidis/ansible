#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
---
module: iam_group
short_description: Manage AWS IAM groups
description:
  - Manage AWS IAM groups
version_added: "2.3"
author: Nick Aslanidis, @naslanidis
options:
  name:
    description:
      - The name of the group to create.
    required: true
  managed_policy:
    description:
      - A list of managed policy ARNs (can't use friendly names due to AWS API limitation) to attach to the group. To embed an inline policy, use M(iam_policy). To remove existing policies, use an empty list item.
    required: false
  users:
    description:
      - A list of existing users to add as members of the group.
    required: false    
  state:
    description:
      - Create or remove the IAM group
    required: true
    choices: [ 'present', 'absent' ]
requirements: [ botocore, boto3 ]
extends_documentation_fragment:
  - aws
'''

EXAMPLES = '''
# Note: These examples do not set authentication details, see the AWS Guide for details.

# Create a group
- iam_group:
    name: testgroup1
    state: present

# Create a group and attach a managed policy using its ARN
- iam_group:
    name: testgroup1
    managed_policy:
      - arn:aws:iam::aws:policy/AmazonSNSFullAccess
    state: present

# Create a group with users as members and attach a managed policy using its ARN
- iam_group:
    name: testgroup1
    managed_policy:
      - arn:aws:iam::aws:policy/AmazonSNSFullAccess
    users:
      - test_user1
      - test_user2
    state: present

# Remove all managed policies from an existing group with an empty list
- iam_group:
    name: testgroup1
    managed_policy:
      -
    state: present

# Remove all group members from an existing group with an empty list
- iam_group:
    name: testgroup1
    managed_policy:
      - arn:aws:iam::aws:policy/AmazonSNSFullAccess
    users:
      -
    state: present


# Delete the group
- iam_group:
    name: testgroup1
    state: absent

'''
RETURN = '''
group:
    description: dictionary containing all the group information
    returned: success
    type: dictionary
    contains:
        arn:
    		description: the Amazon Resource Name (ARN) specifying the group
    		type: string
    		sample: "arn:aws:iam::1234567890:group/testgroup1"
		create_date:
		    description: the date and time, in ISO 8601 date-time format, when the group was created
		    type: string
		    sample: "2017-02-08T04:36:28+00:00"
	    group_id:
		    description: the stable and unique string identifying the group
		    type: string
		    sample: AGPAIDBWE12NSFINE55TM
		group_name:
		    description: the friendly name that identifies the group
		    type: string
		    sample: testgroup1
		path:
		    description: the path to the group
		    type: string
		    sample: /
users:
    description: list containing all the group members
    returned: success
    type: list
    contains:
        arn:
    		description: the Amazon Resource Name (ARN) specifying the user
    		type: string
    		sample: "arn:aws:iam::1234567890:user/test_user1"
		create_date:
		    description: the date and time, in ISO 8601 date-time format, when the user was created
		    type: string
		    sample: "2017-02-08T04:36:28+00:00"
	    user_id:
		    description: the stable and unique string identifying the user
		    type: string
		    sample: AIDAIZTPY123YQRS22YU2
		user_name:
		    description: the friendly name that identifies the user
		    type: string
		    sample: testgroup1
		path:
		    description: the path to the user
		    type: string
		    sample: /		    
'''


import json

try:
    import boto3
    from botocore.exceptions import ClientError, ParamValidationError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


def compare_attached_group_policies(current_attached_policies, new_attached_policies):

    # If new_attached_policies is None it means we want to remove all policies
    if len(current_attached_policies) > 0 and new_attached_policies is None:
        return False

    current_attached_policies_arn_list = []
    for policy in current_attached_policies:
        current_attached_policies_arn_list.append(policy['PolicyArn'])

    if set(current_attached_policies_arn_list) == set(new_attached_policies):
        return True
    else:
        return False


def compare_group_members(current_group_members, new_group_members):

    # If new_attached_policies is None it means we want to remove all policies
    if len(current_group_members) > 0 and new_group_members is None:
        return False

    if set(current_group_members) == set(new_group_members):
        return True
    else:
        return False


def create_or_update_group(connection, module):

    params = dict()
    params['GroupName'] = module.params.get('name')
    managed_policies = module.params.get('managed_policy')
    users = module.params.get('users')
    changed = False

    # Get group
    group = get_group(connection, params['GroupName'])

    # If group is None, create it
    if group is None:
        try:
            group = connection.create_group(**params)
            changed = True
        except (ClientError, ParamValidationError) as e:
            module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

    # Manage managed policies      
    current_attached_policies = get_attached_policy_list(connection, params['GroupName'])
    if not compare_attached_group_policies(current_attached_policies, managed_policies):
        # If managed_policies has a single empty element we want to remove all attached policies
        if len(managed_policies) == 1 and managed_policies[0] == "":
            for policy in current_attached_policies:
                try:
                    connection.detach_group_policy(GroupName=params['GroupName'], PolicyArn=policy['PolicyArn'])
                except (ClientError, ParamValidationError) as e:
                    module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        # Detach policies not present
        current_attached_policies_arn_list = []
        for policy in current_attached_policies:
            current_attached_policies_arn_list.append(policy['PolicyArn'])

        for policy_arn in list(set(current_attached_policies_arn_list) - set(managed_policies)):
            try:
                connection.detach_group_policy(GroupName=params['GroupName'], PolicyArn=policy_arn)
            except (ClientError, ParamValidationError) as e:
                module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))


        # If there are policies in managed_policies attach each policy
        if managed_policies != [None]:
	        for policy_arn in managed_policies:
	            try:
	                connection.attach_group_policy(GroupName=params['GroupName'], PolicyArn=policy_arn)
	            except (ClientError, ParamValidationError) as e:
	                module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        changed = True
    
    # Manage group memberships
    current_group_members = get_group(connection, params['GroupName'])['Users']
    current_group_members_list = []
    for member in current_group_members:
    	current_group_members_list.append(member['UserName'])

    if not compare_group_members(current_group_members_list, users):

        # If users has a single empty element we want to remove all users that are members of the group
        if len(users) == 1 and users[0] == None:
            for user in current_group_members_list:
                try:
                    connection.remove_user_from_group(GroupName=params['GroupName'], UserName=user)
                except (ClientError, ParamValidationError) as e:
                    module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        for user in list(set(current_group_members_list) - set(users)):
            try:
                connection.remove_user_from_group(GroupName=params['GroupName'], UserName=user)
            except (ClientError, ParamValidationError) as e:
                module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))                    

        if users != [None]:
	        for user in users:
	            try:
	                connection.add_user_to_group(GroupName=params['GroupName'], UserName=user)
	            except (ClientError, ParamValidationError) as e:
	                module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        changed = True

    # Get the group again
    group = get_group(connection, params['GroupName'])

    module.exit_json(changed=changed, iam_group=camel_dict_to_snake_dict(group))


def destroy_group(connection, module):

    params = dict()
    params['GroupName'] = module.params.get('name')

    if get_group(connection, params['GroupName']):

        # Remove any attached policies otherwise deletion fails
        try:
            for policy in get_attached_policy_list(connection, params['GroupName']):
                connection.detach_group_policy(GroupName=params['GroupName'], PolicyArn=policy['PolicyArn'])
        except (ClientError, ParamValidationError) as e:
            module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        # Remove any users in the group otherwise deletion fails
    	current_group_members = get_group(connection, params['GroupName'])['Users']
    	current_group_members_list = []
    	for member in current_group_members:
    		current_group_members_list.append(member['UserName'])
        for user in current_group_members_list:
            try:
                connection.remove_user_from_group(GroupName=params['GroupName'], UserName=user)
            except (ClientError, ParamValidationError) as e:
                module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))

        try:
            connection.delete_group(**params)
        except ClientError as e:
            module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))
    
    else:
        module.exit_json(changed=False)

    module.exit_json(changed=True)


def get_group(connection, name):

    params = dict()
    params['GroupName'] = name

    try:
        return connection.get_group(**params)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            return None
        else:
            module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))


def get_attached_policy_list(connection, name):

    try:
        return connection.list_attached_group_policies(GroupName=name)['AttachedPolicies']
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            return None
        else:
            module.fail_json(msg=e.message, **camel_dict_to_snake_dict(e.response))


def main():

    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            name=dict(required=True, type='str'),
            managed_policy=dict(default=[], required=False, type='list'),
            users=dict(default=[], required=False, type='list'),
            state=dict(default=None, choices=['present', 'absent'], required=True)
        )
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
    )

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 required for this module')

    region, ec2_url, aws_connect_params = get_aws_connection_info(module, boto3=True)

    connection = boto3_conn(module, conn_type='client', resource='iam', region=region, endpoint=ec2_url, **aws_connect_params)

    state = module.params.get("state")

    if state == 'present':
        create_or_update_group(connection, module)
    else:
        destroy_group(connection, module)

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ec2 import *

if __name__ == '__main__':
    main()
