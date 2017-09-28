# -*- coding: utf-8 -*-
import unittest
import sys
from os.path import basename
from os.path import dirname
from os.path import exists
from os.path import join
from os.path import normcase
from types import ModuleType

from pkg_resources import Distribution
from pkg_resources import EntryPoint
from pkg_resources import WorkingSet

from calmjs import artifact
from calmjs import dist
from calmjs.utils import pretty_logging
from calmjs.registry import get
from calmjs.artifact import ArtifactRegistry
from calmjs.artifact import verify_builder

from calmjs.testing import utils
from calmjs.testing import mocks


class IntegrationTestCase(unittest.TestCase):

    def test_integrated_get(self):
        # test that the default registry is registered.
        self.assertTrue(isinstance(get('calmjs.artifacts'), ArtifactRegistry))


class ArtifactRegistryTestCase(unittest.TestCase):
    """
    Standard test cases.
    """

    def assertPathsEqual(self, first, second):
        def norm(items):
            return [normcase(i) for i in items]
        self.assertEqual(norm(first), norm(second))

    def test_verify(self):
        def good_builder(package_names, export_target):
            "An expected argument signature"

        def bad_builder(package_names):
            "An unexpected argument signature"

        self.assertTrue(verify_builder(good_builder))
        self.assertFalse(verify_builder(bad_builder))

    def test_basic(self):
        working_dir = utils.mkdtemp(self)

        utils.make_dummy_dist(self, (
            ('requires.txt', '\n'.join([
            ])),
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'full.js = calmjs_testbuild:full',
                'base.lib.js = calmjs_testbuild:lib',
            ])),
        ), 'base', '1.0', working_dir=working_dir)

        utils.make_dummy_dist(self, (
            ('requires.txt', '\n'.join([
                'base',
            ])),
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'full.js = calmjs_testbuild:full',
                'lib1.lib.js = calmjs_testbuild:lib',
            ])),
        ), 'lib1', '1.0', working_dir=working_dir)

        utils.make_dummy_dist(self, (
            ('requires.txt', '\n'.join([
                'base',
            ])),
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'full.js = calmjs_testbuild:full',
                'lib2.lib.js = calmjs_testbuild_extended:lib',
            ])),
        ), 'lib2', '1.0', working_dir=working_dir)

        utils.make_dummy_dist(self, (
            ('requires.txt', '\n'.join([
                'lib1',
                'lib2',
            ])),
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'full.js = calmjs_testbuild:full',
                # this one doesn't provided a standalone library
            ])),
        ), 'app1', '1.0', working_dir=working_dir)

        mock_ws = WorkingSet([working_dir])

        # stub the default working set in calmjs.dist for the resolver
        # to work.
        utils.stub_item_attr_value(self, dist, 'default_working_set', mock_ws)
        # still specify the working set.
        registry = ArtifactRegistry('calmjs.artifacts', _working_set=mock_ws)

        self.assertNotEqual(len(list(registry.iter_records())), 0)

        self.assertEqual(
            normcase(join(
                working_dir, 'lib1-1.0.egg-info', 'calmjs_artifacts',
                'lib1.lib.js'
            )),
            normcase(registry.get_artifact_filename('lib1', 'lib1.lib.js')),
        )

        self.assertEqual([], list(registry.resolve_artifacts_by_builder_compat(
            ['no_such_package'], 'full')))
        self.assertEqual([], list(registry.resolve_artifacts_by_builder_compat(
            ['lib1'], 'no_such_rule')))

        self.assertPathsEqual([
            join(working_dir, 'lib1-1.0.egg-info', 'calmjs_artifacts',
                 'full.js'),
        ], list(registry.resolve_artifacts_by_builder_compat(
            ['lib1'], 'full')))

        self.assertPathsEqual([
            join(working_dir, 'base-1.0.egg-info', 'calmjs_artifacts',
                 'base.lib.js'),
            join(working_dir, 'lib1-1.0.egg-info', 'calmjs_artifacts',
                 'lib1.lib.js'),
        ], list(registry.resolve_artifacts_by_builder_compat(
            ['lib1'], 'lib', dependencies=True)))

        self.assertPathsEqual([
            join(working_dir, 'base-1.0.egg-info', 'calmjs_artifacts',
                 'base.lib.js'),
            join(working_dir, 'lib2-1.0.egg-info', 'calmjs_artifacts',
                 'lib2.lib.js'),
            join(working_dir, 'lib1-1.0.egg-info', 'calmjs_artifacts',
                 'lib1.lib.js'),
        ], list(registry.resolve_artifacts_by_builder_compat(
            ['lib2', 'lib1'], 'lib', dependencies=True)))

        self.assertPathsEqual([
            join(working_dir, 'base-1.0.egg-info', 'calmjs_artifacts',
                 'base.lib.js'),
            join(working_dir, 'lib1-1.0.egg-info', 'calmjs_artifacts',
                 'lib1.lib.js'),
            join(working_dir, 'lib2-1.0.egg-info', 'calmjs_artifacts',
                 'lib2.lib.js'),
        ], list(registry.resolve_artifacts_by_builder_compat(
            ['app1'], 'lib', dependencies=True)))

        entry_point = registry.belongs_to(join(
            working_dir, 'base-1.0.egg-info', 'calmjs_artifacts',
            'base.lib.js',
        ))
        self.assertEqual('base', entry_point.dist.project_name)
        self.assertEqual('base.lib.js', entry_point.name)

    def test_conflict_registration(self):
        # create an empty working set for a clean-slate test.
        cwd = utils.mkdtemp(self)
        mock_ws = WorkingSet([])
        registry = ArtifactRegistry('calmjs.artifacts', _working_set=mock_ws)
        # using named case for case sensitivity test.
        st = join(cwd, 'calmjs_artifacts', 'Simple.js')
        dist_ = Distribution(cwd, project_name='pkg', version='1.0')
        dist_.egg_info = cwd  # just lazy
        s1 = EntryPoint.parse('Simple.js = dummy_builder:builder1')
        s1.dist = dist_
        s2 = EntryPoint.parse('Simple.js = dummy_builder:builder2')
        s2.dist = dist_

        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.register_entry_point(s1)
            # normal registry usage shouldn't do this.
            registry.register_entry_point(s2)

        log = stream.getvalue()
        self.assertIn(
            "entry point 'Simple.js = dummy_builder:builder2' from package "
            "'pkg 1.0' will generate an artifact at '%s' but it was already "
            "registered to entry point 'Simple.js = dummy_builder:builder1'; "
            "conflicting entry point registration will be ignored." % st,
            log
        )

    def test_normcase_registration(self):
        # create an empty working set for a clean-slate test.
        cwd = utils.mkdtemp(self)
        mock_ws = WorkingSet([])
        dist_ = Distribution(cwd, project_name='pkg', version='1.0')
        dist_.egg_info = cwd  # just lazy
        registry = ArtifactRegistry('calmjs.artifacts', _working_set=mock_ws)
        # case sensitive test; have to patch the normcase at artifact
        # module with the nt version
        from ntpath import normcase as nt_normcase
        utils.stub_item_attr_value(self, artifact, 'normcase', nt_normcase)
        # using named case for case sensitivity test.
        c1 = EntryPoint.parse('case.js = dummy_builder:builder1')
        c1.dist = dist_
        c2 = EntryPoint.parse('Case.js = dummy_builder:builder2')
        c2.dist = dist_
        # use the error one
        ct = join(cwd, 'calmjs_artifacts', 'Case.js')
        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.register_entry_point(c1)
            registry.register_entry_point(c2)

        log = stream.getvalue()
        self.assertIn(
            "entry point 'Case.js = dummy_builder:builder2' from package "
            "'pkg 1.0' will generate an artifact at '%s' but it was already "
            "registered to entry point 'case.js = dummy_builder:builder1'; "
            "conflicting entry point registration will be ignored." % ct,
            log
        )
        self.assertIn(
            "the file mapping error is caused by this platform's case-"
            "insensitive filename", log
        )

    def test_build_artifacts_success(self):
        # dummy builder
        def builder(package_names, export_target):
            with open(export_target, 'w') as fd:
                fd.writelines(package_names)

        # inject dummy module and add cleanup
        mod = ModuleType('calmjs_testing_dummy')
        mod.complete = builder
        mod.partial = builder
        self.addCleanup(sys.modules.pop, 'calmjs_testing_dummy')
        sys.modules['calmjs_testing_dummy'] = mod

        working_dir = utils.mkdtemp(self)

        utils.make_dummy_dist(self, (
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'artifact.js = calmjs_testing_dummy:complete',
                'partial.js = calmjs_testing_dummy:partial',
            ])),
        ), 'app', '1.0', working_dir=working_dir)

        mock_ws = WorkingSet([working_dir])
        utils.stub_item_attr_value(self, dist, 'default_working_set', mock_ws)
        registry = ArtifactRegistry('calmjs.artifacts', _working_set=mock_ws)

        registry.build_artifacts('app')
        complete = list(registry.resolve_artifacts_by_builder_compat(
            ['app'], 'complete'))
        partial = list(registry.resolve_artifacts_by_builder_compat(
            ['app'], 'partial'))

        self.assertEqual(len(complete), 1)
        self.assertEqual(len(partial), 1)
        self.assertEqual(basename(complete[0]), 'artifact.js')
        self.assertEqual(basename(partial[0]), 'partial.js')

        with open(complete[0]) as fd:
            self.assertEqual(fd.read(), 'app')

        with open(partial[0]) as fd:
            self.assertEqual(fd.read(), 'app')

    def test_build_artifacts_logs_and_failures(self):
        # bad dummy builder
        def bad_builder():
            "Wrong function signature"

        # dummy builder
        def nothing_builder(package_names, export_target):
            "does nothing"

        # inject dummy module and add cleanup
        mod = ModuleType('calmjs_testing_dummy')
        mod.bad_builder = bad_builder
        mod.nothing_builder = nothing_builder
        self.addCleanup(sys.modules.pop, 'calmjs_testing_dummy')
        sys.modules['calmjs_testing_dummy'] = mod

        working_dir = utils.mkdtemp(self)

        utils.make_dummy_dist(self, (
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'not_exist.js = calmjs_testing_dummy:not_exist',
                'bad.js = calmjs_testing_dummy:bad_builder',
                'nothing.js = calmjs_testing_dummy:nothing_builder',
            ])),
        ), 'app', '1.0', working_dir=working_dir)

        utils.make_dummy_dist(self, (
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'bad.js = calmjs_testing_dummy:bad_builder',
                'nothing.js = calmjs_testing_dummy:nothing_builder',
            ])),
        ), 'bad', '1.0', working_dir=working_dir)

        utils.make_dummy_dist(self, (
            ('entry_points.txt', '\n'.join([
                '[calmjs.artifacts]',
                'nothing.js = calmjs_testing_dummy:nothing_builder',
            ])),
        ), 'nothing', '1.0', working_dir=working_dir)

        mock_ws = WorkingSet([working_dir])
        utils.stub_item_attr_value(self, dist, 'default_working_set', mock_ws)
        registry = ArtifactRegistry('calmjs.artifacts', _working_set=mock_ws)

        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.build_artifacts('app')

        log = stream.getvalue()
        self.assertIn(
            "unable to import the target builder for the entry point "
            "'not_exist.js = calmjs_testing_dummy:not_exist' from package "
            "'app 1.0'", log
        )

        self.assertIn(
            "the builder referenced by the entry point "
            "'bad.js = calmjs_testing_dummy:bad_builder' from package "
            "'app 1.0' has an incompatible signature", log
        )

        # force an existing file
        target = registry.records[('app', 'nothing.js')]
        with open(target, 'w'):
            pass

        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.build_artifacts('app')

        log = stream.getvalue()
        self.assertIn("unlinking existing export target at ", log)
        self.assertFalse(exists(target))

        # clog the directory location with a file
        with open(dirname(registry.records[('bad', 'bad.js')]), 'w'):
            pass

        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.build_artifacts('bad')

        log = stream.getvalue()
        self.assertIn("this target's parent is not a directory", log)

        with pretty_logging(stream=mocks.StringIO()) as stream:
            registry.build_artifacts('nothing')

        log = stream.getvalue()
        self.assertIn(
            "the entry point "
            "'nothing.js = calmjs_testing_dummy:nothing_builder' from package "
            "'nothing 1.0' failed to generate an artifact", log
        )