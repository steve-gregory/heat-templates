#!/usr/bin/env python
import json
import logging
import os
import subprocess
import sys

WORKING_DIR = os.environ.get('HEAT_ANSIBLE_WORKING',
                             '/var/lib/heat-config/heat-config-ansible')
OUTPUTS_DIR = os.environ.get('HEAT_ANSIBLE_OUTPUTS',
                             '/var/run/heat-config/heat-config-ansible')


def prepare_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, 0o700)


def main(argv=sys.argv):
    log = logging.getLogger('heat-config')
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            '[%(asctime)s] (%(name)s) [%(levelname)s] %(message)s'))
    log.addHandler(handler)
    log.setLevel('DEBUG')

    prepare_dir(OUTPUTS_DIR)
    prepare_dir(WORKING_DIR)
    os.chdir(WORKING_DIR)

    c = json.load(sys.stdin)

    variables = {}
    for input in c['inputs']:
        input_name = input['name']
        var_name = 'FACTER_%s' % input_name
        variables[var_name] = input.get('value','')

    fn = os.path.join(WORKING_DIR, '%s_playbook.yaml' % c['id'])
    heat_outputs_path = os.path.join(OUTPUTS_DIR, c['id'])
    variables['FACTER_heat_outputs_path'] = heat_outputs_path

    #Write 'FACTER_*' vars to env, ansible will pick them up!
    env_debug = ' '.join('%s="%s"' % (k, v) for k, v in variables.items())

    env = os.environ.copy()
    env.update(variables)

    #Write 'config' to file
    with os.fdopen(os.open(fn, os.O_CREAT | os.O_WRONLY, 0o700), 'w') as f:
        f.write(c.get('config',''))

    cmd = ['ansible-playbook','-i','localhost,', fn]
    log.debug('Running %s %s' % (env_debug, ' '.join(cmd)))
    try:
        subproc = subprocess.Popen([cmd], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env)
    except OSError:
        log.warn("ansible not installed yet")
        return
    stdout, stderr = subproc.communicate()

    log.info('Return code %s' % subproc.returncode)
    if stdout:
        log.info(stdout)
    if stderr:
        log.info(stderr)

    #TODO: Test if ansible returns any non-zero return codes in success.
    if subproc.returncode:
        log.error("Error running %s. [%s]\n" % (fn, subproc.returncode))
    else:
        log.info('Completed %s' % fn)

    response = {}

    for output in c.get('outputs') or []:
        output_name = output['name']
        try:
            with open('%s.%s' % (heat_outputs_path, output_name)) as out:
                response[output_name] = out.read()
        except IOError:
            pass

    response.update({
        'deploy_stdout': stdout,
        'deploy_stderr': stderr,
        'deploy_status_code': subproc.returncode,
    })

    json.dump(response, sys.stdout)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
