#!/usr/bin/env python

from setuptools import setup

setup(name='SSTT',
      version='0.0.1',
      description='P2P Message Transport Layer via JSONRPC over HTTP',
      author='Max Kaye',
      author_email='max@eudemonia.io',
      packages=['SSTT'],
      install_requires=['Flask', 'Flask-JSONRPC', 'jsonrpc-requests', 'encodium'],
     )


