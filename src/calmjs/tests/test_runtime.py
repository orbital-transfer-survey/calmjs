# -*- coding: utf-8 -*-
import unittest
import json
import os
import sys
from argparse import ArgumentParser
from os.path import join
from logging import DEBUG

import pkg_resources

from calmjs import cli
from calmjs import runtime
from calmjs.utils import pretty_logging

from calmjs.testing import mocks
from calmjs.testing.utils import make_dummy_dist
from calmjs.testing.utils import mkdtemp
from calmjs.testing.utils import remember_cwd
from calmjs.testing.utils import stub_dist_flatten_egginfo_json
from calmjs.testing.utils import stub_mod_call
from calmjs.testing.utils import stub_mod_check_interactive
from calmjs.testing.utils import stub_stdouts


class PackageManagerDriverTestCase(unittest.TestCase):
    """
    Test cases for the package manager driver and argparse usage.
    """

    def test_command_creation(self):
        driver = cli.PackageManagerDriver(pkg_manager_bin='mgr')
        cmd = runtime.PackageManagerRuntime(driver)
        text = cmd.argparser.format_help()
        self.assertIn(
            "run 'mgr install' with generated 'default.json';", text,
        )

    def test_duplicate_init_no_error(self):
        driver = cli.PackageManagerDriver(pkg_manager_bin='mgr')
        cmd = runtime.PackageManagerRuntime(driver)
        cmd.init()

    def test_root_runtime_errors_ignored(self):
        stub_stdouts(self)
        working_set = mocks.WorkingSet({'calmjs.runtime': [
            'foo = calmjs.nosuchmodule:no.where',
            'bar = calmjs.npm:npm',
            'npm = calmjs.npm:npm.runtime',
        ]})
        rt = runtime.Runtime(working_set=working_set)
        with self.assertRaises(SystemExit):
            rt(['-h'])
        out = sys.stdout.getvalue()
        self.assertNotIn('foo', out)
        self.assertIn('npm', out)

    def test_root_runtime_bad_names(self):
        working_set = mocks.WorkingSet({'calmjs.runtime': [
            'bad name = calmjs.npm:npm.runtime',
            'bad.name = calmjs.npm:npm.runtime',
            'badname:likethis = calmjs.npm:npm.runtime',
        ]})

        stderr = mocks.StringIO()
        with pretty_logging(
                logger='calmjs.runtime', level=DEBUG, stream=stderr):
            rt = runtime.Runtime(working_set=working_set)
        err = stderr.getvalue()

        self.assertIn("bad 'calmjs.runtime' entry point", err)

        stub_stdouts(self)
        with self.assertRaises(SystemExit):
            rt(['-h'])
        out = sys.stdout.getvalue()
        self.assertNotIn('bad name', out)
        self.assertNotIn('bad.name', out)
        self.assertNotIn('badname:likethis', out)
        self.assertNotIn('npm', out)

    def setup_dupe_runtime(self):
        from calmjs.testing import utils
        from calmjs.npm import npm
        utils.foo_runtime = runtime.PackageManagerRuntime(npm.cli_driver)
        utils.runtime_foo = runtime.PackageManagerRuntime(npm.cli_driver)

        def cleanup():
            del utils.foo_runtime
            del utils.runtime_foo
        self.addCleanup(cleanup)

    def test_duplication_and_runtime_errors(self):
        """
        Duplicated entry point names

        Naturally, there may be situations where different packages have
        registered entry_points with the same name.  It will be great if
        that can be addressed.
        """

        self.setup_dupe_runtime()

        make_dummy_dist(self, ((
            'entry_points.txt',
            '[calmjs.runtime]\n'
            'bar = calmjs.testing.utils:foo_runtime\n'
        ),), 'example1.foo', '1.0')

        make_dummy_dist(self, ((
            'entry_points.txt',
            '[calmjs.runtime]\n'
            'bar = calmjs.testing.utils:foo_runtime\n'
        ),), 'example2.foo', '1.0')

        make_dummy_dist(self, ((
            'entry_points.txt',
            '[calmjs.runtime]\n'
            'bar = calmjs.testing.utils:runtime_foo\n'
            'baz = calmjs.testing.utils:runtime_foo\n'
        ),), 'example3.foo', '1.0')

        make_dummy_dist(self, ((
            'entry_points.txt',
            '[calmjs.runtime]\n'
            'bar = calmjs.testing.utils:runtime_foo\n'
            'baz = calmjs.testing.utils:runtime_foo\n'
        ),), 'example4.foo', '1.0')

        working_set = pkg_resources.WorkingSet([self._calmjs_testing_tmpdir])

        stderr = mocks.StringIO()
        with pretty_logging(
                logger='calmjs.runtime', level=DEBUG, stream=stderr):
            rt = runtime.Runtime(working_set=working_set)

        msg = stderr.getvalue()
        self.assertIn(
            "duplicated registration of command 'baz' via entry point "
            "'baz = calmjs.testing.utils:runtime_foo' ignored; ",
            msg
        )
        self.assertIn(
            "a calmjs runtime command named 'bar' already registered.", msg)
        self.assertIn(
            "'bar = calmjs.testing.utils:foo_runtime' from 'example", msg)
        self.assertIn(
            "'bar = calmjs.testing.utils:runtime_foo' from 'example", msg)
        self.assertIn(
            "fallback entry point is already added.", msg)

        # Try to use it
        stub_stdouts(self)
        with self.assertRaises(SystemExit):
            rt(['-h'])
        out = sys.stdout.getvalue()
        self.assertIn('bar', out)
        self.assertIn('baz', out)
        # The full import names are available for the one that had a
        # fallback naming triggered - order determined by filesystem.
        foo_runtime = 'calmjs.testing.utils:foo_runtime'
        fr_check = foo_runtime, (foo_runtime in out)
        runtime_foo = 'calmjs.testing.utils:runtime_foo'
        rf_check = runtime_foo, (runtime_foo in out)
        self.assertNotEqual(fr_check[1], rf_check[1])
        cmd = [c for c, check in [rf_check, fr_check] if check][0]

        # see that the full one can be invoked and actually invoke the
        # underlying runtime
        stub_stdouts(self)
        with self.assertRaises(SystemExit):
            rt([cmd, '-h'])
        out = sys.stdout.getvalue()
        self.assertIn(cmd, out)
        self.assertIn("run 'npm install' with generated 'package.json';", out)

        # Time to escalate the problems one can cause...
        with self.assertRaises(RuntimeError):
            # yeah instances of root runtimes are NOT meant for reuse
            # by other runtime instances or argparsers, so this will
            # fail.
            rt.init_argparser(ArgumentParser())

        stderr = mocks.StringIO()
        with pretty_logging(
                logger='calmjs.runtime', level=DEBUG, stream=stderr):
            rt.argparser = None
            rt.init()

        # A forced reinit shouldn't cause a major issue, but it will
        # definitely result in a distinct lack of named commands.
        self.assertNotIn(
            "Runtime instance has been used or initialized improperly.", msg)

        stub_stdouts(self)
        with self.assertRaises(SystemExit):
            rt(['-h'])
        out = sys.stdout.getvalue()
        self.assertNotIn('bar', out)
        self.assertNotIn('baz', out)

        # Now for the finale, where we really muck with the internals.
        stderr = mocks.StringIO()
        with pretty_logging(
                logger='calmjs.runtime', level=DEBUG, stream=stderr):
            # This normally shouldn't happen due to naming restriction,
            # i.e. where names with "." or ":" are disallowed so that
            # they are reserved for fallbacks; although if some other
            # forces are at work, like this...
            rt.runtimes[foo_runtime] = runtime.DriverRuntime(None)
            rt.runtimes[runtime_foo] = runtime.DriverRuntime(None)
            # Now, if one were to force a bad init to happen with
            # (hopefully forcibly) mismatched runtime instances, the
            # main runtime instance will simply explode into the logger
            # in a fit of critical level agony.
            rt.argparser = None
            rt.init()

        # EXPLOSION
        msg = stderr.getvalue()
        self.assertIn("CRITICAL", msg)
        self.assertIn(
            "Runtime instance has been used or initialized improperly.", msg)
        # Naisu Bakuretsu - Megumin.


