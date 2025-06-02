import os
from setuptools import setup


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="hevy-sync",
    version="1.0.0.dev1",
    author="Lucas Girod, based on withing-sync by Masayuki Hamasaki, Steffen Vogel",
    author_email="noreply@girod-steiger.ch",
    description="A tool for synchronisation of Hevy to Garmin Connect.",
    keywords="garmin hevy sync api smarthome",
    url="https://github.com/lucasgirod/hevy-sync",
    packages=["hevy_sync"],
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    classifiers=[
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
        "lxml==5.2.2",
        "requests==2.31.0",
        "garth==0.4.46",
        "python-dotenv",
        "fit_tool"],
    entry_points={
        "console_scripts": ["hevy-sync=hevy_sync.sync_app:main"],
    },
    zip_safe=False,
    include_package_data=True,
)
