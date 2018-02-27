import os
import sys
import logging
import time
import re
import json

from pprint import pformat
from time import sleep
from datetime import datetime
from shutil import copyfile

from lib.events import EventList
from lib.slurm import Slurm
from JobStatus import JobStatus, StatusMap
from lib.util import (render,
                      print_debug,
                      print_line)


class APrimeDiags(object):
    def __init__(self, config, event_list):
        """
        Setup class attributes
        """
        self.event_list = event_list
        self.inputs = {
            'account': '',
            'simulation_start_year': '',
            'target_host_path': '',
            'ui': '',
            'web_dir': '',
            'host_url': '',
            'experiment': '',
            'run_scripts_path': '',
            'year_set': '',
            'input_path': '',
            'start_year': '',
            'end_year': '',
            'output_path': '',
            'template_path': '',
            'test_atm_res': '',
            'test_mpas_mesh_name': '',
            'aprime_code_path': '',
            'filemanager': ''
        }
        self.start_time = None
        self.end_time = None
        self.output_path = config['output_path']
        self.filemanager = config['filemanager']
        self.config = {}
        self.host_suffix = '/index.html'
        self.status = JobStatus.INVALID
        self._type = 'aprime_diags'
        self.year_set = config['year_set']
        self.start_year = config['start_year']
        self.end_year = config['end_year']
        self.job_id = 0
        self.depends_on = []
        self.prevalidate(config)

    def __str__(self):
        sanitized = {k: v for k, v in self.config.items() if k != 'filemanager'}
        return json.dumps({
            'type': self.type,
            'config': sanitized,
            'status': self.status,
            'depends_on': self.depends_on,
            'job_id': self.job_id,
            'year_set': self.year_set
        }, sort_keys=True, indent=4)

    @property
    def type(self):
        return self._type

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        self._status = status

    def prevalidate(self, config):
        """
        Create input and output directories
        """
        self.config = config
        self.status = JobStatus.VALID
        if not os.path.exists(self.config.get('run_scripts_path')):
            os.makedirs(self.config.get('run_scripts_path'))
        if not os.path.exists(self.config['input_path']):
            msg = 'Creating input directory at {}'.format(self.config['input_path'])
            print_line(
                ui=self.config.get('ui', False),
                line=msg,
                event_list=self.event_list,
                current_state=True)
            os.makedirs(self.config['input_path'])

        if self.year_set == 0:
            self.status = JobStatus.INVALID
        else:
            self.status = JobStatus.VALID

    def postvalidate(self):
        """
        Check that what the job was supposed to do actually happened
        returns 1 if the job is done, 0 otherwise
        """
        # find the directory generated by coupled diags

        if not os.path.exists(self.output_path):
            return False
        try:
            output_contents = os.listdir(self.output_path)
        except IOError:
            return False
        if not output_contents:
            return False
        output_total = sum([len(files)
                            for r, d, files in os.walk(self.output_path)])
        return bool(output_total >= 600)

    def setup_input_directory(self):
        """
        Creates a directory full of symlinks to the input data

        Parameters:
            None
        Returns:
            True if successful
            False if missing input data
            2 if error
        """
        types = ['atm', 'ocn', 'ice', 'streams.ocean',
                 'streams.cice', 'rest', 'mpas-o_in',
                 'mpas-cice_in', 'meridionalHeatTransport',
                 'mpascice.rst']
        test_archive_path = os.path.join(
            self.config['input_path'],
            self.config['experiment'],
            'run')
        if not os.path.exists(test_archive_path):
            os.makedirs(test_archive_path)
        try:
            for datatype in types:
                input_files = self.filemanager.get_file_paths_by_year(
                    start_year=self.start_year,
                    end_year=self.end_year,
                    _type=datatype)
                for file in input_files:
                    if not os.path.exists(file):
                        return False
                    head, tail = os.path.split(file)
                    dst = os.path.join(test_archive_path, tail)
                    if not os.path.exists(dst):
                        os.symlink(file, dst)
        except Exception as e:
            print_debug(e)
            return 2
        return True

    def execute(self):
        """
        Setup the run script which will symlink in all the required data,
        and submit that script to resource manager
        """
        # First check if the job has already been completed
        if self.postvalidate():
            self.status = JobStatus.COMPLETED
            return 0
        
        # set the job to pending so it doesnt get double started
        self.status = JobStatus.PENDING

        set_string = '{start:04d}_{end:04d}'.format(
            start=self.config.get('start_year'),
            end=self.config.get('end_year'))

        # Setup output directory
        if not os.path.exists(self.config['output_path']):
            os.makedirs(self.config['output_path'])

        # render run template
        run_aprime_template_out = os.path.join(
            self.output_path,
            'run_aprime.bash')
        variables = {
            'output_base_dir': self.output_path,
            'test_casename': self.config['experiment'],
            'test_archive_dir': self.config['input_path'],
            'test_atm_res': self.config['test_atm_res'],
            'test_mpas_mesh_name': self.config['test_mpas_mesh_name'],
            'begin_yr': self.start_year,
            'end_yr': self.end_year
        }
        render(
            variables=variables,
            input_path=self.config['template_path'],
            output_path=run_aprime_template_out)

        # copy the template into the run_scripts directory
        run_name = '{type}_{start:04d}_{end:04d}'.format(
            start=self.start_year,
            end=self.end_year,
            type=self.type)
        template_copy = os.path.join(
            self.config.get('run_scripts_path'),
            run_name)
        copyfile(
            src=run_aprime_template_out,
            dst=template_copy)
        # create the slurm run script
        cmd = 'sh {run_aprime}'.format(
            run_aprime=run_aprime_template_out)

        run_script = os.path.join(
            self.config.get('run_scripts_path'),
            run_name)
        if os.path.exists(run_script):
            os.remove(run_script)
        
        # render the submission script, which includes input directory setup
        input_files = list()
        types = ['atm', 'ocn', 'ice', 'streams.ocean',
                 'streams.cice', 'rest', 'mpas-o_in',
                 'mpas-cice_in', 'meridionalHeatTransport',
                 'mpascice.rst']
        for datatype in types:
            new_files = self.filemanager.get_file_paths_by_year(
                start_year=self.start_year,
                end_year=self.end_year,
                _type=datatype)
            if new_files is None or len(new_files) == 0:
                return -1
            input_files += new_files
        if self.config['simulation_start_year'] != self.start_year:
            input_files += self.filemanager.get_file_paths_by_year(
                start_year=self.config['simulation_start_year'],
                end_year=self.config['simulation_start_year'] + 1,
                _type='ocn')
        variables = {
            'ACCOUNT': self.config.get('account', ''),
            'WORKDIR': self.config.get('aprime_code_path'),
            'CONSOLE_OUTPUT': '{}.out'.format(run_script),
            'FILES': input_files,
            'INPUT_PATH': self.config['input_path'],
            'EXPERIMENT': self.config['experiment'],
            'SCRIPT_PATH': run_aprime_template_out
        }

        head, _ = os.path.split(self.config['template_path'])
        submission_template_path = os.path.join(head, 'aprime_submission_template.sh')
        logging.info('Rendering submision script for aprime')
        logging.info(json.dumps({'variables': variables, 'input_path': input_path, 'output_path': output_path}))
        render(
            variables=variables,
            input_path=submission_template_path,
            output_path=run_script)

        slurm = Slurm()
        msg = 'Submitting to queue {type}: {start:04d}-{end:04d}'.format(
            type=self.type,
            start=self.start_year,
            end=self.end_year)
        print_line(
            ui=self.config.get('ui', False),
            line=msg,
            event_list=self.event_list,
            current_state=True)
        self.job_id = slurm.batch(run_script)
        status = slurm.showjob(self.job_id)
        self.status = StatusMap[status.get('JobState')]

        return self.job_id
