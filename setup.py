from setuptools import setup

setup(name='pygernag',
      version='0.0.1',
      description='Sync PD / Nag - see README',
      packages=['pygernag'],
      entry_points={
            'console_scripts': ['pygernag = pygernag.pygernag:main']
      }
      )
