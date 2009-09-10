# Copyright (c) 2009 Stefan Marr <http://www.stefan-marr.de/>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
from __future__ import with_statement

import logging
import subprocess
import math
import numpy
import scipy.stats as stats
import scipy.stats.distributions as distributions

from contextpy import layer, proceed, activelayer, activelayers, after, around, before, base, globalDeactivateLayer

benchmark = layer("benchmark")
profile = layer("profile")

class Executor:
    
    def __init__(self, config, description, actions, executions,
                 benchmark=None, input_size=None):
        self.desctiption = description
        self.actions = actions
        self.executions = executions
        self.input_size = input_size
        self.config = config
        self.result = {}
        self.benchmark_data = {}
        self.current_data = None
        self.current_vm = None
        self.current_benchmark_suite = config["benchmark-suites"][benchmark]
        self.current_benchmark = None
        
        self.perf_reader = None
        
    def _construct_cmdline(self, command, input_size, benchmark, ulimit,
                           bench_location, path, binary, extra_args = None):
        cmdline  = ""
        cmdline += "cd %s && "%(bench_location)
        cmdline += "ulimit -t %s && "%(ulimit)
                
        if self.config["options"]["use_nice"]:
            cmdline += "sudo nice -n-20 "
        cmdline += "%s/%s "%(path, binary)
        cmdline += command%(dict(benchmark=benchmark, input=input_size))
        if extra_args is not None:
            cmdline += " %s"%(extra_args)
        return cmdline
    
    def _exec_vm_run(self, input_size):
        self.result[self.current_vm] = {}
        self.benchmark_data[self.current_vm] = {}
        vm_cfg = self.config["virtual_machines"][self.current_vm]
        

        # some VMs have there own versions of the benchmarks
        if self.current_benchmark_suite.has_key("location"):
            bench_location = self.current_benchmark_suite["location"]
        else:
            bench_location = vm_cfg["path"]
        
        for bench in self.current_benchmark_suite["benchmarks"]:
            if type(bench) == dict:
                bench_name = bench.keys()[0]
                extra_args = str(bench[bench_name]['extra-args'])
            else:
                extra_args = None
                bench_name = bench
            
            self.current_benchmark = bench_name
            
            self.current_data = []
            self.benchmark_data[self.current_vm][bench_name] = self.current_data
            
            cmdline = self._construct_cmdline(self.current_benchmark_suite["command"],
                                              input_size,
                                              bench_name,
                                              self.current_benchmark_suite["ulimit"],
                                              bench_location, 
                                              vm_cfg["path"], 
                                              vm_cfg["binary"],
                                              extra_args)
            logging.debug("command = " + cmdline)
            
            terminate = False
            error = (0, 0)  # (consequent_erroneous_runs, erroneous_runs)
            
            while not terminate:
                terminate, error = self._exec_benchmark_run(cmdline, error)
                logging.debug("Run: #%d"%(len(self.current_data)))
                    
            result = self._confidence(self.current_data, 
                                      self.config["statistics"]['confidence_level'])
            self.result[self.current_vm][bench_name] = result
            
            (mean, sdev, interval_details, interval_details_t) = result 
            logging.debug("Run completed for %s:%s, mean=%f, sdev=%f"%(self.current_vm, bench_name, mean, sdev))
            
            # TODO add here some user-interface stuff to show progress

    @before(benchmark)
    def _exec_vm_run(self, input_size):
        logging.debug("Statistic cfg: min_runs=%s, max_runs=%s"%(self.config["statistics"]["min_runs"],
                                                                 self.config["statistics"]["max_runs"]))
        
        p = __import__("performance", fromlist=self.current_benchmark_suite["performance_reader"])
        self.perf_reader = getattr(p, self.current_benchmark_suite["performance_reader"])()    
        
    def _exec_benchmark_run(self, cmdline, error):
        (consequent_erroneous_runs, erroneous_runs) = error
        p = subprocess.Popen(cmdline, stdout=subprocess.PIPE, shell=True)
        (output, tmp) = p.communicate()
        
        if p.returncode != 0:
            consequent_erroneous_runs += 1
            erroneous_runs += 1
            logging.warning("Run #%d of %s:%s failed"%(len(self.current_data), self.current_vm, self.current_benchmark))
        else:
            logging.debug(u"Output: %s"%(output))
            self._eval_output(output, consequent_erroneous_runs, erroneous_runs)
        
        return self._check_termination_condition(consequent_erroneous_runs, erroneous_runs)
    
    def _eval_output(self, output, consequent_erroneous_runs, erroneous_runs):
        pass
    
    @after(benchmark)
    def _eval_output(self, output, consequent_erroneous_runs, erroneous_runs, __result__):
        exec_time = self.perf_reader.parse_data(output)
        if exec_time is None:
            consequent_erroneous_runs += 1
            erroneous_runs += 1
            logging.warning("Run of %s:%s failed"%(self.current_vm, self.current_benchmark))
        else:    
            self.benchmark_data[self.current_vm][self.current_benchmark].append(exec_time)
            consequent_erroneous_runs = 0
            logging.debug("Run %s:%s result=%s"%(self.current_vm, self.current_benchmark, exec_time))
    
    @after(profile)
    def _check_termination_condition(self, consequent_erroneous_runs, erroneous_runs, __result__):
        return True, (consequent_erroneous_runs, erroneous_runs)
    
    def _check_termination_condition(self, consequent_erroneous_runs, erroneous_runs):
        return False, (consequent_erroneous_runs, erroneous_runs)
    
    @after(benchmark)
    def _check_termination_condition(self, consequent_erroneous_runs, erroneous_runs, __result__):
        terminate = False
        
        if consequent_erroneous_runs >= 3:
            logging.error("Three runs of %s have failed in a row, benchmark is aborted"%(self.current_benchmark))
            terminate = True
        elif erroneous_runs > len(self.current_data) / 2 and erroneous_runs > 6:
            logging.error("Many runs of %s are failing, benchmark is aborted."%(self.current_benchmark))
            terminate = True
        elif len(self.current_data) >= self.config["statistics"]["max_runs"]:
            logging.debug("Reached max_runs for %s"%(self.current_benchmark))
            terminate = True
        elif (len(self.current_data) > self.config["statistics"]["min_runs"]
              and self._confidence_reached(self.current_data)):
            logging.debug("Confidence is reached for %s"%(self.current_benchmark))
            terminate = True
        
        return terminate, (consequent_erroneous_runs, erroneous_runs)
    
                
    def _confidence_reached(self, values):
        (mean, sdev, norm_dist, t_dist) = \
            self._confidence(values, self.config["statistics"]['confidence_level'])
        ((i_low, i_high), i_percentage) = norm_dist
        
        logging.debug("Run: %d, Mean: %f, current error: %f, Interval: [%f, %f]"%(
                            len(values), mean, i_percentage, i_low, i_high))
        
        if i_percentage < self.config["statistics"]["error_margin"]:
            return True
        else:
            return False
        
    def _confidence(self, samples, confidence_level):
        """This function determines the confidence interval for a given set of samples, 
           as well as the mean, the standard deviation, and the size of the confidence 
           interval as a percentage of the mean.
        """
        
        mean = numpy.mean(samples)
        sdev = numpy.std(samples)
        n    = len(samples)
        norm = distributions.norm.ppf((1 + confidence_level)/2.0)
        
        
        interval_low  = mean - (norm * sdev / math.sqrt(n))
        interval_high = mean + (norm * sdev / math.sqrt(n))
        interval = (interval_low, interval_high)
        
        # original calculations from javastats, using students i.e. t distribution for fewer values
        df   = n - 1
        t    = distributions.t.ppf((1 + confidence_level)/2.0, df)
        interval_t = (interval_low_t, interval_high_t) = ( mean - t * sdev / math.sqrt(n) , mean + t * sdev / math.sqrt(n) )
        
        interval_size = interval_high - interval_low
        interval_percentage = interval_size / mean
        return (mean, sdev,
                (interval, interval_percentage), 
                (interval_t, (interval_high_t - interval_low_t) / mean)) 
    
    def execute(self):
        if isinstance(self.actions, basestring):
            self.actions = [self.actions]
        
        for action in self.actions:
            with activelayers(layer(action)):
                for vm in self.executions:
                    self.current_vm = vm
                    self._exec_vm_run(self.input_size)
    
    def get_results(self):
        return (self.result, self.benchmark_data)
    
        