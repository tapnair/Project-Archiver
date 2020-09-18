from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='Project-Archiver',
    version='2.0.1',
    description='A Project Archiving Utility for Fusion 360',
    long_description=long_description,
    packages=['Project-Archiver', 'Project-Archiver.apper.apper', 'Project-Archiver.commands'],
    package_data={
        "": ["resources/*", "resources/**/*", "*.manifest"],
    },
    url='https://github.com/tapnair/Project-Archiver',
    license='MIT',
    author='Patrick Rainsberry',
    author_email='patrick.rainsberry@autodesk.com',
)
