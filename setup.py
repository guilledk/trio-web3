#!/usr/bin/python3

from glob import glob
from setuptools import setup, find_packages


setup(
	name='trio-web3',
	version='0.1a0',
	author='Guillermo Rodriguez',
	author_email='guillermo@telos.net',
	packages=find_packages(),
	install_requires=[
        'trio',
        'asks',
        'web3',
        'eth_abi',
        'msgspec',
        'hexbytes',
        'eth_utils',
        'eth_typing',
        'eth-hash[pycryptodome]'
    ],
    data_files=glob('abis/**')
)
