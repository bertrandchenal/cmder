#!/usr/bin/env python
from setuptools import setup


long_description = '''
Conquer is a small python3 utility to help run commands. It supports
Linux, Windows and MacOS.
'''

description = 'Conquer runs commands'

setup(name='Conquer',
      version='0.0.2',
      description=description,
      long_description=long_description,
      author='Bertrand Chenal',
      author_email='bertrand@adimian.com',
      url='https://github.com/bertrandchenal/conquer',
      license='MIT',
      packages=['conquer'],
  )
