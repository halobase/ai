from setuptools import setup, find_packages

# TODO: dynamically retrieve version
name = 'xooai'
version = '0.0.0'
description = 'A lightweight and pluggable tookit to put multiple ML models into production.'

try:
    with open('README.md') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ''



def build_core_requires():
    return [
        'pydantic',
    ]


def build_extra_requires():
    extras_require = {
        'http': [
            'uvicorn',
            'starlette'
        ],
        'grpc': [
            'grpcio',
        ]
    }
    all = []
    for extra in extras_require.values():
        for pkg in extra:
            all.append(pkg)
    return extras_require


setup(
    name=name,
    version=version,
    packages=find_packages(),
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    install_requires=build_core_requires(),
    extras_require=build_extra_requires(),
    classifiers=[],
    keywords=[]
)
