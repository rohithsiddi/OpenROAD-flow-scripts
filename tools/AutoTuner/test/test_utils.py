#############################################################################
##
## BSD 3-Clause License
##
## Copyright (c) 2026, Precision Innovations Inc.
## All rights reserved.
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are met:
##
## * Redistributions of source code must retain the above copyright notice, this
##   list of conditions and the following disclaimer.
##
## * Redistributions in binary form must reproduce the above copyright notice,
##   this list of conditions and the following disclaimer in the documentation
##   and/or other materials provided with the distribution.
##
## * Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived from
##   this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
## AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
## IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
## ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
## LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
## CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
## SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
## INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
## CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
## ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.
##
###############################################################################

import os
import sys
import tempfile
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import mock_open, patch

cur_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(cur_dir, "../src")
sys.path.insert(0, src_dir)

from autotuner import utils


class ParseFlowVariablesTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.flow_dir = os.path.join(self.tmp_dir.name, "flow")
        self.scripts_dir = os.path.join(self.flow_dir, "scripts")
        os.makedirs(self.scripts_dir)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_file(self, path, contents):
        with open(path, "w") as file:
            file.write(contents)

    def test_parse_flow_variables_from_scripts_and_vars_tcl(self):
        self._write_file(
            os.path.join(self.scripts_dir, "floorplan.tcl"),
            """
            set util $::env(core_utilization)
            set margin $env(CORE_MARGIN)
            """,
        )
        self._write_file(
            os.path.join(self.scripts_dir, "route.tcl"),
            """
            if {$::env(FASTROUTE_TCL) != ""} {
              puts $::env(FASTROUTE_TCL)
            }
            """,
        )
        self._write_file(
            os.path.join(self.flow_dir, "vars.tcl"),
            """
            set ::env(PLACE_DENSITY) 0.7
            """,
        )

        with patch.object(
            utils.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0),
        ) as run:
            variables = utils.parse_flow_variables(self.tmp_dir.name, "sky130hd")

        run.assert_called_once_with(
            ["make", "-C", self.flow_dir, "vars", "PLATFORM=sky130hd"],
            capture_output=True,
        )
        self.assertEqual(
            variables,
            {
                "CORE_UTILIZATION",
                "CORE_MARGIN",
                "FASTROUTE_TCL",
                "PLACE_DENSITY",
            },
        )

    def test_parse_flow_variables_exits_when_make_fails(self):
        with patch.object(
            utils.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=2),
        ):
            with patch("sys.stdout", new=StringIO()) as stdout:
                with self.assertRaises(SystemExit):
                    utils.parse_flow_variables(self.tmp_dir.name, "sky130hd")

        self.assertIn("[ERROR TUN-0018]", stdout.getvalue())

    def test_parse_flow_variables_exits_when_vars_tcl_is_missing(self):
        with patch.object(
            utils.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0),
        ):
            with patch("sys.stdout", new=StringIO()) as stdout:
                with self.assertRaises(SystemExit):
                    utils.parse_flow_variables(self.tmp_dir.name, "sky130hd")

        self.assertIn("[ERROR TUN-0019]", stdout.getvalue())


class ParseTunableVariablesTest(unittest.TestCase):
    def test_parse_tunable_variables_returns_only_tunable_keys(self):
        variables_yaml = {
            "CORE_UTILIZATION": {"tunable": 1},
            "PLACE_DENSITY": {"tunable": 1},
            "GENERATE_ARTIFACTS_ON_FAILURE": {"default": 0},
            "DETAILED_METRICS": {"tunable": 0},
        }

        with patch("builtins.open", mock_open(read_data="unused")) as open_mock:
            with patch.object(utils.yaml, "safe_load", return_value=variables_yaml):
                variables = utils.parse_tunable_variables()

        open_mock.assert_called_once()
        self.assertEqual(variables, {"CORE_UTILIZATION", "PLACE_DENSITY"})
        self.assertIsInstance(variables, set)


if __name__ == "__main__":
    unittest.main()