class IntegrationTestCase(unittest.TestCase):

    def test_calmjs_main_console_entry_point(self):
        stub_stdouts(self)
        with self.assertRaises(SystemExit):
            runtime.main(['-h'])
        # ensure our base action module/class is registered.
        self.assertIn('npm', sys.stdout.getvalue())

    def setup_runtime(self):
        make_dummy_dist(self, (
            ('package.json', json.dumps({
                'name': 'site',
                'dependencies': {
                    'jquery': '~3.1.0',
                },
            })),
        ), 'example.package1', '1.0')

        make_dummy_dist(self, (
            ('package.json', json.dumps({
                'name': 'site',
                'dependencies': {
                    'underscore': '~1.8.3',
                },
            })),
        ), 'example.package2', '2.0')

        working_set = pkg_resources.WorkingSet([self._calmjs_testing_tmpdir])

        # Stub out the underlying data needed for the cli for the tests
        # to test against our custom data for reproducibility.
        stub_dist_flatten_egginfo_json(self, [cli], working_set)
        stub_mod_check_interactive(self, [cli], True)

        # Of course, apply a mock working set for the runtime instance
        # so it can use the npm runtime, however we will use a different
        # keyword.  Note that the runtime is invoked using foo.
        working_set = mocks.WorkingSet({
            'calmjs.runtime': [
                'foo = calmjs.npm:npm.runtime',
            ],
        })
        return runtime.Runtime(working_set=working_set)

    def test_npm_init_integration(self):
        remember_cwd(self)
        tmpdir = mkdtemp(self)
        os.chdir(tmpdir)

        rt = self.setup_runtime()
        rt(['foo', '--init', 'example.package1'])

        with open(join(tmpdir, 'package.json')) as fd:
            result = json.load(fd)

        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')

    def test_npm_install_integration(self):
        remember_cwd(self)
        tmpdir = mkdtemp(self)
        os.chdir(tmpdir)
        stub_mod_call(self, cli)
        rt = self.setup_runtime()
        rt(['foo', '--install', 'example.package1', 'example.package2'])

        with open(join(tmpdir, 'package.json')) as fd:
            result = json.load(fd)

        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')
        self.assertEqual(result['dependencies']['underscore'], '~1.8.3')
        # not foo install, but npm install since entry point specified
        # the actual runtime instance.
        self.assertEqual(self.call_args, ((['npm', 'install'],), {}))

    def test_npm_view(self):
        remember_cwd(self)
        tmpdir = mkdtemp(self)
        os.chdir(tmpdir)
        stub_stdouts(self)
        rt = self.setup_runtime()
        rt(['foo', '--view', 'example.package1', 'example.package2'])
        result = json.loads(sys.stdout.getvalue())
        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')
        self.assertEqual(result['dependencies']['underscore'], '~1.8.3')

        stub_stdouts(self)
        rt(['foo', 'example.package1', 'example.package2'])
        result = json.loads(sys.stdout.getvalue())
        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')
        self.assertEqual(result['dependencies']['underscore'], '~1.8.3')

    def test_npm_all_the_actions(self):
        remember_cwd(self)
        tmpdir = mkdtemp(self)
        os.chdir(tmpdir)
        stub_stdouts(self)
        stub_mod_call(self, cli)
        rt = self.setup_runtime()
        rt(['foo', '--install', '--view', '--init',
            'example.package1', 'example.package2'])

        # inside stdout
        result = json.loads(sys.stdout.getvalue())
        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')
        self.assertEqual(result['dependencies']['underscore'], '~1.8.3')

        with open(join(tmpdir, 'package.json')) as fd:
            result = json.load(fd)

        self.assertEqual(result['dependencies']['jquery'], '~3.1.0')
        self.assertEqual(result['dependencies']['underscore'], '~1.8.3')
        # not foo install, but npm install since entry point specified
        # the actual runtime instance.
        self.assertEqual(self.call_args, ((['npm', 'install'],), {}))

    def test_npm_verbose_quiet(self):
        remember_cwd(self)
        tmpdir = mkdtemp(self)
        os.chdir(tmpdir)
        rt = self.setup_runtime()

        stub_stdouts(self)
        rt(['-v', 'foo', '--init', 'example.package1'])
        self.assertIn("generating a flattened", sys.stderr.getvalue())
        self.assertNotIn("found 'package.json'", sys.stderr.getvalue())

        # extra verbosity shouldn't blow up
        stub_stdouts(self)
        rt(['-vvvv', 'foo', '--init', 'example.package1'])
        self.assertIn("generating a flattened", sys.stderr.getvalue())
        self.assertIn("found 'package.json'", sys.stderr.getvalue())

        # q and v negates each other
        stub_stdouts(self)
        rt(['-v', '-q', 'foo', '--init', 'example.package2'])
        self.assertNotIn("generating a flattened", sys.stderr.getvalue())
        self.assertNotIn("found 'package.json'", sys.stderr.getvalue())
        self.assertIn("WARNING", sys.stderr.getvalue())

        # extra quietness shouldn't blow up
        stub_stdouts(self)
        rt(['-qqqqq', 'foo', '--install', 'example.package2'])
        self.assertNotIn("WARNING", sys.stderr.getvalue())
