from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tools-admin",
    version="2.7.0",
    author="gruelasjr",
    description="Complete Python toolkit for Linux server administration, audit, and management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gruelasjr/Tools",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: System Administrators",
    ],
    python_requires=">=3.8",
    install_requires=[
        "click>=8.1.0",
        "paramiko>=2.12.0",
        "dnspython>=2.3.0",
        "requests>=2.28.0",
        "pyyaml>=6.0",
        "tqdm>=4.65.0",
    ],
    entry_points={
        "console_scripts": [
            "tools=tools.cli.main:cli",
        ],
    },
)
