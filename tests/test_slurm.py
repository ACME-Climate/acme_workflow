import unittest
import os, sys
import inspect

if sys.path[0] != '.':
    sys.path.insert(0, os.path.abspath('.'))


from lib.slurm import Slurm
from lib.util import print_message

class TestSlurm(unittest.TestCase):

    def test_batch_and_cancel(self):
        print '\n'; print_message('---- Starting Test: {} ----'.format(inspect.stack()[0][3]), 'ok')
        slurm = Slurm()
        command = os.path.join('tests', 'test_slurm_batch.sh')
        job_id = slurm.batch(command)
        self.assertTrue(job_id)
        self.assertTrue(isinstance(job_id, int))
        self.assertNotEqual(job_id, 0)

        job_info = slurm.showjob(job_id)
        allowed_states = ['PENDING', 'RUNNING', 'COMPLETE', 'COMPLETING']
        self.assertTrue(job_info.state in allowed_states)

        info = slurm.queue()
        in_queue = False
        for item in info:
            if int(item['JOBID']) == job_id:
                in_queue = True
                break
        self.assertTrue(in_queue)
        self.assertTrue(slurm.cancel(job_id))

if __name__ == '__main__':
    unittest.main()
