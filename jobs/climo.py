import logging
import os
from jobs.job import Job
from lib.JobStatus import JobStatus
from lib.filemanager import FileStatus
from lib.util import get_climo_output_files, print_line
from lib.slurm import Slurm

class Climo(Job):
    def __init__(self, *args, **kwargs):
        super(Climo, self).__init__(*args, **kwargs)
        self._data_required = ['atm']
        self._job_type = 'climo'
        self._dryrun = True if kwargs.get('dryrun') == True else False
        self._slurm_args = {
            'num_cores': '-n 16',  # 16 cores
            'run_time': '-t 0-10:00',  # 5 hours run time
            'num_machines': '-N 1',  # run on one machine
            'oversubscribe': '--oversubscribe'
        }
    
    def setup_dependencies(self, *args, **kwargs):
        """
        Climo doesnt require any other jobs
        """
        return True

    def prevalidate(self):
        """
        Prerun validation for Ncclimo

        Ncclimo just needs atm files, 12 for each year

        Returns true if all the input files were found, False otherwise
        """
        if self._dryrun:
            return True

        for year in range(self.start_year, self.end_year + 1):
            for month in range(1, 13):
                # create the name of the file we're expecting
                testname = '{exp}.cam.h0.{year:04d}-{month:02d}.nc'.format(
                    exp=self.case, year=year, month=month)
                found = False
                for input_file in self._input_file_paths:
                    tail, head = os.path.split(input_file)
                    if testname in head:
                        found = True
                        break
                if not found:
                    msg = '{file} not found for {job}-{start:04d}-{end:04d}-{case}'.format(
                        file=testname, job=self.job_type, start=self.start_year, end=self.end_year, case=self._short_name)
                    logging.error(msg)
                    self.status = JobStatus.INVALID
                    return False
                if not os.path.exists(input_file):
                    msg = '{} does not exist'.format(input_file)
                    logging.error(msg)
                    self.status = JobStatus.INVALID
                    return False
        msg = '{job}-{start:04d}-{end:04d}-{case}: prevalidation successful'.format(
            job=self.job_type, start=self.start_year, end=self.end_year, case=self._short_name)
        logging.info(msg)
        self.status = JobStatus.VALID
        return True
    
    def postvalidate(self, config):
        """
        Postrun validation for Ncclimo
        
        Ncclimo outputs 17 files, one for each month and then one for the 5 seasons
        """
        if self._dryrun:
            return True
        regrid_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['post-processing']['climo']['destination_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))
        climo_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['simulations'][self.case]['native_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))
        self._output_path = climo_path

        # check the output directories exist
        if not os.path.exists(regrid_path):
            return False
        if not os.path.exists(climo_path):
            return False
        file_list = get_climo_output_files(
            input_path=regrid_path,
            start_year=self.start_year,
            end_year=self.end_year)
        if len(file_list) < 17: # number of months plus seasons and annual
            msg = '{}-{:04d}-{:04d}-{}: Failed to produce all regridded climos'.format(
                self.job_type, self.start_year, self.end_year, self._short_name)
            logging.error(msg)
            return False
        file_list = get_climo_output_files(
            input_path=climo_path,
            start_year=self.start_year,
            end_year=self.end_year)
        if len(file_list) < 17: # number of months plus seasons and annual
            msg = '{}-{:04d}-{:04d}-{}: Failed to produce all native grid climos'.format(
                    self.job_type, self.start_year, self.end_year, self._short_name)
            logging.error(msg)
            return False

        # nothing's gone wrong, so we must be done
        return True
    
    def execute(self, config, dryrun=False):
        regrid_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['post-processing']['climo']['destination_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))
        if not os.path.exists(regrid_path):
            os.makedirs(regrid_path)

        climo_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['simulations'][self.case]['native_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))
        if not os.path.exists(climo_path):
            os.makedirs(climo_path)

        self._output_path = climo_path

        if not dryrun:
            self._dryrun = False
            if not self.prevalidate():
                return False
            if self.postvalidate(config):
                self.status = JobStatus.COMPLETED
                return True
        else:
            self._dryrun = True
              
        input_path, _ = os.path.split(self._input_file_paths[0])
        cmd = [
            'ncclimo',
            '-c', self.case,
            '-a', 'sdd',
            '-s', str(self.start_year),
            '-e', str(self.end_year),
            '-i', input_path,
            '-r', config['post-processing']['climo']['regrid_map_path'],
            '-o', climo_path,
            '-O', regrid_path,
            '--no_amwg_links',
        ]
        slurm_command = ' '.join(cmd)
        
        return self._submit_cmd_to_slurm(config, cmd)
    
    def handle_completion(self, filemanager, event_list, config):
        if self.status != JobStatus.COMPLETED:
            msg = '{job}-{start:04d}-{end:04d}-{case}: Job failed, not running completion handler'.format(
                job=self.job_type, start=self.start_year, end=self.end_year, case=self._short_name)
            print_line(msg, event_list)
            logging.info(msg)
            return
        else:
            msg = '{job}-{start:04d}-{end:04d}-{case}: Job complete'.format(
                job=self.job_type, start=self.start_year, end=self.end_year, case=self._short_name)
            print_line(msg, event_list)
            logging.info(msg)

        regrid_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['post-processing']['climo']['destination_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))

        new_files = list()
        for regrid_file in get_climo_output_files(regrid_path, self.start_year, self.end_year):
            new_files.append({
                'name': regrid_file,
                'local_path': os.path.join(regrid_path, regrid_file),
                'case': self.case,
                'year': self.start_year,
                'local_status': FileStatus.PRESENT.value
            })
        filemanager.add_files(
            data_type='climo_regrid',
            file_list=new_files)
        if not config['data_types'].get('climo_regrid'):
            config['data_types']['climo_regrid'] = {'monthly': True}
        
        climo_path = os.path.join(
            config['global']['project_path'], 'output', 'pp',
            config['simulations'][self.case]['native_grid_name'],
            self._short_name, 'climo', '{length}yr'.format(length=self.end_year-self.start_year+1))

        for climo_file in get_climo_output_files(climo_path, self.start_year, self.end_year):
            new_files.append({
                'name': climo_file,
                'local_path': os.path.join(regrid_path, climo_file),
                'case': self.case,
                'year': self.start_year,
                'local_status': FileStatus.PRESENT.value
            })
        filemanager.add_files(
            data_type='climo_native',
            file_list=new_files)
        if not config['data_types'].get('climo_native'):
            config['data_types']['climo_native'] = {'monthly': True}
        
        msg = '{job}-{start:04d}-{end:04d}-{case}: Job completion handler done'.format(
            job=self.job_type, start=self.start_year, end=self.end_year, case=self._short_name)
        print_line(msg, event_list)
        logging.info(msg)
