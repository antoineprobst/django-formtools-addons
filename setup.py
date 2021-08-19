#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import sys

import setuptools

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

__version__ = '0.2.2'

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

setuptools.setup(
    name='django2-formtools-addons',
    version=__version__,
    description="""'Addons for Django 2 Formtools'""",
    long_description=readme + '\n\n' + history,
    author='VikingCo',
    author_email='technology@vikingco.com',
    url='https://github.com/hpe95/django-formtools-addons',
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=["django >= 2.1", "six >= 1.9"],
    extras_require={},
    license="BSD",
    zip_safe=False,
    keywords='django2-formtools-addons',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)
