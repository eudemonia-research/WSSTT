#!/usr/bin/env python

from setuptools import setup

setup(name='WSSTT',
      version='0.0.4',
      description='P2P Message Transport Layer via WebSockets',
      author='Max Kaye',
      author_email='max@eudemonia.io',
      packages=['WSSTT'],
      install_requires=['encodium', 'websockets'],
     )


