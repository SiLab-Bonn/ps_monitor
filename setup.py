#!/usr/bin/env python
import sys
from setuptools import setup, find_packages  # This setup relies on setuptools since distutils is insufficient and badly hacked code

version = '0.1'
author = 'Jannes Schmitz'
author_email = 'jannes.schmitz@uni-bonn.de'

with open('requirements.txt') as f:
    required = f.read().splitlines()

# Make dict to pass to setup
setup_kwargs = {'name': 'ps_monitor',
                'version': version,
                'description': 'Monitoring and data acquisition software for the DEPFET power supply',
                'url': 'https://github.com/SiLab-Bonn/ps_monitor',
                'license': 'MIT License',
                'long_description': '',
                'author': author,
                'maintainer': author,
                'author_email': author_email,
                'maintainer_email': author_email,
                'packages': find_packages(),
                'setup_requires': ['setuptools'],
                'install_requires': required,
                'include_package_data': True,  # accept all data files and directories matched by MANIFEST.in or found in source control
                'package_data': {'': ['README.*', 'VERSION'], 'docs': ['*'], 'examples': ['*']},
                'keywords': ['electronics', 'daq', 'visualization'],
                'platforms': 'any',
                'entry_points': {'console_scripts': ['ps_monitor = ps_monitor.main:main']}
                }

# Setup
setup(**setup_kwargs)

