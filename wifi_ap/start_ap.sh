#!/bin/bash

script_dir="$(dirname "$(realpath "$0")")";
cd $script_dir

python ap_service.py
