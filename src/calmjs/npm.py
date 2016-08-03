# -*- coding: utf-8 -*-
"""
Module for dealing with npm framework.

Provides some helper functions that deal with package.json
"""

from calmjs.cli import Driver

PACKAGE_JSON = 'package.json'
NPM = 'npm'

_inst = Driver(pkg_manager_bin=NPM, pkgdef_filename=PACKAGE_JSON)
get_node_version = _inst.get_node_version
get_npm_version = _inst.get_pkg_manager_version
npm_init = _inst.pkg_manager_init
npm_install = _inst.pkg_manager_install
package_json = _inst.pkgdef_filename
