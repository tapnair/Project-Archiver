#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

import os
import time

import adsk.core

app = adsk.core.Application.get()

LOG_FILE_NAME = 'Project-Archiver-log.txt'

log_path = None


def start_log(output_folder: str, header_lines: list):
    """Start logging an export to the Text Commands window and to a log file in the output folder.

    The log file is appended to, so exporting into the same folder again keeps the earlier runs.
    """
    global log_path
    log_path = os.path.join(output_folder, LOG_FILE_NAME)

    log('')
    log('=' * 60)
    log('Project Archiver export started {}'.format(time.strftime('%Y-%m-%d %H:%M:%S')))
    for line in header_lines:
        log(line)
    log('=' * 60)


def end_log(summary_lines: list):
    """Log the summary of an export and stop writing to the log file."""
    global log_path

    log('-' * 60)
    log('Project Archiver export finished {}'.format(time.strftime('%Y-%m-%d %H:%M:%S')))
    for line in summary_lines:
        log(line)

    log_path = None


def log(message: str):
    """Write a line to the Text Commands window and, during an export, to the log file."""
    # The Text Commands window doesn't accept an empty line
    app.log(message or ' ', adsk.core.LogLevels.InfoLogLevel, adsk.core.LogTypes.ConsoleLogType)

    if log_path:
        try:
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write(message + '\n')
        except OSError:
            pass
