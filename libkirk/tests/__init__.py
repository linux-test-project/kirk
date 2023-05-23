"""
.. module:: __init__
    :platform: Linux
    :synopsis: Entry point of the testing suite
.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import os
import sys

# include library
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
