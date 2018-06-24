# Copyright (c) 2018 Stefan Marr <http://www.stefan-marr.de/>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
from __future__ import print_function
import os

from ...configurator     import Configurator, load_config
from ...executor         import Executor
from ...persistence      import DataStore
from ..rebench_test_case import ReBenchTestCase


class Issue81UnicodeSuite(ReBenchTestCase):

    def setUp(self):
        super(Issue81UnicodeSuite, self).setUp()
        self._set_path(__file__)
        if os.path.exists(self._path + '/build.log'):
            os.remove(self._path + '/build.log')

    def test_building(self):
        cnf = Configurator(load_config(self._path + '/issue_81.conf'), DataStore(),
                           data_file=self._tmp_file, exp_name='Test')
        runs = list(cnf.get_runs())
        runs = sorted(runs, key=lambda e: e.benchmark.name)

        ex = Executor(runs, False, True, build_log=cnf.build_log)
        ex.execute()

        self.assertEqual("Bench1", runs[0].benchmark.name)
        self.assertEqual(2, runs[0].get_number_of_data_points())

        self.assertTrue(os.path.exists(self._path + '/build.log'))

        with open(self._path + '/build.log', 'r') as build_file:
            log = build_file.read()

        try:
            unicode_char = unichr(22234)
        except NameError:
            unicode_char = chr(22234)

        self.assertGreater(log.find("VM:VM1|ERR:" + unicode_char), -1)
        self.assertGreater(log.find("VM:VM1|STD:" + unicode_char), -1)

        self.assertGreater(log.find("S:Suite1|ERR:" + unicode_char), -1)
        self.assertGreater(log.find("S:Suite1|STD:" + unicode_char), -1)

        if os.path.exists(self._path + '/build.log'):
            os.remove(self._path + '/build.log')
