# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.

"""Tool to convert and test pre-trained tensorflow models."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import argparse
import subprocess
import numpy as np
import yaml
import time
import utils
from math import ceil
import psutil
from subprocess import PIPE
import xml.etree.ElementTree as xml
from time import gmtime, strftime

def get_args():
    """Parse commandline."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default="/tmp/pre-trained", help="pre-trained models cache dir")
    parser.add_argument("--config", default="config/habana.yaml", help="yaml config to use")
    parser.add_argument("--tests", help="tests to run")
    parser.add_argument("--target", default="", help="target platform")
    parser.add_argument("--backend", nargs='+', type=str, default=["habana"], help="backend to use")
    parser.add_argument("--verbose", help="verbose output", action="store_true")
    parser.add_argument("--opset", type=int, default=7, help="opset to use")
    parser.add_argument("--debug", help="debug vlog", action="store_true")
    parser.add_argument("--list", help="list tests", action="store_true")
    parser.add_argument("--onnx-file", help="create onnx file in directory")
    parser.add_argument("--perf", help="capture performance numbers")
    parser.add_argument("--fold_const", help="enable tf constant_folding transformation before conversion",action="store_true")
    parser.add_argument("--include-disabled", help="include disabled tests", action="store_true")
    parser.add_argument("--override", help="names and values of tensors to overwrite")
    parser.add_argument("--time", default = None , help="To update/work with the existing Workbook specify the time it was created")
    parser.add_argument("--model_dir", default = "/mnt/tensorflow/models/", help="path of the TF model")
    parser.add_argument("--data_dir", default = "/mnt/tensorflow/data/", help="path of the Test dataset")
    parser.add_argument("--log_dir", default = "/mnt/tensorflow/nightly/", help="path to store the results")
    args = parser.parse_args()

    args.target = args.target.split(",")
    return args


def read_config(fname):
    """Create test class from yaml file."""
    tests = {}
    config = yaml.safe_load(open(fname, 'r').read())
    return config

def get_number_of_cpu(x):
    if x < 100:
        return 1
    else:
        return ceil(x/100)

