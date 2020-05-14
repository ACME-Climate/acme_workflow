from __future__ import absolute_import, division, print_function, unicode_literals
import logging
import os
import re
import sys
import traceback

from datetime import datetime

import jinja2


def print_line(line, ignore_text=False, newline=True, status='ok'):
    """
    Prints a message to either the console, the event_list, or the current event

    Parameters:
        line (str): The message to print
        ignore_text (bool): should this be printed to the console if in text mode
    """
    logging.info(line)
    if not ignore_text:
        now = datetime.now()
        if status == 'ok':
            start_color = colors.OKGREEN
        else:
            start_color = colors.FAIL
        timestr = '{color_start}[+]{color_end} {hour}:{min}:{sec}'.format(
            hour=now.strftime('%H'),
            min=now.strftime('%M'),
            sec=now.strftime('%S'),
            color_start=start_color,
            color_end=colors.ENDC)
        msg = '{time}: {line}'.format(
            time=timestr,
            line=line)
        if newline:
            print(msg)
        else:
            print(msg, end=' ')
        sys.stdout.flush()
# -----------------------------------------------


def get_climo_output_files(input_path, start_year, end_year):
    """
    Return a list of ncclimo climatologies from start_year to end_year

    Parameters:
        input_path (str): the directory to look in
        start_year (int): the first year of climos to add to the list
        end_year (int): the last year
    Returns:
        file_list (list(str)): A list of the climo files in the directory
    """
    if not os.path.exists(input_path):
        return None
    contents = [s for s in os.listdir(input_path) if not os.path.isdir(s)]
    pattern = r'_{start:04d}\d\d_{end:04d}\d\d_climo\.nc'.format(
        start=start_year,
        end=end_year)
    return [x for x in contents if re.search(pattern=pattern, string=x)]
# -----------------------------------------------


def get_cmip_output_files(input_path):
    """
    From a CMIP6 filename, return the variable name as well as the start and end year
    """

    if input_path[-3:] != '.nc':
        return False, False, False
    
    idx = input_path.find('_')
    var = input_path[:idx]

    pattern = r'\d{6}-\d{6}'
    idx = re.search(pattern, input_path)
    if not idx:
        return False, False, False
    idx = idx.start()
    start = int(input_path[idx: idx + 4])
    end = int(input_path[idx + 7: idx + 11])

    return var, start, end
# -----------------------------------------------


def get_ts_output_files(input_path, var_list, start_year, end_year):
    """
    Return a list of ncclimo timeseries files from a list of variables, start_year to end_year

    Parameters:
        input_path (str): the directory to look in
        var_list (list): a list of strings of variable names
        start_year (int): the first year of climos to add to the list
        end_year (int): the last year
    Returns:
        ts_list (list): A list of the ts files
    """
    if not os.path.exists(input_path):
        return None
    contents = [s for s in os.listdir(input_path) if not os.path.isdir(s)]
    ts_list = list()
    for var in var_list:
        pattern = r'{var}_{start:04d}01_{end:04d}12\.nc'.format(
            var=var,
            start=start_year,
            end=end_year)
        for item in contents:
            if re.search(pattern, item):
                ts_list.append(item)
                break
    return ts_list
# -----------------------------------------------


def get_data_output_files(input_path, case, start_year, end_year):
    if not os.path.exists(input_path):
        return None
    contents = [s for s in os.listdir(input_path) if not os.path.isdir(s)]
    contents.sort()
    data_list = list()
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            pattern = r'%s.*\.%04d-%02d.nc' % (case, year, month)
            for item in contents:
                if re.match(pattern, item):
                    data_list.append(item)
                    break
    return data_list
# -----------------------------------------------


def print_debug(e):
    """
    Print an exceptions relavent information
    """
    print('1', e.__doc__)
    print('2', sys.exc_info())
    print('3', sys.exc_info()[0])
    print('4', sys.exc_info()[1])
    _, _, tb = sys.exc_info()
    print('5', traceback.print_tb(tb))
# -----------------------------------------------


def format_debug(e):
    """
    Return a string of an exceptions relavent information
    """
    _, _, tb = sys.exc_info()
    return """
1: {doc}
2: {exec_info}
3: {exec_0}
4: {exec_1}
5: {lineno}
6: {stack}
""".format(
        doc=e.__doc__,
        exec_info=sys.exc_info(),
        exec_0=sys.exc_info()[0],
        exec_1=sys.exc_info()[1],
        stack=traceback.print_tb(tb))
# -----------------------------------------------


class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
# -----------------------------------------------


def print_message(message, status='error'):
    """
    Prints a message with either a green + or a red -

    Parameters:
        message (str): the message to print
        status (str): th"""
    if status == 'error':
        print(colors.FAIL + '[-] ' + colors.ENDC + \
            colors.BOLD + str(message) + colors.ENDC)
    elif status == 'ok':
        print(colors.OKGREEN + '[+] ' + colors.ENDC + str(message))
# -----------------------------------------------


def render(variables, input_path, output_path):
    """
    Renders the jinja2 template from the input_path into the output_path
    using the variables from variables
    """
    try:
        tail, head = os.path.split(input_path)

        template_path = os.path.abspath(tail)
        loader = jinja2.FileSystemLoader(searchpath=template_path)
        env = jinja2.Environment(loader=loader)
        template = env.get_template(head)
        outstr = template.render(variables)

        with open(output_path, 'a+') as outfile:
            outfile.write(outstr)
    except Exception:
        return False
    else:
        return True
# -----------------------------------------------


def create_symlink_dir(src_dir, src_list, dst):
    """
    Create a directory, and fill it with symlinks to all the items in src_list

    Parameters:
        src_dir (str): the path to the source directory
        src_list (list): a list of strings of filenames
        dst (str): the path to the directory that should hold the symlinks
    """
    if not src_list:
        return
    if not os.path.exists(dst):
        os.makedirs(dst)
    for src_file in src_list:
        if not src_file:
            continue
        source = os.path.join(src_dir, src_file)
        destination = os.path.join(dst, src_file)
        if os.path.lexists(destination):
            os.remove(destination)
        try:
            os.symlink(source, destination)
        except Exception as e:
            msg = format_debug(e)
            logging.error(msg)
# -----------------------------------------------
