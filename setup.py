#!/usr/bin/python3

from setuptools import setup


setup(
	name='trio-web3',
	version='0.1a0',
	author='Guillermo Rodriguez',
	author_email='guillermo@telos.net',
	packages=['trio_web3'],
	install_requires=['web3', 'trio']
)