def main():
    # suppress log info of tensorflow so that result of test can be seen much easier
    try:
        args = get_args()
        config = read_config(args.config)

        if(args.time==None) :
            showtime = strftime("%d-%m-%Y_%H:%M")
        else :
            showtime = args.time

        f = open("./test.cfg", "r")
        cfg = f.readline()
        f.close()
        cfg_auto = cfg.split("auto=")[-1].replace('"', '')
        if "true" in cfg_auto:
            mode = "automatic"
        elif "false" in cfg_auto:
            mode = "manual"

        if not os.path.exists(args.log_dir):
            os.makedirs(args.log_dir)
        if not os.path.exists(os.path.join(args.log_dir ,"habana_tf_"+mode+"_report_"+showtime)):
            os.makedirs(os.path.join(args.log_dir ,"habana_tf_"+mode+"_report_"+showtime))
        wb_name=os.path.join(os.path.join(args.log_dir,"habana_tf_"+mode+"_report_"+showtime),'Consolidated_Results_'+showtime+'.xlsx')
        xml_file = "./test_result.xml"
        print("LOG FILE:", wb_name)
        print ("BACKEND:", args.backend)
        utils.initialize_worksheet(wb_name)

        failed = 0
        count = 0
        run = 0
        num = 0
        skip = 0
        total = len(config)

        root = xml.Element("testsuites")
        userelement = xml.Element("testsuite", name="TensorflowONNXtests")
        root.append(userelement)

        start_time = time.time()
        for k, v in config.items():
            test = k
            count = count+1
            num = num+1
            start_sub_time = time.time()
            try:
                print ("MODEL:", test)
                cmd = ["python3.6", "run_test.py", str(args.model_dir),str(args.data_dir),str(test),str(v), wb_name, xml_file, str([count, args.debug, args.onnx_file, args.opset, args.perf, args.fold_const, args.override, args.include_disabled, mode]), args.log_dir, showtime, str(args.backend)]
                process = psutil.Popen(cmd, stdout=PIPE)

                peak_mem = 0
                peak_cpu = 0
                cpu_percent_list = []
                while(process.is_running()):
                    time.sleep(1)
                    mem = process.memory_info().rss/ (float)(2**30)
                    cpu = process.cpu_percent()
                    cpu_percent_list.append(cpu)
                    if mem > peak_mem:
                        peak_mem = mem
                    if cpu > peak_cpu:
                        peak_cpu = cpu
                    if mem == 0.0:
                        break

                print("Peak memory usage for the model {} is {} GB".format(test, peak_mem))
                print("Peak CPU utilization for the model {} is {} %".format(test, peak_cpu))
                print("list of cpu utilizations:", cpu_percent_list)
                output = process.communicate()[0]
                # output = subprocess.check_output(cmd)
                output = (output.decode("utf-8"))
                cpu_util_list = []
                for entry in cpu_percent_list:
                    num_cpu = get_number_of_cpu(entry)
                    if num_cpu == 0:
                        cpu_util_list.append(1)
                    else:
                        cpu_util_list.append(num_cpu)
                print("Utilization per CPU: ", cpu_util_list)
                Average_Util = 0.0
                for i in range(len(cpu_util_list)):
                    Average_Util = Average_Util + ((cpu_percent_list[i]/cpu_util_list[i]))

                Average_Util = Average_Util/len(cpu_percent_list)
                print("The Average Utilization per CPU for model {} is {}".format(test, Average_Util))

                print ("OUTPUT:", output.rstrip())
                ret = output.split("RETURN STATUS: ")[-1].split("\n")[0]
                print ("\n###############################################")

            except Exception as ex:
                ret = None
                failed = failed+1
            elapsed_sub_time = "{0:.2f}".format(time.time() - start_sub_time)
            if ret == '1':
                #utils.delete_rows_from_worksheet(3+count, wb_name)
                #count = count-1
                skip = skip+1
                print ("RESULT: Model is disabled in run models list\n")
                xml.SubElement(userelement, "testcase", name=test, time=str(elapsed_sub_time))
            elif ret == '0':
                run = run+1
                print ("RESULT: Model Passed\n")
                #count = count+1
                xml.SubElement(userelement, "testcase", name=test, time=str(elapsed_sub_time))
            elif ret == '2':
                run = run+1
                failed = failed+1
                #utils.delete_rows_from_worksheet(3+count, wb_name)
                #count = count-1
                print ("RESULT: Model Failed")
                print ("FAIL ERROR:", output.split("FAIL ERROR: ")[-1].split("RETURN STATUS: ")[0])
                print ("###############################################")
                msg = ""
                if output.find('Accuracy') != -1:
                    msg = "Accuracy Measurement failed"
                elif output.find('Performance') != -1:
                    msg = "Performance Measurement failed"
                else:
                    msg = "Model parsing failed. Check input and output names"
                failure = xml.SubElement(userelement, "testcase", name=test, time=str(elapsed_sub_time))
                fail_msg = xml.SubElement(failure, "failure")
                fail_msg.set("message", msg)
                fail_msg.set("type", "ERROR")
                fail_msg.text = output.split("FAIL ERROR: ")[-1].split("RETURN STATUS: ")[0]

        elapsed_time = "{0:.2f}".format(time.time() - start_time)
        userelement.set('time', str(elapsed_time))
        userelement.set('tests', str(num))
        userelement.set('failures', str(failed))
        userelement.set('errors', str(failed))
        userelement.set('disabled', str(skip))
        print("=== RESULT: {} failed of {}\n".format(failed, run))

        tree = xml.tostring(root, encoding='unicode')
        myfile = open(xml_file, "w+")
        myfile.write(tree)
        myfile.close()

        utils.format_worksheet(wb_name)
        return 0
    except Exception as ex:
        print (ex)
        return 1

if __name__ == "__main__":
    retcode = main()
    exit(retcode)
