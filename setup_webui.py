# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2015

import os
import subprocess
import sys

from distutils.command.sdist import sdist as _sdist

if sys.version_info < (2, 4):
    print('ERROR: Rucio requires at least Python 2.5 to run.')
    sys.exit(1)

sys.path.insert(0, os.path.abspath('lib/'))

from rucio import version

try:
    from setuptools import setup
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()

name = 'rucio-webui'
packages = ['rucio', 'rucio.web', 'rucio.web.ui', 'rucio.web.ui.common']
data_files = []
description = "Rucio WebUI Package"
IsRelease = True


def run_git_command(cmd):
    output = subprocess.Popen(["/bin/sh", "-c", cmd],
                              stdout=subprocess.PIPE)
    return output.communicate()[0].strip()

if os.path.isdir('.git'):
    if IsRelease:
        git_version_cmd = 'git describe --abbrev=4'
    else:
        git_version_cmd = '''git describe --dirty=-dev`date +%s`'''
    git_version = run_git_command(git_version_cmd)
    branch_nick_cmd = 'git branch | grep -Ei "\* (.*)" | cut -f2 -d" "'
    branch_nick = run_git_command(branch_nick_cmd)
    revid_cmd = "git rev-parse HEAD"
    revid = run_git_command(revid_cmd)
    revno_cmd = "git --no-pager log --oneline | wc -l"
    revno = run_git_command(revno_cmd)
    version_file = open("lib/rucio/vcsversion.py", 'w')
    version_file.write("""
# This file is automatically generated by setup.py, So don't edit it. :)
VERSION_INFO = {
    'final': %s,
    'version': '%s',
    'branch_nick': '%s',
    'revision_id': '%s',
    'revno': %s
}
""" % (IsRelease, git_version, branch_nick, revid, revno))
    version_file.close()
    webui_version_file = open("lib/rucio/web/ui/static/webui_version", 'w')
    webui_version_file.write('%s' % git_version)
    webui_version_file.close()

# If Sphinx is installed on the box running setup.py,
# enable setup.py to build the documentation, otherwise,
# just ignore it
cmdclass = {}

try:
    from sphinx.setup_command import BuildDoc

    class local_BuildDoc(BuildDoc):
        def run(self):
            for builder in ['html']:   # 'man','latex'
                self.builder = builder
                self.finalize_options()
                BuildDoc.run(self)
    cmdclass['build_sphinx'] = local_BuildDoc
except:
    pass


class CustomSdist(_sdist):

    user_options = [
        ('packaging=', None, "Some option to indicate what should be packaged")
    ] + _sdist.user_options

    def __init__(self, *args, **kwargs):
        _sdist.__init__(self, *args, **kwargs)
        self.packaging = "default value for this option"

    def get_file_list(self):
        print "Chosen packaging option: " + name
        self.distribution.data_files = data_files
        _sdist.get_file_list(self)


cmdclass['sdist'] = CustomSdist

setup(
    name=name,
    version=version.version_string(),
    packages=packages,
    package_dir={'': 'lib'},
    data_files=None,
    script_args=sys.argv[1:],
    cmdclass=cmdclass,
    include_package_data=True,
    scripts=None,
    # doc=cmdclass,
    author="Rucio",
    author_email="rucio-dev@cern.ch",
    description=description,
    license="Apache License, Version 2.0",
    url="http://rucio.cern.ch/",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'Operating System :: POSIX :: Linux',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Environment :: No Input/Output (Daemon)', ],
    install_requires=['rucio>=1.2.5', ],
    dependency_links=[],
)
