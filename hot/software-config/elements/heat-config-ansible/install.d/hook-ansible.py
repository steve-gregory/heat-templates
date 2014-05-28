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
        variables[input['name']] = input.get('value','')

    fn = os.path.join(WORKING_DIR, '%s_playbook.yaml' % c['id'])
    vars_filename = os.path.join(WORKING_DIR, '%s_variables.json' % c['id'])
    heat_outputs_path = os.path.join(OUTPUTS_DIR, c['id'])
    variables['heat_outputs_path'] = heat_outputs_path
    
    config_text = c.get('config','')
    if not config_text:
        log.warn("No 'config' input found, nothing to do.")
        return
    #Write 'variables' to file
    with os.fdopen(os.open(vars_filename, os.O_CREAT | os.O_WRONLY, 0o700), 'w') as var_file:
        json.dump(variables, var_file)
    #Write the executable, 'config', to file
    with os.fdopen(os.open(fn, os.O_CREAT | os.O_WRONLY, 0o700), 'w') as f:
        f.write(c.get('config',''))

    cmd = ['ansible-playbook','-i','localhost,', fn, '--extra-vars','@%s' % vars_filename]
    log.debug('Running %s' % (' '.join(cmd),))
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
