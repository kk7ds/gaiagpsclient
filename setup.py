from setuptools import setup, find_packages

setup(
    name='gaiagpsclient',
    version='0.1.1',
    packages=find_packages(),
    install_requires=['requests', 'prettytable', 'pytz', 'tzlocal', 'pyyaml', 'pathvalidate'],
    entry_points={
        'console_scripts': ['gaiagps = gaiagps.shell:main'],
    },
)
