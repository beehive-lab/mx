#!/usr/bin/env python2.7
#
# ----------------------------------------------------------------------------------------------------
#
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# This code is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 only, as
# published by the Free Software Foundation.
#
# This code is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# version 2 for more details (a copy is included in the LICENSE file that
# accompanied this code).
#
# You should have received a copy of the GNU General Public License version
# 2 along with this work; if not, write to the Free Software Foundation,
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
# or visit www.oracle.com if you need additional information or have any
# questions.
#
# ----------------------------------------------------------------------------------------------------
#

import mx
import os
import tempfile
import zipfile
import shutil
from os.path import join, exists

def defaultFindbugsArgs():
    args = ['-textui', '-low', '-maxRank', '15']
    if mx.is_interactive():
        args.append('-progress')
    return args

def _should_test_project(p):
    if not p.isJavaProject():
        return False
    if hasattr(p, 'findbugs'):
        return p.findbugs.lower() == 'true' or p.findbugs is True
    if p.name.endswith('.test'):
        return False
    return True

def findbugs(args, fbArgs=None, suite=None, projects=None):
    """run FindBugs against non-test Java projects"""
    findBugsHome = mx.get_env('FINDBUGS_HOME', None)
    if suite is None:
        suite = mx._primary_suite
    if findBugsHome:
        findbugsJar = join(findBugsHome, 'lib', 'findbugs.jar')
    else:
        findbugsLib = join(mx._mx_suite.get_output_root(), 'findbugs-3.0.0')
        if not exists(findbugsLib):
            tmp = tempfile.mkdtemp(prefix='findbugs-download-tmp', dir=mx._mx_suite.dir)
            try:
                findbugsDist = mx.library('FINDBUGS_DIST').get_path(resolve=True)
                with zipfile.ZipFile(findbugsDist) as zf:
                    candidates = [e for e in zf.namelist() if e.endswith('/lib/findbugs.jar')]
                    assert len(candidates) == 1, candidates
                    libDirInZip = os.path.dirname(candidates[0])
                    zf.extractall(tmp)
                shutil.copytree(join(tmp, libDirInZip), findbugsLib)
            finally:
                shutil.rmtree(tmp)
        findbugsJar = join(findbugsLib, 'findbugs.jar')
    assert exists(findbugsJar)
    nonTestProjects = [p for p in mx.projects() if _should_test_project(p)]
    if not nonTestProjects:
        return 0

    ignoredClasses = set()
    for p in nonTestProjects:
        ignore = getattr(p, 'findbugsIgnoresGenerated', False)
        if not isinstance(ignore, bool):
            mx.abort('Value of attribute "findbugsIgnoresGenerated" must be True or False', context=p)
        if ignore is True:
            sourceDir = p.source_gen_dir()
            for root, _, files in os.walk(sourceDir):
                for name in files:
                    if name.endswith('.java') and '-info' not in name:
                        pkg = root[len(sourceDir) + 1:].replace(os.sep, '.')
                        cls = pkg + '.' + name[:-len('.java')]
                        ignoredClasses.add(cls)

    with tempfile.NamedTemporaryFile(suffix='.xml', prefix='findbugs_exclude_filter.', mode='w', delete=False) as fp:
        findbugsExcludeFilterFile = fp.name
        xmlDoc = mx.XMLDoc()
        xmlDoc.open('FindBugsFilter')
        for cls in ignoredClasses:
            xmlDoc.open('Match')
            xmlDoc.element('Class', attributes={'name' : '~' + cls + '.*'})
            xmlDoc.close('Match')
        xmlDoc.close('FindBugsFilter')
        xml = xmlDoc.xml(indent='  ', newl='\n')
        print >> fp, xml

    outputDirs = map(mx._cygpathU2W, [p.output_dir() for p in nonTestProjects])
    javaCompliance = max([p.javaCompliance for p in nonTestProjects])
    jdk = mx.get_jdk(javaCompliance)
    if jdk.javaCompliance >= "1.9":
        mx.log('FindBugs does not yet support JDK9 - skipping')
        return 0

    findbugsResults = join(suite.dir, 'findbugs.results')

    if fbArgs is None:
        fbArgs = defaultFindbugsArgs()
    cmd = ['-jar', mx._cygpathU2W(findbugsJar)] + fbArgs
    cmd = cmd + ['-exclude', findbugsExcludeFilterFile]
    cmd = cmd + ['-auxclasspath', mx._separatedCygpathU2W(mx.classpath([p.name for p in nonTestProjects], jdk=jdk)), '-output', mx._cygpathU2W(findbugsResults), '-exitcode'] + args + outputDirs
    try:
        exitcode = mx.run_java(cmd, nonZeroIsFatal=False, jdk=jdk)
    finally:
        os.unlink(findbugsExcludeFilterFile)
    if exitcode != 0:
        with open(findbugsResults) as fp:
            mx.log(fp.read())
    os.unlink(findbugsResults)
    return exitcode
