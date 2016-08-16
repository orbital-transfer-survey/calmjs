# -*- coding: utf-8 -*-
import unittest
import os

from calmjs import base
from calmjs.testing import mocks
from calmjs.testing.utils import mkdtemp


class DummyModuleRegistry(base.BaseModuleRegistry):

    def _register_entry_point_module(self, entry_point, module):
        self.records[entry_point.name] = {module.__name__: module}


class BaseRegistryTestCase(unittest.TestCase):
    """
    Test the base registry.
    """

    def test_empty(self):
        working_set = mocks.WorkingSet([])
        registry = base.BaseRegistry(__name__, _working_set=working_set)
        self.assertEqual(registry.raw_entry_points, [])

    def test_entry_points(self):
        working_set = mocks.WorkingSet([
            'module1 = calmjs.testing.module1',
            'module2 = calmjs.testing.module2',
            'module3 = calmjs.testing.module3',
        ])

        registry = base.BaseRegistry(__name__, _working_set=working_set)
        self.assertEqual(len(registry.raw_entry_points), 3)

    def test_not_implemented(self):
        registry = base.BaseRegistry(__name__)

        with self.assertRaises(NotImplementedError):
            registry.get_record('something')

        with self.assertRaises(NotImplementedError):
            registry.iter_records()


class BaseModuleRegistryTestCase(unittest.TestCase):
    """
    Test the base registry.
    """

    def setUp(self):
        self.original_working_set = base.working_set

    def tearDown(self):
        base.working_set = self.original_working_set

    def test_empty(self):
        working_set = mocks.WorkingSet([])
        registry = base.BaseModuleRegistry(__name__, _working_set=working_set)
        self.assertEqual(list(registry.iter_records()), [])

    def test_bad_record(self):
        working_set = mocks.WorkingSet([
            'calmjs.testing.not_a_module = calmjs.testing.not_a_module',
        ])
        registry = base.BaseModuleRegistry(__name__, _working_set=working_set)
        self.assertEqual(len(registry.raw_entry_points), 1)
        self.assertEqual(registry.get_record('module'), {})
        self.assertEqual(list(registry.iter_records()), [])

    def test_not_implemented(self):
        working_set = mocks.WorkingSet([
            'calmjs.testing.module1 = calmjs.testing.module1',
        ])
        with self.assertRaises(NotImplementedError):
            base.BaseModuleRegistry(__name__, _working_set=working_set)

    def test_dummy_implemented(self):
        from calmjs.testing import module1
        working_set = mocks.WorkingSet([
            'calmjs.testing.module1 = calmjs.testing.module1',
        ])
        registry = DummyModuleRegistry(__name__, _working_set=working_set)
        result = registry.get_record('calmjs.testing.module1')
        self.assertEqual(result, {'calmjs.testing.module1': module1})
        self.assertEqual(list(registry.iter_records()), [
            ('calmjs.testing.module1', {'calmjs.testing.module1': module1}),
        ])

    def test_got_record_cloned(self):
        # returned records should clones.
        working_set = mocks.WorkingSet([
            'calmjs.testing.module1 = calmjs.testing.module1',
        ])
        registry = DummyModuleRegistry(__name__, _working_set=working_set)
        record1 = registry.get_record('calmjs.testing.module1')
        record2 = registry.get_record('calmjs.testing.module1')
        self.assertIsNot(record1, record2)


class BaseDriverClassTestCase(unittest.TestCase):
    """
    BaseDriver class test case.
    """

    def test_construction(self):
        driver = base.BaseDriver(
            node_path='node_path', env_path='env_path', working_dir='cwd',
            indent=2, separators=(', ', ':'))
        self.assertEqual(driver.node_path, 'node_path')
        self.assertEqual(driver.env_path, 'env_path')
        self.assertEqual(driver.working_dir, 'cwd')
        self.assertEqual(driver.indent, 2)
        self.assertEqual(driver.separators, (', ', ':'))

    def test_join_cwd(self):
        driver = base.BaseDriver()
        self.assertTrue(driver.join_cwd('bar').startswith(os.getcwd()))
        driver.working_dir = mkdtemp(self)

        result = driver.join_cwd('bar')
        self.assertTrue(result.startswith(driver.working_dir))
        self.assertTrue(result.endswith('bar'))

        result = driver.join_cwd()
        self.assertEqual(result, driver.working_dir)

    def test_which(self):
        driver = base.BaseDriver()
        # no binary, no nothing.
        self.assertIsNone(driver.which())

    def test_set_env_path_with_node_modules_undefined(self):
        driver = base.BaseDriver()
        with self.assertRaises(ValueError) as e:
            driver._set_env_path_with_node_modules()
        self.assertEqual(
            str(e.exception),
            "binary undefined for 'calmjs.base:BaseDriver' instance"
        )
