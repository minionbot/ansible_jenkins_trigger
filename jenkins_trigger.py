#!/usr/bin/env python
# coding: utf-8
# Wang Jing (wangjild@gmail.com)

__author__ = 'wangjing'

DOCUMENTATION = '''
---
module: jenkins_trigger
short_description: Trigger a job in jenkins with/without parameters
version_added: "2.1.0"
description:
            - Trigger a job in jenkins.
            - Optionally send a dictionary parameters
            - Optionally do authentication
options:
    name:
        description:
          - Jenkins job name
        required: true
    url:
        description:
          - Jenkins job url
        required: true
    timeout:
        description:
          - Wait jenkins job for a moment
        required: false
    params:
        description:
            - A dictionary of parameters to inject in job
notes:
   - Will always return changed if job exists, else will fail
   - Supports basic authentication
requirements: [ jenkinsapi ]
'''

EXAMPLES = '''
- name: Trigger a job no parm
  jenkins_trigger:
     name="test-remote_trigger"
     url="jenkins.example.com:8080"
- name: Trigger a job with parm
  jenkins_trigger:
     name="test-remote_trigger"
     url="jenkins.example.com:8080"
  args:
    params:
        x: 1
        y: 2
        z: 3
- name: Trigger a job auth
  jenkins_trigger:
     name="test-remote_trigger"
     url="jenkins.example.com:8080"
     user=foo
     password=pass
'''

import multiprocessing

try:
    from jenkinsapi.jenkins import Jenkins as JenkinsAPI
    from jenkinsapi import config, constants
    import jenkinsapi
except ImportError:
    jenkinsapi_client_found = False
    JenkinsAPI = object
else:
    jenkinsapi_client_found = True

class Jenkins(JenkinsAPI):

    def build_job(self, jobname, params=None, block = False, delay = 5):
        """
        Invoke a build by job name
        :param jobname: name of exist job, str
        :param params: the job params, dict
        :return: none
        """
        return self[jobname].invoke(build_params=params or {}, block = block, delay=delay)

def run_module(job_name, jenkins_url, jenkins_parm, jenkins_user, jenkins_password, q):

    build_queue = None
    status = constants.STATUS_FAIL

    try:
        J = Jenkins(jenkins_url, username=jenkins_user, password=jenkins_password)
    except Exception, e:
        q.put([status, "Jenkins connection to '{}' Issue: ".format(jenkins_url, e.message)])
        return

    try:
        build_queue = J.build_job(job_name, jenkins_parm, block=True, delay=5)
    except jenkinsapi.custom_exceptions.UnknownJob:
        q.put([status, "Job '{}' does not exist on '{}'".format(job_name, jenkins_url)])
        return
    except Exception, e:
        q.put([status, "Job '{}/job/{}' execution encounter error. Issue: ".format(jenkins_url,
                                                                                                job_name,
                                                                                                e.message)])
    build = build_queue.get_build()

    result_api_url = build.get_result_url()
    result_url = result_api_url[:len(result_api_url) - len(config.JENKINS_API)]
    status = build.get_status()

    q.put([status, "Job result is {}. See: {} for more detail".format(status, result_url)])

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(default=None, required=True),
            user=dict(default=None, required=False),
            password=dict(default=None, required=False),
            url=dict(default=None, required=True),
            params=dict(default=None, type="dict"),
            timeout=dict(default=1800, type='int', required=False)
        ),
        # No need to support check mode
        supports_check_mode=False
    )

    job_name = module.params['name']
    jenkins_url = module.params['url']
    jenkins_parm = module.params['params']
    jenkins_user = module.params['user']
    jenkins_password = module.params['password']
    timeout = module.params['timeout']

    if not jenkinsapi_client_found:
        module.fail_json(msg="The Jenkins Trigger module requires jenkinsapi library. use 'pip install jenkinsapi' ")

    msg_queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=run_module, args=(
        job_name, jenkins_url, jenkins_parm, jenkins_user, jenkins_password, msg_queue))
    process.start()

    process.join(timeout=timeout)

    if process.is_alive():
        process.terminate()
        module.fail_json(msg="Jenkins job timeout! see: {}/job/{} for more detail".format(jenkins_url, job_name))

    if not msg_queue.qsize():
        module.fail_json(msg = "Job execute failed due to unknown reason")

    result = msg_queue.get(block=True)

    if result[0] in [constants.STATUS_SUCCESS, constants.STATUS_PASSED, constants.STATUS_FIXED]:
        module.exit_json(changed=True, msg=result[1], status=result[0])

    module.fail_json(msg=result[1], status=result[0])

# import module snippets
from ansible.module_utils.basic import *
main()
