# -*- coding: utf-8 -*-
"""
打包脚本
"""

import os
from setuptools import setup, find_packages

BASE_DIR = os.path.realpath(os.path.dirname(__file__))


def generate_version():
    version = "1.0.0"
    if os.path.isfile(os.path.join(BASE_DIR, "version.txt")):
        with open("version.txt", "r") as fd:
            content = fd.read().strip()
            if content:
                version = content
    return version


def parse_requirements():
    reqs = []
    if os.path.isfile(os.path.join(BASE_DIR, "requirements.txt")):
        with open(os.path.join(BASE_DIR, "requirements.txt"), 'r') as fd:
            for line in fd.readlines():
                line = line.strip()
                if line:
                    reqs.append(line)
    return reqs


if __name__ == "__main__":
    setup(
        version=generate_version(),
        name="chrome-master",
        cmdclass={},
        packages=find_packages(exclude=(
            "test",
            "test.*",
        )),
        author="Tencent",
        license="Copyright(c)2010-2022 Tencent All Rights Reserved. ",
        install_requires=parse_requirements(),
        extras_require={'dom': ['py-dom-xpath-six']},
    )
