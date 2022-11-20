#!/usr/bin/python3

from glob import glob
from setuptools import setup


setup(
	name='trio-web3',
	version='0.1a0',
	author='Guillermo Rodriguez',
	author_email='guillermo@telos.net',
	packages=['trio_web3'],
	install_requires=[
        'trio',
        'httpx',
        'eth_abi',
        'eth_utils',
        'eth_typing'
    ],
    data_files=glob('abis/**')
)
