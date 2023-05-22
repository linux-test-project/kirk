"""
.. module:: setup
   :platform: Multiplatform
   :synopsis: installer module
.. moduleauthor:: Andrea Cervesato <andrea.cervesato@mailbox.org>
"""
from setuptools import setup

setup(
    name='kirk',
    version='1.0',
    description='All-in-one Linux Testing Framework',
    author='Andrea Cervesato',
    author_email='andrea.cervesato@mailbox.org',
    license='LGPLv2',
    url='https://github.com/acerv/kirk',
    classifiers=[
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Software Development :: Testing',
    ],
    extras_require={
        'ssh':  ['asyncssh <= 2.13.1'],
        'ltx':  ['msgpack <= 1.0.5'],
    },
    packages=['kirk'],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'kirk=kirk.main:run',
        ],
    },
)
