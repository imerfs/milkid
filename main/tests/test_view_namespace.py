"""``main.views`` re-exports every view module with ``import *``; two modules defining the same name would silently shadow each other."""
import collections
import importlib
import inspect
import pkgutil

from django.test import SimpleTestCase

import main.views as views_package


class ViewNamespace(SimpleTestCase):
    def defined_names(self):
        owners = collections.defaultdict(list)
        modules = [m.name for m in pkgutil.iter_modules(views_package.__path__)] + ['..messaging_views']
        for name in modules:
            module = importlib.import_module('main.messaging_views' if name.startswith('..') else f'main.views.{name}')
            for attr, value in vars(module).items():
                if attr.startswith('_') or not (inspect.isfunction(value) or inspect.isclass(value)):
                    continue
                if value.__module__ == module.__name__:
                    owners[attr].append(module.__name__)
        return owners

    def test_no_two_modules_define_the_same_public_name(self):
        clashes = {name: mods for name, mods in self.defined_names().items() if len(mods) > 1}
        self.assertEqual(clashes, {})

