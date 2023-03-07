from setuptools import setup, find_packages

# TODO: dynamically retrieve version
__name = 'xooai'
__version = '0.0.0'
__description = 'A cloud-native solution to put multiple ML models into production.'

try:
    with open('README.md') as f:
        __long_description = f.read()
except FileNotFoundError:
    __long_description = ''

setup(
    name=__name,
    version=__version,
    packages=find_packages(),
    description=__description,
    long_description=__long_description,
    long_description_content_type='text/markdown',
    install_requires=['numpy'],
    extras_require={
        'full': []
    },
    classifiers=[],
    keywords=[]
)
